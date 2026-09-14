"""
Automated i18n completeness tests (Spec_29 T-13).

Guard tests that enforce the multilingual Definition of Done on every
fast-gate CI run:

1. ``test_no_hardcoded_visible_text`` — scans public/seller-facing templates
   for visible text not wrapped in ``{% trans %``.
2. ``test_extraction_completeness`` — every ``{% trans %}``/``{{ _("…") }}``
   msgid exists in all three ``.po`` files (ru, bs, en).
3. ``test_no_empty_msgstr`` — ``ru`` and ``bs`` have 0 empty ``msgstr``
   for non-header entries (``en`` is exempt — msgid is English).
4. ``test_mo_compiled`` — compiled ``.mo`` files exist for every ``.po``.
5. ``test_template_extraction_coverage`` — msgids extracted from
   templates (``{% trans %}``, ``{{ _("…") }}``, ``{% blocktrans %}``)
   each exist in all three ``.po`` files.
6. ``test_hreflang_present`` — ``xfail`` until I18N-004 adds
   ``<link rel="alternate" hreflang>`` tags.
7. ``test_plural_forms`` — each ``.po`` Plural-Forms header matches CLDR.
8. ``test_locale_switch_re_render`` — ``{% trans %}`` re-renders in the
   active locale (bs/ru).

All are marked ``@pytest.mark.unit`` (fast gate, no database).
No third-party deps: reuses the ``_parse_po_entries`` parser approach
(no ``polib``); stdlib regex for template scanning.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.template import Context, Template
from django.utils import translation

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers (mirrors the parser in test_i18n_pipeline.py to avoid cross-test
# module imports)
# ---------------------------------------------------------------------------


def _parse_po_entries(text: str) -> list[tuple[str, str]]:
    """Parse ``.po`` text into ``(msgid, msgstr)`` tuples.

    Handles both simple and plural entries. For plural entries
    (``msgid_plural`` / ``msgstr[N]``), the singular ``msgid`` and the
    ``msgid_plural`` are both returned as separate tuples sharing the
    first ``msgstr`` value encountered.
    """
    entries: list[tuple[str, str]] = []
    cur_msgid: list[str] = []
    cur_msgstr: list[str] = []
    cur_plural: list[str] = []
    in_msgstr = False

    def _unescape(s: str) -> str:
        s = s.strip()
        if s.startswith('"') and s.endswith('"'):
            s = s[1:-1]
        return s.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")

    def _flush() -> None:
        if in_msgstr:
            entries.append(("".join(cur_msgid), "".join(cur_msgstr)))
        if cur_plural:
            entries.append(("".join(cur_plural), "".join(cur_msgstr)))

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("msgid "):
            _flush()
            cur_msgid = [_unescape(stripped[len("msgid ") :])]
            cur_msgstr = []
            cur_plural = []
            in_msgstr = False
        elif stripped.startswith("msgid_plural "):
            cur_plural = [_unescape(stripped[len("msgid_plural ") :])]
        elif stripped.startswith("msgstr"):
            in_msgstr = True
            rest = stripped[len("msgstr") :]
            if rest.startswith("["):
                rest = rest[rest.index("]") + 1 :]
            cur_msgstr = [_unescape(rest)]
        elif stripped.startswith('"') and in_msgstr:
            cur_msgstr.append(_unescape(stripped))
        elif stripped.startswith('"') and cur_plural:
            cur_plural.append(_unescape(stripped))
        elif stripped.startswith('"') and cur_msgid:
            cur_msgid.append(_unescape(stripped))
        elif stripped == "" and (in_msgstr or cur_plural):
            _flush()
            cur_msgid = []
            cur_msgstr = []
            cur_plural = []
            in_msgstr = False

    _flush()

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
    "code",
)

# ISO 4217 currency codes used as visible text (not translatable).
_NON_TRANSLATABLE_TOKENS = frozenset({"EUR", "RSD", "BAM"})


# ---------------------------------------------------------------------------
# Template → .po extraction helpers
# ---------------------------------------------------------------------------

# {% trans "msgid" %} and {% trans 'msgid' %} (inline string literal form).
_TRANS_INLINE_RE = re.compile(r"""{%\s*trans\s+(["'])(.*?)\1[^%]*?%}""", re.DOTALL)

# {{ _("msgid") }} and {{ _('msgid') }}.
_GETTEXT_VAR_RE = re.compile(r"""\{\{\s*_\(\s*(["'])(.*?)\1\s*\)\s*\}\}""", re.DOTALL)

# {% blocktrans [attrs] %}content{% endblocktrans %} (with optional {% plural %})
_BLOCKTRANS_RE = re.compile(
    r"""{%\s*blocktrans\b.*?%}(.*?){%\s*endblocktrans\s*%}""",
    re.DOTALL,
)
_BLOCKTRANS_PLURAL_RE = re.compile(r"{%\s*plural\s*%}")

# {{ var }} → %(var)s (the substitution makemessages applies inside blocktrans).
_TEMPLATE_VAR_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def _blocktrans_msgid(text: str) -> str:
    """Convert blocktrans inner text to a ``.po``-style msgid.

    Replaces ``{{ var }}`` placeholders with ``%(var)s`` (the format
    Django's ``makemessages`` uses) and strips surrounding whitespace.
    """
    return _TEMPLATE_VAR_RE.sub(r"%(\1)s", text).strip()


def _extract_template_msgids(content: str) -> list[str]:
    """Extract all translatable msgids from a template's raw source.

    Covers ``{% trans "..." %}``, ``{{ _("...") }}``, and
    ``{% blocktrans %}...{% endblocktrans %}`` (including plural forms).
    """
    msgids: list[str] = []

    for m in _TRANS_INLINE_RE.finditer(content):
        msgid = m.group(2)
        if msgid:
            msgids.append(msgid)

    for m in _GETTEXT_VAR_RE.finditer(content):
        msgid = m.group(2)
        if msgid:
            msgids.append(msgid)

    for m in _BLOCKTRANS_RE.finditer(content):
        inner = m.group(1)
        if _BLOCKTRANS_PLURAL_RE.search(inner):
            parts = _BLOCKTRANS_PLURAL_RE.split(inner)
        else:
            parts = [inner]
        for part in parts:
            msgid = _blocktrans_msgid(part)
            if msgid:
                msgids.append(msgid)

    return msgids


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


# ---------------------------------------------------------------------------
# Part B — extended extraction / pipeline gates
# ---------------------------------------------------------------------------


def _all_po_msgids() -> dict[str, set[str]]:
    """Return ``{lang: {msgid, ...}}`` for every ``.po`` file."""
    result: dict[str, set[str]] = {}
    for po_path in _po_files():
        lang = po_path.parent.parent.name
        entries = _parse_po_entries(po_path.read_text(encoding="utf-8"))
        result[lang] = {msgid for msgid, _ in entries if msgid}
    return result


def test_template_extraction_coverage() -> None:
    """Every msgid in templates must exist as a msgid in all ``.po`` files.

    Extracts ``{% trans "..." %}``, ``{{ _("...") }}``, and
    ``{% blocktrans %}...{% endblocktrans %}`` strings from every public
    template (via ``_collect_template_files``) and asserts each extracted
    msgid is present in all three locale ``.po`` files.
    """
    po_msgids = _all_po_msgids()
    if not po_msgids:
        pytest.fail("No .po files found")

    for tpl_path in _collect_template_files():
        content = tpl_path.read_text(encoding="utf-8")
        for msgid in _extract_template_msgids(content):
            for lang, msgids in po_msgids.items():
                assert msgid in msgids, (
                    f"{tpl_path.relative_to(settings.BASE_DIR)}: "
                    f"msgid {msgid!r} not found in {lang}/django.po"
                )


@pytest.mark.xfail(reason="hreflang tags added in I18N-004", strict=True)
def test_hreflang_present() -> None:
    """All page templates must include ``<link rel="alternate" hreflang>`` tags.

    One alternate link per configured language (ru, bs, en) is required for
    SEO correctness.  Tagged ``xfail`` until I18N-004 adds the tags; once
    they are present, remove the decorator so the test runs normally.
    """
    expected_langs = {code for code, _ in settings.LANGUAGES}
    found_langs: set[str] = set()
    for tpl_path in _collect_template_files():
        content = tpl_path.read_text(encoding="utf-8")
        for lang in expected_langs:
            if f'hreflang="{lang}"' in content:
                found_langs.add(lang)
    missing = expected_langs - found_langs
    assert not missing, f"Missing hreflang tags for languages: {sorted(missing)}"


def test_plural_forms() -> None:
    """Each ``.po`` file's ``Plural-Forms`` header must match CLDR rules."""
    expected = {
        "en": "nplurals=2; plural=(n != 1);",
        "ru": (
            "nplurals=3; plural=(n%10==1 && n%100!=11 ? 0 : "
            "n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2);"
        ),
        "bs": (
            "nplurals=3; plural=(n%10==1 && n%100!=11 ? 0 : "
            "n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2);"
        ),
    }
    for po_path in _po_files():
        lang = po_path.parent.parent.name
        text = po_path.read_text(encoding="utf-8")
        match = re.search(r'"Plural-Forms:\s*(.+?)\\n"', text, re.DOTALL)
        assert match, f"{po_path}: no Plural-Forms header found"
        raw = match.group(1)
        # .po concatenation may split fields across quoted lines; join them.
        actual = raw.replace('"', "").replace("\n", "").strip()
        assert actual == expected[lang], (
            f"{lang}: Plural-Forms mismatch — "
            f"expected {expected[lang]!r}, got {actual!r}"
        )


def test_locale_switch_re_render() -> None:
    """Rendering a ``{% trans %}`` tag re-renders content in the active locale.

    Verifies that ``translation.override`` activates the correct catalogue:
    ``bs`` renders the Bosnian translation, ``ru`` renders the Russian
    translation of the same msgid.
    """
    tpl = Template('{% load i18n %}{% trans "Dashboard" %}')

    with translation.override("bs"):
        rendered = tpl.render(Context({}))
    assert "Ploča" in rendered

    with translation.override("ru"):
        rendered = tpl.render(Context({}))
    assert "Панель управления" in rendered
