import re
from pathlib import Path

BASE = Path(r"C:\py_dev\mko_bazuna\src\backend")
tmpl_dir = BASE / "templates"
locale_dir = BASE / "locale"

trans_msgids = set()
trans_pattern = re.compile(r'{%\s*trans\s+["\'](.+?)["\']\s*%}', re.DOTALL)

files = sorted(tmpl_dir.rglob("*.html"))
for f in files:
    content = f.read_text(encoding="utf-8")
    for m in trans_pattern.finditer(content):
        trans_msgids.add(m.group(1))

print("Template files scanned: " + str(len(files)))
print("Unique trans msgids in templates: " + str(len(trans_msgids)))

def parse_po_msgids(text):
    msgids = set()
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("msgid "):
            val = line[6:].strip().strip('"')
            j = i + 1
            while j < len(lines) and lines[j].strip().startswith('"'):
                nxt = lines[j].strip()
                if nxt.startswith("msgstr") or nxt.startswith("msgid") or nxt.startswith("#"):
                    break
                val += nxt.strip().strip('"')
                j += 1
            msgids.add(val)
            i = j
        else:
            i += 1
    return msgids

for lang in ["ru", "bs", "en"]:
    po = locale_dir / lang / "LC_MESSAGES" / "django.po"
    text = po.read_text(encoding="utf-8")
    po_msgids = parse_po_msgids(text)
    missing = trans_msgids - po_msgids
    print("\n" + lang + ".po: " + str(len(po_msgids)) + " msgids")
    print("  Missing in " + lang + " (in templates, not in .po): " + str(len(missing)))
    if missing:
        for m in sorted(missing):
            print("    - " + repr(m))
