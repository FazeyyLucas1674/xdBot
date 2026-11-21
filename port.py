#!/usr/bin/env python3
"""Patches xdBot (GD 2.2074 / Geode 4.x) for GD 2.2091 / Geode v6 (round 2).
Run from the repo root before building. Safe to run more than once."""
import re, pathlib

ROOT = pathlib.Path(__file__).resolve().parent
SRC = ROOT / "src"
changed = {}

def edit(path, fn):
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8", errors="surrogateescape")
    new = fn(text)
    if new != text:
        path.write_text(new, encoding="utf-8", errors="surrogateescape")
        changed[str(path.relative_to(ROOT))] = True

def write(path, content):
    if not path.exists() or path.read_text(errors="surrogateescape") != content:
        path.write_text(content)
        changed[str(path.relative_to(ROOT))] = True

def sources():
    for p in SRC.rglob("*"):
        if p.suffix in (".cpp", ".hpp", ".h") and p.name not in ("json.hpp", "xd_popup.hpp"):
            yield p

# ---- 1. ffmpeg API events: stub ----
write(SRC / "renderer" / "ffmpeg" / "events.hpp", '''#pragma once

#include "render_settings.hpp"

#include <Geode/Result.hpp>

#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

// Stub: the old ffmpeg-api event style does not exist in Geode v6.
namespace ffmpeg::events {

class Recorder {
public:
    Recorder() = default;
    bool isValid() const { return false; }
    geode::Result<> init(RenderSettings const&) { return geode::Err("FFmpeg API is not available"); }
    void stop() {}
    geode::Result<> writeFrame(const std::vector<uint8_t>&) { return geode::Err("FFmpeg API is not available"); }
    static std::vector<std::string> getAvailableCodecs() { return {}; }
};

class AudioMixer {
public:
    AudioMixer() = delete;
    static geode::Result<> mixVideoAudio(std::filesystem::path const&, std::filesystem::path const&, std::filesystem::path const&) {
        return geode::Err("FFmpeg API is not available");
    }
    static geode::Result<> mixVideoRaw(std::filesystem::path const&, const std::vector<float>&, std::filesystem::path const&) {
        return geode::Err("FFmpeg API is not available");
    }
};

}
''')

# ---- 2. Compatibility header (Popup shim + file picker helper) ----
write(SRC / "xd_popup.hpp", '''#pragma once

#include <Geode/Geode.hpp>
#include <asp/fs/std.hpp>

#include <filesystem>
#include <optional>

// Mimics the old geode::Popup<Args...> (setup + initAnchored)
template <class... Args>
class XdPopup : public geode::Popup {
protected:
    virtual bool setup(Args... args) = 0;

public:
    bool initAnchored(float width, float height, Args... args, char const* bg = "GJ_square01.png") {
        if (!geode::Popup::init(width, height, bg)) return false;
        return this->setup(args...);
    }

    bool initAnchored(float width, float height, Args... args, char const* bg, cocos2d::CCRect) {
        return this->initAnchored(width, height, args..., bg);
    }
};

// Replacement for the old file picker callback style (callback takes Result<path>*)
template <class F>
void xdPick(geode::utils::file::PickMode mode, geode::utils::file::FilePickOptions options, F&& callback) {
    geode::async::spawn(
        geode::utils::file::pick(mode, std::move(options)),
        [cb = std::forward<F>(callback)](geode::Result<std::optional<asp::fs::Path>> r) mutable {
            geode::Result<std::filesystem::path> res = geode::Err("File picker was cancelled");
            if (r.isOk() && r.unwrap().has_value()) {
                res = geode::Ok(r.unwrap().value().toStdPath().unwrap());
            }
            cb(&res);
        }
    );
}
''')

def inc(text):
    if '#include "xd_popup.hpp"' not in text:
        text = text.replace("#include <Geode/Geode.hpp>", '#include <Geode/Geode.hpp>\n#include "xd_popup.hpp"', 1)
    return text
edit(SRC / "includes.hpp", inc)

