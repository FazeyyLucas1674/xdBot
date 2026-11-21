#!/usr/bin/env python3
"""Patches xdBot (GD 2.2074 / Geode 4.x) for GD 2.2091 / Geode v6.
Safe to run more than once. Run from the repo root."""
import re, pathlib

ROOT = pathlib.Path(__file__).resolve().parent
SRC = ROOT / "src"
changed = {}

def edit(path, fn):
    text = path.read_text(encoding="utf-8", errors="surrogateescape")
    new = fn(text)
    if new != text:
        path.write_text(new, encoding="utf-8", errors="surrogateescape")
        changed[str(path.relative_to(ROOT))] = True

def sources():
    for p in SRC.rglob("*"):
        if p.suffix in (".cpp", ".hpp", ".h") and p.name != "json.hpp":
            yield p

# 1. ffmpeg API events: old Event style no longer exists, replace with a stub
EVENTS = '''#pragma once

#include "render_settings.hpp"

#include <Geode/Result.hpp>

#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

// Stub: the old ffmpeg-api event style does not exist in Geode v6.
// Rendering through the ffmpeg API is unavailable in this port.
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
'''
ev = SRC / "renderer" / "ffmpeg" / "events.hpp"
if ev.exists() and ev.read_text(errors="surrogateescape") != EVENTS:
    ev.write_text(EVENTS)
    changed[str(ev.relative_to(ROOT))] = True

# 2. Popup is not a template in Geode v6: add a small compatibility shim
SHIM = '''#pragma once

#include <Geode/Geode.hpp>
#include <asp/fs/std.hpp>

// Compatibility shim: mimics the old geode::Popup<Args...> (setup + initAnchored)
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
'''
shim = SRC / "xd_popup.hpp"
if not shim.exists() or shim.read_text() != SHIM:
    shim.write_text(SHIM)
    changed[str(shim.relative_to(ROOT))] = True

def inc(text):
    if '#include "xd_popup.hpp"' not in text:
        text = text.replace("#include <Geode/Geode.hpp>", '#include <Geode/Geode.hpp>\n#include "xd_popup.hpp"', 1)
    return text
edit(SRC / "includes.hpp", inc)

# 3. Source-wide mechanical fixes
def fix(text):
    t = text
    # Popup<> -> XdPopup / geode::Popup
    t = t.replace("geode::Popup<std::string, geode::Popup<>*>", "XdPopup<std::string, geode::Popup*>")
    t = t.replace("geode::Popup<geode::Popup<>*, geode::Popup<>*, bool>", "XdPopup<geode::Popup*, geode::Popup*, bool>")
    t = t.replace("public geode::Popup<>", "public XdPopup<>")
    t = t.replace("geode::Popup<>", "geode::Popup")
    # gd:: types are gone
    t = t.replace("gd::string", "std::string")
    t = re.sub(r"gd::vector<", "std::vector<", t)
    # PlayLayer::init lost a parameter in 2.2091
    t = t.replace("bool init(GJGameLevel * level, bool b1, bool b2)", "bool init(GJGameLevel * level, bool b1)")
    t = t.replace("PlayLayer::init(level, b1, b2)", "PlayLayer::init(level, b1)")
    # GJBaseGameLayer::processCommands gained two parameters
    t = t.replace("void processCommands(float dt) {", "void processCommands(float dt, bool pcA, bool pcB) {")
    t = t.replace("GJBaseGameLayer::processCommands(dt)", "GJBaseGameLayer::processCommands(dt, pcA, pcB)")
    # Mod paths are asp::fs::Path now
    t = re.sub(r"\b(getSaveDir|getResourcesDir|getConfigDir|getTempDir|getPersistentDir)\(\)(?!\.toStdPath)", r"\1().toStdPath()", t)
    t = re.sub(r"getSettingValue<std::filesystem::path>\(([^()]*)\)", r"getSettingValue<asp::fs::Path>(\1).toStdPath()", t)
    t = re.sub(r'setSettingValue<std::filesystem::path>\(("[^"]*"), (.*)\);', r'setSettingValue<asp::fs::Path>(\1, asp::fs::Path::fromStdPath(\2));', t)
    return t
for p in sources():
    edit(p, fix)

# 4. PlayerObject fields that no longer exist in the 2.2091 bindings
def drop_fields(text):
    lines = text.split("\n")
    keep = [l for l in lines if not re.search(r"\bm_currentSlope3\b|\bm_flashRelated\b", l) or l.lstrip().startswith("//")]
    return "\n".join(keep) if len(keep) != len(lines) else text
for p in (SRC / "practice_fixes").glob("*.cpp"):
    edit(p, drop_fields)

print("port.py: patched %d file(s)" % len(changed))
for k in sorted(changed):
    print("  -", k)
