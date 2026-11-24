#!/usr/bin/env python3
"""xdBot port, round 3 (run after port.py). Safe to run more than once."""
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

def sources():
    for p in SRC.rglob("*"):
        if p.suffix in (".cpp", ".hpp", ".h") and p.name not in ("json.hpp", "xd_popup.hpp"):
            yield p

# helpers appended to the compatibility header
def popup_hpp(text):
    if "xdReadDir" in text:
        return text
    return text + '''
#include <type_traits>
#include <vector>

template <class T>
std::filesystem::path xdToStd(T const& p) {
    if constexpr (std::is_same_v<std::decay_t<T>, std::filesystem::path>) return p;
    else return p.toStdPath().unwrap();
}

inline std::vector<std::filesystem::path> xdReadDir(std::filesystem::path const& dir) {
    std::vector<std::filesystem::path> out;
    auto res = geode::utils::file::readDirectory(asp::fs::Path::fromStdPath(dir));
    if (res.isOk()) {
        for (auto const& e : res.unwrap()) out.push_back(xdToStd(e));
    }
    return out;
}
'''
edit(SRC / "xd_popup.hpp", popup_hpp)

def fix(t):
    # wide-string paths only work with MSVC streams
    t = t.replace("std::ofstream f(widePath, std::ios::binary);", "std::ofstream f(std::filesystem::path(widePath), std::ios::binary);")
    t = t.replace("std::ifstream file(Utils::widen(path.string()));", "std::ifstream file(std::filesystem::path(Utils::widen(path.string())));")
    t = t.replace("std::ofstream f2(Utils::widen(pathString), std::ios::binary);", "std::ofstream f2(std::filesystem::path(Utils::widen(pathString)), std::ios::binary);")
    # hook must return on every path
    t = t.replace("            return FMODAudioEngine::playEffect(path, speed, p2, volume);\n    }",
                  "            return FMODAudioEngine::playEffect(path, speed, p2, volume);\n\n        return 0;\n    }")
    # keyBackClicked is protected now; onClose is public
    t = re.sub(r"(?<!this)(?<![\w>])(\w+)->keyBackClicked\(\);", r"\1->onClose(nullptr);", t)
    # Popup close button is a geode::Button now
    t = re.sub(r"m_closeBtn->getNormalImage\(\)->setScale\(([^)]*)\);", r"m_closeBtn->setScale(\1);", t)
    # search box callback
    t = t.replace("searchInput->setDelegate(this);",
                  "searchInput->setCallback([this](std::string const&) { this->textChanged(nullptr); });")
    t = t.replace("search = Utils::toLower(node->getString());", "search = Utils::toLower(searchInput->getString());")
    # readDirectory
    t = t.replace("file::readDirectory(path).unwrapOrDefault()", "xdReadDir(path)")
    # ColorPickPopupDelegate was removed
    t = re.sub(r",\s*public ColorPickPopupDelegate", "", t)
    t = re.sub(r"void updateColor\((const cocos2d::ccColor4B&|cocos2d::ccColor4B const&)\) override", r"void updateColor(\1)", t)
    t = t.replace("popup->setDelegate(this);",
                  "popup->setCallback([this](cocos2d::ccColor4B const& c) { this->updateColor(c); });")
    return t
for p in sources():
    edit(p, fix)

print("port2.py: patched %d file(s)" % len(changed))
for k in sorted(changed):
    print("  -", k)