# Utils::setBackgroundColor: popups now use NineSlice instead of CCScale9Sprite
def utils_hpp(text):
    if "static void setBackgroundColor(T* bg)" in text:
        return text
    decl = "static void setBackgroundColor(cocos2d::extension::CCScale9Sprite* bg);"
    extra = '''
    template <class T>
    static void setBackgroundColor(T* bg) {
        cocos2d::ccColor3B color = geode::Mod::get()->getSettingValue<cocos2d::ccColor3B>("background_color");
        if (color == cocos2d::ccc3(51, 68, 153)) color = cocos2d::ccc3(255, 255, 255);
        bg->setColor(color);
    }
'''
    return text.replace(decl, decl + "\n" + extra, 1)
edit(SRC / "utils" / "utils.hpp", utils_hpp)

# ---- 3. macro editor: text changes now come through callbacks ----
def macro_editor(text):
    if "macroEditInputChanged" in text:
        return text
    text = text.replace('#include "macro_editor.hpp"\n',
        '#include "macro_editor.hpp"\nstatic void macroEditInputChanged(int which, std::string text);\n', 1)
    text = text.replace("pageInput->getInputNode()->setDelegate(this);",
        "pageInput->setCallback([](std::string const& s) { macroEditInputChanged(0, s); });")
    text = text.replace("frameInput->getInputNode()->setDelegate(this);",
        "frameInput->setCallback([](std::string const& s) { macroEditInputChanged(1, s); });")
    text = text.replace("void MacroEditLayer::textChanged(CCTextInputNode* input) {\n    if (!input || !editLayer) return;\n\n    std::string text = input->getString();",
        "void MacroEditLayer::textChanged(CCTextInputNode*) {}\n\nstatic void macroEditInputChanged(int which, std::string text) {\n    if (!editLayer) return;")
    text = text.replace("if (input == editLayer->pageInput->getInputNode()) {", "if (which == 0) {")
    text = text.replace("if (input == editLayer->frameInput->getInputNode()) {", "if (which == 1) {")
    text = text.replace("layer->keyBackClicked();", "layer->onClose(nullptr);")
    return text
edit(SRC / "ui" / "macro_editor.cpp", macro_editor)

# ---- 4. Source-wide mechanical fixes ----
GONE_FIELDS = r"\b(m_currentSlope3|m_flashRelated|m_flashRelated1|m_gv0096|m_gv0100|m_unk9e8|m_ringOrStreakRelated|m_unkAAC|m_gamevar0060|m_gamevar0062|m_robotHasRun3|m_robotHasRun2|m_item20)\b"

