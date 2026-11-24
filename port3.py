#!/usr/bin/env python3
"""xdBot port, round 4 (run after port2.py). Safe to run more than once."""
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

# These pointers are plain FLAlertLayer/CCLayer, which still have a public keyBackClicked()
edit(SRC / "ui" / "button_setting.cpp", lambda t: t.replace("layer->onClose(nullptr);", "layer->keyBackClicked();"))
edit(SRC / "ui" / "record_layer.cpp", lambda t: t.replace("layer->onClose(nullptr);", "layer->keyBackClicked();"))
edit(SRC / "ui" / "load_macro_layer.cpp", lambda t: t.replace("loadLayer->onClose(nullptr);", "loadLayer->keyBackClicked();"))

# More PlayerObject fields that are gone in the 2.2091 bindings
GONE = r"\b(m_stateNoStickX|m_stateNoStickY|m_stateUnk2)\b"
def drop_fields(text):
    lines = text.split("\n")
    keep = [l for l in lines if l.lstrip().startswith("//") or not re.search(GONE, l)]
    return "\n".join(keep) if len(keep) != len(lines) else text
for p in (SRC / "practice_fixes").glob("*.cpp"):
    edit(p, drop_fields)

print("port3.py: patched %d file(s)" % len(changed))
for k in sorted(changed):
    print("  -", k)
