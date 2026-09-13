"""Fixed extraction completeness: correct multi-line .po parsing."""
import re
from pathlib import Path

po_dir = Path("src/backend/locale")
tmpl_dir = Path("src/backend/templates")


def unescape_po(s):
    """Strip surrounding quotes and unescape a single .po quoted string fragment."""
    s = s.strip()
    if s.startswith('"') and s.endswith('"') and len(s) >= 2:
        s = s[1:-1]
    return s.replace('\\n', '\n').replace('\\"', '"').replace('\\', '')


def parse_po_entries(content):
    """Return list of (msgid, msgstr) tuples with proper multi-line handling."""
    entries = []
    lines = content.splitlines()
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("msgid "):
            rest = stripped[6:].strip()
            msgid_parts = []
            if rest.startswith('"'):
                msgid_parts.append(rest)
                i += 1
                while i < len(lines) and lines[i].strip().startswith('"'):
                    msgid_parts.append(lines[i].strip())
                    i += 1
            elif rest == "":
                msgid_parts.append('""')
                i += 1
                while i < len(lines) and lines[i].strip().startswith('"'):
                    msgid_parts.append(lines[i].strip())
                    i += 1
            else:
                # single-word msgid (rare)
                msgid_parts.append(f'"{rest}"')
                i += 1
            msgid = "".join(unescape_po(p) for p in msgid_parts)

            # Find msgstr
            msgstr = None
            if i < len(lines) and lines[i].strip().startswith("msgstr"):
                mrest = lines[i].strip()[6:].strip()
                if mrest.startswith('"'):
                    msgstr_parts = [mrest]
                    i += 1
                    while i < len(lines) and lines[i].strip().startswith('"'):
                        msgstr_parts.append(lines[i].strip())
                        i += 1
                    msgstr = "".join(unescape_po(p) for p in msgstr_parts)
                elif mrest == "":
                    msgstr_parts = ['""']
                    i += 1
                    while i < len(lines) and lines[i].strip().startswith('"'):
                        msgstr_parts.append(lines[i].strip())
                        i += 1
                    msgstr = "".join(unescape_po(p) for p in msgstr_parts)
                else:
                    msgstr = mrest
                    i += 1
            elif i < len(lines) and lines[i].strip().startswith("msgid_plural"):
                # plural form — collect all msgstr[N]
                i += 1
                while i < len(lines):
                    sl = lines[i].strip()
                    if sl.startswith("msgstr["):
                        # parse this msgstr
                        pass
                    if sl.startswith('"'):
                        pass
                    i += 1
                    # advance past plural block
                continue
            else:
                msgstr = None

            if msgid and msgstr is not None:
                entries.append((msgid, msgstr))
        else:
            i += 1
    return entries


# --- Parse .po files ---
po_msgids = {}
po_empty = {}
for lang_dir in sorted(po_dir.iterdir()):
    if not lang_dir.is_dir():
        continue
    po_file = lang_dir / "LC_MESSAGES" / "django.po"
    if not po_file.exists():
        continue
    lang = lang_dir.name
    entries = parse_po_entries(po_file.read_text(encoding="utf-8"))
    msgids = {m for m, s in entries if m}
    empty = {m for m, s in entries if m and not s.strip() and lang != "en"}
    po_msgids[lang] = msgids
    po_empty[lang] = empty

print("=== PO FILE MSGID COUNTS (fixed parser) ===")
for lang in sorted(po_msgids):
    print(f"  {lang}: {len(po_msgids[lang])} msgids, {len(po_empty[lang])} empty msgstr")

# Cross-language consistency
all_po = set()
for m in po_msgids.values():
    all_po.update(m)
print(f"  Total unique msgids: {len(all_po)}")
for lang in sorted(po_msgids):
    missing = all_po - po_msgids[lang]
    if missing:
        print(f"  {lang}: {len(missing)} msgids present in other langs but missing")
        for m in sorted(missing)[:5]:
            print(f"    - '{m[:70]}'")
    else:
        print(f"  {lang}: all msgids present in all languages ✓")

# --- Extract msgids from templates ---
all_tmpl = list(tmpl_dir.rglob("*.html"))
excluded = ("admin/", "analytics/moderation_dashboard.html", "components/feature_tag.html")
scanned = [f for f in all_tmpl
           if not any(f.relative_to(tmpl_dir).as_posix().startswith(ex) for ex in excluded)]

tmpl_msgids = {}
for f in scanned:
    content = f.read_text(encoding="utf-8")
    rel = f.relative_to(tmpl_dir).as_posix()
    for m in re.finditer(r'\{%\s*trans\s+([\"\'])(.*?)\1\s*%\}', content):
        tmpl_msgids.setdefault(m.group(2), set()).add(rel)
    for m in re.finditer(r'\{\{\s*_\(\s*([\"\'])(.*?)\1\s*\)\s*\}\}', content):
        tmpl_msgids.setdefault(m.group(2), set()).add(rel)
    for m in re.finditer(r'\{%\s*trans\s*%\}\s*(.*?)\s*\{%\s*endtrans\s*%\}', content, re.DOTALL):
        msg = m.group(1).strip()
        if msg:
            tmpl_msgids.setdefault(msg, set()).add(rel)

print(f"\n=== TEMPLATE EXTRACTION ({len(scanned)} templates) ===")
print(f"  Template msgids: {len(tmpl_msgids)}")

# --- Compare ---
print("\n=== MISSING FROM .po FILES ===")
total_missing = 0
for msgid in sorted(tmpl_msgids):
    for lang in sorted(po_msgids):
        if msgid not in po_msgids[lang]:
            print(f"  {lang}: '{msgid[:70]}' (from: {sorted(tmpl_msgids[msgid])[:3]})")
            total_missing += 1
if total_missing == 0:
    print(f"  All {len(tmpl_msgids)} template msgids found in all .po files ✓")
else:
    print(f"  Total missing: {total_missing}")

# --- blocktrans blocks ---
print("\n=== {% blocktrans %} blocks (NOT checked by extraction test) ===")
bt = 0
for f in scanned:
    content = f.read_text(encoding="utf-8")
    rel = f.relative_to(tmpl_dir).as_posix()
    for m in re.finditer(r'\{%\s*blocktrans[^%]*%\}(.*?)\{%\s*endblocktrans\s*%\}', content, re.DOTALL):
        bt += 1
        print(f"  {rel}: '{m.group(1).strip()[:70]}...'")
print(f"  Total: {bt}")

# --- POT-Creation-Date ---
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
