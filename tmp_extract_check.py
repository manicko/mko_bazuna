"""Extraction completeness comparison: template {% trans %} msgids vs .po msgids."""
import re
from pathlib import Path

po_dir = Path("src/backend/locale")
tmpl_dir = Path("src/backend/templates")

# --- 1. Parse .po files for msgids ---
po_msgids = {}
po_empty = {}
for lang_dir in sorted(po_dir.iterdir()):
    if not lang_dir.is_dir():
        continue
    po_file = lang_dir / "LC_MESSAGES" / "django.po"
    if not po_file.exists():
        continue
    lang = lang_dir.name
    content = po_file.read_text(encoding="utf-8")
    msgids = set()
    empty = set()
    lines = content.splitlines()
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("msgid "):
            rest = stripped[6:].strip()
            cur_msgid = None
            if rest.startswith('"'):
                parts = [rest]
                i += 1
                while i < len(lines) and lines[i].strip().startswith('"'):
                    parts.append(lines[i].strip())
                    i += 1
                joined = "".join(parts)
                cur_msgid = joined.strip('"').replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")
            elif rest == "":
                i += 1
                parts = []
                while i < len(lines) and lines[i].strip().startswith('"'):
                    parts.append(lines[i].strip())
                    i += 1
                if parts:
                    joined = "".join(parts)
                    cur_msgid = joined.strip('"').replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")
            else:
                cur_msgid = rest
                i += 1

            # Find msgstr
            cur_msgstr = None
            if i < len(lines) and lines[i].strip().startswith("msgstr"):
                mrest = lines[i].strip()[6:].strip()
                if mrest.startswith('"'):
                    sparts = [mrest]
                    i += 1
                    while i < len(lines) and lines[i].strip().startswith('"'):
                        sparts.append(lines[i].strip())
                        i += 1
                    sjoined = "".join(sparts)
                    cur_msgstr = sjoined.strip('"').replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")
                elif mrest == "":
                    cur_msgstr = ""
                    i += 1
            elif i < len(lines) and lines[i].strip().startswith("msgid_plural"):
                # plural - skip msgstr[0..N]
                i += 1
                while i < len(lines) and (lines[i].strip().startswith('"') or lines[i].strip().startswith("msgstr[")):
                    i += 1
                continue

            if cur_msgid and cur_msgid != "":
                msgids.add(cur_msgid)
                if lang != "en" and cur_msgstr is not None and not cur_msgstr.strip():
                    empty.add(cur_msgid)
        else:
            i += 1
    po_msgids[lang] = msgids
    po_empty[lang] = empty

print("=== PO FILE MSGID COUNTS ===")
for lang in sorted(po_msgids):
    e = po_empty.get(lang, set())
    print(f"  {lang}: {len(po_msgids[lang])} msgids, {len(e)} empty msgstr")
    if e:
        for x in sorted(e)[:5]:
            print(f"    EMPTY: '{x[:60]}'")

# Cross-language consistency
all_po = set()
for m in po_msgids.values():
    all_po.update(m)
print(f"  Total unique msgids across all: {len(all_po)}")
for lang in sorted(po_msgids):
    missing = all_po - po_msgids[lang]
    if missing:
        print(f"  {lang}: {len(missing)} msgids in OTHER langs but missing from {lang}")
        for m in sorted(missing)[:5]:
            print(f"    - '{m[:60]}'")

# --- 2. Extract msgids from templates ---
all_tmpl = list(tmpl_dir.rglob("*.html"))
excluded = ("admin/", "analytics/moderation_dashboard.html", "components/feature_tag.html")
scanned = [f for f in all_tmpl
           if not any(f.relative_to(tmpl_dir).as_posix().startswith(ex) for ex in excluded)]
print(f"\n=== TEMPLATE EXTRACTION ({len(scanned)} templates, excluded {len(all_tmpl)-len(scanned)}) ===")

tmpl_msgids = {}
for f in scanned:
    content = f.read_text(encoding="utf-8")
    rel = f.relative_to(tmpl_dir).as_posix()
    for m in re.finditer(r'\{%\s*trans\s+([\"\'])(.*?)\1\s*%\}', content):
        tmpl_msgids.setdefault(m.group(2), set()).add(rel)
    for m in re.finditer(r'\{\{\s*_\(\s*([\"\'])(.*?)\1\s*\)\s*\}\}', content):
        tmpl_msgids.setdefault(m.group(2), set()).add(rel)
    for m in re.finditer(r'\{%\s*trans\s*%\}\s*(.*?)\s*\{%\s*endtrans\s*%\}', content, re.DOTALL):
        msgid = m.group(1).strip()
        if msgid:
            tmpl_msgids.setdefault(msgid, set()).add(rel)

print(f"  Template msgids extracted: {len(tmpl_msgids)}")

# --- 3. Compare template msgids vs .po msgids ---
print("\n=== MISSING FROM .po FILES ===")
total_missing = 0
for msgid in sorted(tmpl_msgids):
    for lang in sorted(po_msgids):
        if msgid not in po_msgids[lang]:
            print(f"  {lang}: '{msgid[:60]}' not in .po (from: {sorted(tmpl_msgids[msgid])[:3]})")
            total_missing += 1
if total_missing == 0:
    print(f"  All {len(tmpl_msgids)} template msgids found in all 3 .po files.")
else:
    print(f"  Total missing: {total_missing}")

# --- 4. blocktrans blocks ---
print("\n=== {% blocktrans %} BLOCKS (not extracted by simple regex, not checked by test) ===")
bt = 0
for f in scanned:
    content = f.read_text(encoding="utf-8")
    rel = f.relative_to(tmpl_dir).as_posix()
    for m in re.finditer(r'\{%\s*blocktrans[^%]*%\}(.*?)\{%\s*endblocktrans\s*%\}', content, re.DOTALL):
        bt += 1
        print(f"  {rel}: '{m.group(1).strip()[:70]}...'")
print(f"  Total: {bt}")

# --- 5. POT-Creation-Date check ---
print("\n=== POT-Creation-Date per locale ===")
for lang_dir in sorted(po_dir.iterdir()):
    if not lang_dir.is_dir():
        continue
    po_file = lang_dir / "LC_MESSAGES" / "django.po"
    if not po_file.exists():
        continue
    for line in po_file.read_text(encoding="utf-8").splitlines():
        if "POT-Creation-Date" in line:
            print(f"  {lang_dir.name}: {line.strip()}")
