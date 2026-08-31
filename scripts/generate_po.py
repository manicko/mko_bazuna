#!/usr/bin/env python3
"""Generate .po files with extracted UI strings for Mko Bazuna."""

from collections import defaultdict
from pathlib import Path

LOCALE_DIR = (
    Path(__file__).resolve().parent.parent.parent / "src" / "backend" / "locale"
)

LANGUAGES = {
    "ru": {
        "team": "Russian <ru@li.org>",
        "plural": "nplurals=3; plural=(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2);",
    },
    "bs": {
        "team": "Bosnian <bs@li.org>",
        "plural": "nplurals=3; plural=(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2);",
    },
    "en": {
        "team": "English <en@li.org>",
        "plural": "nplurals=2; plural=(n != 1);",
    },
}

PO_HEADER_TEMPLATE = """# {lang_name} translations for Mko Bazuna.
# Copyright (C) 2026 Mko Bazuna
# This file is distributed under the same license as the Mko Bazuna package.
# Automatically generated, 2026.
#
msgid ""
msgstr ""
"Project-Id-Version: Mko Bazuna\\n"
"Report-Msgid-Bugs-To: \\n"
"POT-Creation-Date: 2026-07-27 17:15+0200\\n"
"PO-Revision-Date: YEAR-MO-DA HO:MI+ZONE\\n"
"Last-Translator: FULL NAME <EMAIL@ADDRESS>\\n"
"Language-Team: {team}\\n"
"Language: {lang}\\n"
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Content-Transfer-Encoding: 8bit\\n"
"Plural-Forms: {plural}\\n"

"""

ENTRIES = [
    ("templates/ads/list.html", "Search"),
    ("templates/ads/list.html", "Search ads..."),
    ("templates/ads/list.html", "Category"),
    ("templates/ads/list.html", "Ads"),
    ("templates/ads/detail.html", "Photo"),
    ("templates/ads/detail.html", "for"),
    ("templates/ads/detail.html", "Location:"),
    ("templates/ads/detail.html", "Category:"),
    ("templates/ads/detail.html", "Published:"),
    ("templates/ads/detail.html", "Contact Seller"),
    ("templates/ads/detail.html", "Seller unavailable for contact"),
    ("templates/ads/detail.html", "Back to listings"),
    ("templates/ads/partials/ad_list.html", "Did you mean:"),
    ("templates/ads/partials/ad_list.html", "No image"),
    ("templates/ads/partials/ad_list.html", "Page navigation"),
    ("templates/ads/partials/ad_list.html", 'No results found for "%(query)s"'),
    (
        "templates/ads/partials/ad_list.html",
        "Try a different search term or browse all categories",
    ),
    ("templates/ads/partials/ad_list.html", "No ads available"),
    ("templates/ads/partials/ad_list.html", "Check back later for new listings"),
    ("templates/ads/partials/ad_list.html", "No ads available yet"),
    (
        "templates/ads/partials/ad_list.html",
        "Be the first to create an ad via Telegram!",
    ),
]


def build_po_body(entries):
    lines = []
    by_file = defaultdict(list)
    for f, msg in entries:
        by_file[f].append(msg)

    seen = set()
    for f in sorted(by_file):
        for msg in by_file[f]:
            if msg in seen:
                continue
            seen.add(msg)
            escaped_msg = msg.replace('"', '\\"')
            lines.append(f"#: {f}")
            if "%(" in msg:
                lines.append("#, python-format")
            lines.append(f'msgid "{escaped_msg}"')
            lines.append('msgstr ""')
            lines.append("")
    return "\n".join(lines)


def main():
    body = build_po_body(ENTRIES)
    for lang_code, info in LANGUAGES.items():
        header = PO_HEADER_TEMPLATE.format(
            lang_name=info["team"].split()[0],
            team=info["team"],
            lang=lang_code,
            plural=info["plural"],
        )
        content = header + body
        po_path = LOCALE_DIR / lang_code / "LC_MESSAGES" / "django.po"
        po_path.parent.mkdir(parents=True, exist_ok=True)
        po_path.write_text(content, encoding="utf-8")
        print(f"Written {po_path} ({len(content)} bytes)")


if __name__ == "__main__":
    main()
