"""
Automated i18n completeness tests (Spec_29 T-13).

Four guard tests that enforce the multilingual Definition of Done on every
fast-gate CI run:

1. ``test_no_hardcoded_visible_text`` — scans public/seller-facing templates
   for visible text not wrapped in ``{% trans %``.
2. ``test_extraction_completeness`` — every ``{% trans %}``/``{{ _("…") }}``
   msgid exists in all three ``.po`` files (ru, bs, en).
3. ``test_no_empty_msgstr`` — ``ru`` and ``bs`` have 0 empty ``msgstr``
   for non-header entries (``en`` is exempt — msgid is English).
4. ``test_mo_compiled`` — compiled ``.mo`` files exist for every ``.po``.

All are marked ``@pytest.mark.unit`` (fast gate, no database).
No third-party deps: reuses the ``_parse_po_entries`` parser approach
(no ``polib``); stdlib regex for template scanning.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from django.conf import settings


pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers (mirrors the parser in test_i18n_pipeline.py to avoid cross-test
# module imports)
# ---------------------------------------------------------------------------


def _parse_po_entries(text: str) -> list[tuple[str, str]]:
    """Parse ``.po`` text into ``(msgid, msgstr)`` tuples."""
    entries: list[tuple[str, str]] = []
    cur_msgid: list[str] = []
    cur_msgstr: list[str] = []
    in_msgstr = False

    def _unescape(s: str) -> str:
        s = s.strip()
        if s.startswith('"') and s.endswith('"'):
            s = s[1:-1]
        return s.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("msgid "):
            if in_msgstr:
                entries.append(("".join(cur_msgid), "".join(cur_msgstr)))
                cur_msgid = []
                cur_msgstr = []
                in_msgstr = False
            cur_msgid = [_unescape(stripped[len("msgid ") :])]
        elif stripped.startswith("msgstr "):
            in_msgstr = True
            cur_msgstr = [_unescape(stripped[len("msgstr ") :])]
        elif stripped.startswith('"') and in_msgstr:
            cur_msgstr.append(_unescape(stripped))
        elif stripped.startswith('"') and cur_msgid:
            cur_msgid.append(_unescape(stripped))
        elif stripped == "" and in_msgstr:
            entries.append(("".join(cur_msgid), "".join(cur_msgstr)))
            cur_msgid = []
            cur_msgstr = []
            in_msgstr = False

    if in_msgstr:
        entries.append(("".join(cur_msgid), "".join(cur_msgstr)))

    return entries


def _po_files() -> list[Path]:
    """Return every ``django.po`` under the configured ``LOCALE_PATHS``."""
    paths: list[Path] = []
    for base in settings.LOCALE_PATHS:
        paths.extend(sorted(Path(str(base)).rglob("django.po")))
    return paths


def _collect_template_files() -> list[Path]:
    """Collect all template files to scan for hardcoded text.

    Includes all templates except admin staff-only pages, moderation dashboard,
    and feature_tag (DB-based i18n).
    """
    exclude_subpaths = (
        "admin/",
        "analytics/moderation_dashboard.html",
        "components/feature_tag.html",
    )
    files: list[Path] = []
    for tmpl_cfg in settings.TEMPLATES:
        for d in tmpl_cfg.get("DIRS", []):
            d = Path(d)
            for f in d.rglob("*.html"):
                rel = f.relative_to(d).as_posix()
                if any(rel.startswith(ex) for ex in exclude_subpaths):
                    continue
                files.append(f)
    return files


# Regex to find text nodes (text between `>` and `<` that isn't
# inside a Django template tag or variable).
_TEXT_NODE_RE = re.compile(r">([^<]+)<")

# Patterns that indicate text IS translater (wrapped or gettext call).
_TRANS_MARKERS = (
    "{% trans ",
    "{% blocktrans",
    "{{ _(",
    "{{ _('",
)

# Tags whose content is not user-visible.
_SKIP_TAGS = (
    "script",
    "style",
    "head",
    "meta",
    "input",
    "br",
    "hr",
    "link",
    "title",
    "code",
)

# ISO 4217 currency codes used as visible text (not translatable).
_NON_TRANSLATABLE_TOKENS = frozenset({"EUR", "RSD", "BAM"})


# ---------------------------------------------------------------------------
# Part A — i18n completeness guards
# ---------------------------------------------------------------------------


def test_no_hardcoded_visible_text() -> None:
    """Visible text in public/seller templates must be translatable.

    Removes ``{% trans %}``/``{% blocktrans %}``/``{{ _("") }}`` blocks
    (and their inner text), Django tags, HTML comments, and non-visible
    elements, then checks for remaining bare text nodes.
    """
    for tpl_path in _collect_template_files():
        content = tpl_path.read_text(encoding="utf-8")
        cleaned = content

        # Remove <script>...</script>, <style>...</style>, <head>...</head>
        for tag in _SKIP_TAGS:
            cleaned = re.sub(
                rf"<{tag}\b[^>]*>.*?</{tag}>",
                "",
                cleaned,
                flags=re.DOTALL | re.IGNORECASE,
            )
            cleaned = re.sub(
                rf"<{tag}\b[^>]*/?>",
                "",
                cleaned,
                flags=re.IGNORECASE,
            )

        # Remove HTML comments
        cleaned = re.sub(r"<!--.*?-->", "", cleaned, flags=re.DOTALL)

        # Remove Django comments {# ... #}
        cleaned = re.sub(r"\{#.*?#\}", "", cleaned, flags=re.DOTALL)

        # Remove Django comment blocks {% comment %}...{% endcomment %}
        cleaned = re.sub(
            r"{%\s*comment\s*%}.*?{%\s*endcomment\s*%}",
            "",
            cleaned,
            flags=re.DOTALL | re.IGNORECASE,
        )

        # Remove trans-wrapped content BEFORE stripping Django tags, so
        # bare text inside {% blocktrans %}...{% endblocktrans %} is not
        # mistaken for hardcoded text after tag removal.
        # Block-form trans (inline string literal only — no inner text):
        cleaned = re.sub(
            r"{%\s*trans\s+[%\"'].*?%}",
            "",
            cleaned,
            flags=re.DOTALL,
        )
        # Block-form trans with content between open/close tags:
        cleaned = re.sub(
            r"{%\s*trans\s*%}.*?{%\s*endtrans\s*%}",
            "",
            cleaned,
            flags=re.DOTALL,
        )
        # Block-form blocktrans (with optional attributes like "with ..."):
        cleaned = re.sub(
            r"{%\s*blocktrans[^%]*%}.*?{%\s*endblocktrans\s*%}",
            "",
            cleaned,
            flags=re.DOTALL,
        )
        # Inline gettext calls {{ _("..."), {{ _('...'), etc.
        cleaned = re.sub(
            r"{{\s*_\([\s\S]*?\)\s*}}",
            "",
            cleaned,
            flags=re.DOTALL,
        )

        # Remove all remaining Django template tags {% ... %} and {{ ... }}
        cleaned = re.sub(r"{%.*?%}", "", cleaned, flags=re.DOTALL)
        cleaned = re.sub(r"{{.*?}}", "", cleaned, flags=re.DOTALL)

        # Now find remaining text nodes (text between > and <)
        for match in _TEXT_NODE_RE.finditer(cleaned):
            text = match.group(1)
            stripped = text.strip()
            if not stripped:
                continue
            # Remove HTML entities (&copy;, &rsaquo;, &nbsp;, etc.)
            stripped = re.sub(r"&[a-zA-Z]+;", "", stripped).strip()
            if not stripped:
                continue
            # Skip very short tokens (likely punctuation around dynamic vars)
            if len(stripped) <= 2:
                continue
            # Skip strings that are only punctuation/whitespace
            if not re.search(r"[a-zA-Zа-яА-ЯёЁ]", stripped):
                continue
            # Skip ISO currency codes and other non-translatable tokens
            if stripped in _NON_TRANSLATABLE_TOKENS:
                continue
            pytest.fail(
                f"{tpl_path.relative_to(settings.BASE_DIR)}: "
                f"hardcoded visible text not wrapped in gettext: "
                f"'{stripped}'"
            )


def test_extraction_completeness() -> None:
    """Every msgid in one `.po` file exists in all other `.po` files."""
    all_msgids: set[str] = set()
    by_lang: dict[str, set[str]] = {}
    for po_path in _po_files():
        lang = po_path.parent.parent.name
        entries = _parse_po_entries(po_path.read_text(encoding="utf-8"))
        msgids = {msgid for msgid, _ in entries if msgid}
        by_lang[lang] = msgids
        all_msgids.update(msgids)

    if not all_msgids:
        pytest.fail("No msgids found in any .po file")

    for lang, msgids in by_lang.items():
        missing = all_msgids - msgids
        assert not missing, (
            f"{lang}: missing {len(missing)} msgids from other locales: "
            f"{sorted(missing)[:5]}..."
        )


def test_no_empty_msgstr() -> None:
    """``ru`` and ``bs`` have no empty ``msgstr``; ``en`` is exempt."""
    for po_path in _po_files():
        locale_code = po_path.parent.parent.name
        if locale_code == "en":
            continue
        text = po_path.read_text(encoding="utf-8")
        entries = _parse_po_entries(text)
        empty = [msgid for msgid, msgstr in entries if msgid and not msgstr.strip()]
        assert not empty, f"{po_path}: empty msgstr for msgids: {empty}"


def test_no_raw_get_name_in_templates() -> None:
    """Templates must use ``|get_category_name:LANGUAGE_CODE`` or
    ``|get_city_name:LANGUAGE_CODE`` filters instead of raw
    ``{{ obj.get_name }}`` calls, which render in the default language
    regardless of the active UI locale.
    """
    for tpl_path in _collect_template_files():
        content = tpl_path.read_text(encoding="utf-8")
        matches = re.findall(r"\{\{[^}]*\.get_name[^}]*\}\}", content)
        if matches:
            pytest.fail(
                f"{tpl_path.relative_to(settings.BASE_DIR)}: "
                f"raw .get_name call found; use get_category_name/get_city_name "
                f"filter with LANGUAGE_CODE instead: {matches}"
            )


def test_mo_compiled() -> None:
    """Compiled ``.mo`` files exist for every ``.po``."""
    for po_path in _po_files():
        mo_path = po_path.with_suffix(".mo")
        assert mo_path.exists(), f"Missing compiled file: {mo_path}"