def fix(text):
    t = text
    # Popup<> -> XdPopup / geode::Popup
    t = t.replace("geode::Popup<std::string, geode::Popup<>*>", "XdPopup<std::string, geode::Popup*>")
    t = t.replace("geode::Popup<geode::Popup<>*, geode::Popup<>*, bool>", "XdPopup<geode::Popup*, geode::Popup*, bool>")
    t = t.replace("public geode::Popup<>", "public XdPopup<>")
    t = t.replace("geode::Popup<>", "geode::Popup")
    # Popup now already has TextInputDelegate as a base
    t = re.sub(r",\s*public TextInputDelegate", "", t)
    # gd:: types are gone
    t = t.replace("gd::string", "std::string")
    t = t.replace("gd::vector<", "std::vector<")
    # signatures that changed in GD 2.2091
    t = t.replace("bool init(GJGameLevel * level, bool b1, bool b2)", "bool init(GJGameLevel * level, bool b1)")
    t = t.replace("PlayLayer::init(level, b1, b2)", "PlayLayer::init(level, b1)")
    t = t.replace("void processCommands(float dt) {", "void processCommands(float dt, bool pcA, bool pcB) {")
    t = t.replace("GJBaseGameLayer::processCommands(dt)", "GJBaseGameLayer::processCommands(dt, pcA, pcB)")
    t = t.replace("bool dispatchKeyboardMSG(enumKeyCodes key, bool isKeyDown, bool isKeyRepeat) {",
                  "bool dispatchKeyboardMSG(enumKeyCodes key, bool isKeyDown, bool isKeyRepeat, double timestamp) {")
    t = t.replace("CCKeyboardDispatcher::dispatchKeyboardMSG(key, isKeyDown, isKeyRepeat)",
                  "CCKeyboardDispatcher::dispatchKeyboardMSG(key, isKeyDown, isKeyRepeat, timestamp)")
    t = re.sub(r"dispatchKeyboardMSG\((enumKeyCodes::KEY_Space), (true|false), false\)", r"dispatchKeyboardMSG(\1, \2, false, 0.0)", t)
    # Mod paths are asp::fs::Path now (toStdPath returns a Result)
    t = re.sub(r"\b(getSaveDir|getResourcesDir|getConfigDir|getTempDir|getPersistentDir)\(\)(?!\.toStdPath)", r"\1().toStdPath()", t)
    t = re.sub(r"getSettingValue<std::filesystem::path>\(([^()]*)\)", r"getSettingValue<asp::fs::Path>(\1).toStdPath()", t)
    t = re.sub(r"\.toStdPath\(\)(?!\.unwrap)", ".toStdPath().unwrap()", t)
    t = re.sub(r'setSettingValue<std::filesystem::path>\(("[^"]*"), (.*)\);',
               r'setSettingValue<asp::fs::Path>(\1, asp::fs::Path::fromStdPath(\2));', t)
    # Geode file helpers want asp::fs::Path
    t = re.sub(r"file::pick\((.*?)\)\.listen\(", r"xdPick(\1, ", t)
    t = re.sub(r"(xdPick\([^\n]*?)\.toStdPath\(\)\.unwrap\(\)", r"\1", t)
    t = re.sub(r"file::openFolder\(([^\n]*?)\.toStdPath\(\)\.unwrap\(\)\);", r"file::openFolder(\1);", t)
    t = re.sub(r"file::openFolder\((\w+)\)", r"file::openFolder(asp::fs::Path::fromStdPath(\1))", t)
    t = re.sub(r"createDirectoryAll\((\w+)\)", r"createDirectoryAll(asp::fs::Path::fromStdPath(\1))", t)
    # CCARRAY_FOREACH was removed
    t = re.sub(r"CCARRAY_FOREACH\((\w+),\s*(\w+)\)", r"for (CCObject* \2 : CCArrayExt<CCObject*>(\1))", t)
    # listenForSettingChanges needs an explicit type now
    t = re.sub(r'geode::listenForSettingChanges\(("[^"]+"), \+\[\]\(([\w:]+) value\)',
               r'geode::listenForSettingChanges<\2>(\1, [](\2 value)', t)
    # geode::TextInput no longer exposes the vanilla input node
    t = re.sub(r"(\w+)->getInputNode\(\)->setAllowedChars\((.*?)\);", r"\1->setFilter(\2);", t)
    t = re.sub(r"(\w+)->getInputNode\(\)->setMaxLabelLength\((.*?)\);", r"\1->setMaxCharCount(\2);", t)
    t = re.sub(r"(\w+)->getInputNode\(\)->setDelegate\(this\);",
               r"\1->setCallback([this](std::string const&) { this->textChanged(nullptr); });", t)
    lines = t.split("\n")
    lines = [l for l in lines if l.lstrip().startswith("//") or not re.search(
        r"getInputNode\(\)->(m_placeholderLabel|detachWithIME|onClickTrackNode|m_cursor)|->m_placeholderLabel->", l)]
    t = "\n".join(lines)
    return t
for p in sources():
    edit(p, fix)

# ---- 5. PlayerObject fields that no longer exist in the 2.2091 bindings ----
def drop_fields(text):
    lines = text.split("\n")
    keep = [l for l in lines if l.lstrip().startswith("//") or not re.search(GONE_FIELDS, l)]
    return "\n".join(keep) if len(keep) != len(lines) else text
for p in (SRC / "practice_fixes").glob("*.cpp"):
    edit(p, drop_fields)

print("port.py: patched %d file(s)" % len(changed))
for k in sorted(changed):
    print("  -", k)
