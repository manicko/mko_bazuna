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
  6. ``test_hreflang_present`` — every page template renders
    ``<link rel="alternate" hreflang>`` tags (I18N-004).
7. ``test_plural_forms`` — each ``.po`` Plural-Forms header matches CLDR.
8. ``test_locale_switch_re_render`` — ``{% trans %}`` re-renders in the
   active locale (bs/ru).
9. ``test_bot_no_raw_model_field_access`` — AST-scans bot
   ``handlers/`` and ``services/`` for raw ``name_i18n.get("ru")`` calls
   and ``.name``/``.title``/``.description`` field access in f-strings,
   ``%`` dict values, list comprehensions, and keyword-argument values
   (I18N-001).
10. ``test_title_tags_translated`` — page ``<title>`` tags localize per
    language (I18N-003).
11. ``test_plural_forms_runtime`` — ``{% blocktrans count %}`` selects the
    correct CLDR plural form at runtime (I18N-003).
12. ``test_no_hardcoded_js_strings`` — inline ``<script>`` literals must not
    carry untranslated user-visible text (I18N-008).

``test_hreflang_present`` is extended with the ``x-default`` exclusion
(spec §5f) and ``test_locale_switch_re_render`` with an ``en`` locale-switch
assertion (msgid fallback convention).

All are marked ``@pytest.mark.unit`` (fast gate, no database).
No third-party deps: reuses the ``_parse_po_entries`` parser approach
(no ``polib``); stdlib regex for template scanning.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from django.conf import settings
from django.template import Context, Template
from django.template.loader import get_template
from django.test import RequestFactory
from django.utils import translation

from testing.i18n_helpers import _parse_po_entries

pytestmark = [pytest.mark.unit]


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


# ---------------------------------------------------------------------------
# Inline <script> JS string-literal guard (I18N-008)
# ---------------------------------------------------------------------------

# Inline <script> blocks only (external src= scripts and empty bodies skipped).
_JS_SCRIPT_BLOCK_RE = re.compile(
    r"<script\b([^>]*)>(.*?)</script>", re.DOTALL | re.IGNORECASE
)

# Outer-quote-aware JS string literal matcher.  Single-line only: this sidesteps
# false matches from regex literals such as /"/g (which have no same-line
# closing quote) and treats any inner quotes as part of the literal's content.
_JS_STRING_RE = re.compile(r'''(["'])((?:\\.|(?!\1).)*)\1''')

# JS comments are not user-visible text; strip before scanning for literals.
_JS_COMMENT_RE = re.compile(r"/\*.*?\*/|//[^\n]*", re.DOTALL)

# Django template expressions embedded inside script strings (e.g.
# {{ var|escapejs }}, {% trans "..." %}) are server-rendered, not literal JS
# text, so they are stripped before scanning for hardcoded literals.
_JS_DJANGO_TAG_RE = re.compile(r"{%.*?%}|\{\{.*?\}\}", re.DOTALL)

# Non-translatable tokens that legitimately appear as quoted JS strings.
_JS_NON_TRANSLATABLE_TOKENS = frozenset({
    "js=", "path=", "samesite", "secure", "cookie", "document.cookie",
    "use strict", "use client", "escapejs", "data-domain", "x-csrftoken",
})

# Characters that indicate a string is markup/path/code rather than prose.
_JS_CODE_CHAR_RE = re.compile(r"[/=\[\]{}|~@#\\]")


def _is_user_visible_js_string(content: str) -> bool:
    """Return True if a JS string-literal body looks like translatable prose.

    A positive match requires a space plus at least one letter; HTML/SVG
    markup, Django template expressions, CSS selectors, JS directives,
    cookie/config tokens, and code-heavy strings are all excluded so that
    genuine user-facing text (e.g. ``"Delete ad?"``) is the only hit.
    """
    source = content.strip()
    if not source or " " not in source:
        return False
    if not re.search(r"[A-Za-z\u0400-\u04FF]", source):
        return False
    if "{{" in source or "{%" in source:  # stray template syntax (post-strip)
        return False
    if "<" in source or ">" in source:  # HTML / SVG markup
        return False
    if source.startswith(("#", ".", "[", "'", '"')):  # CSS selector
        return False
    if source in ("use strict", "use client"):
        return False
    folded = source.lower()
    if any(token in folded for token in _JS_NON_TRANSLATABLE_TOKENS):
        return False
    if _JS_CODE_CHAR_RE.search(source):
        return False
    return True


def test_no_hardcoded_js_strings() -> None:
    """Quoted JS string literals in inline <script> blocks must not carry
    hardcoded user-visible text (I18N-008).

    Scans every inline ``<script>...</script>`` block in the template scope
    (``_collect_template_files``) and flags string literals that look like
    natural-language prose.  Server-rendered template expressions, HTML/SVG
    markup, CSS selectors, JS directives, and cookie/config tokens are excluded
    as non-translatable.  The current baseline's inline JS uses only such
    non-translatable strings, so it reports no violations; this guards against
    future hardcoded copy in JS.
    """
    violations: list[str] = []
    for tpl_path in _collect_template_files():
        source = tpl_path.read_text(encoding="utf-8")
        rel_path = str(tpl_path.relative_to(settings.BASE_DIR))

        for opening, body in _JS_SCRIPT_BLOCK_RE.findall(source):
            # Skip external scripts and empty/whitespace-only bodies.
            if "src=" in opening or not body.strip():
                continue
            # Strip JS comments first — prose inside /* ... */ or // lines is
            # not user-visible (e.g. the "All Categories" label in a comment).
            body = _JS_COMMENT_RE.sub("", body)
            # Remove Django template expressions next so their quoted
            # arguments (e.g. {% trans "..." %} inside a JS string) are not
            # mistaken for standalone literal text.
            body = _JS_DJANGO_TAG_RE.sub("", body)

            for match in _JS_STRING_RE.finditer(body):
                literal = match.group(2)
                if _is_user_visible_js_string(literal):
                    violations.append(
                        f"{rel_path}:"
                        f" hardcoded user-visible JS string literal: "
                        f"{match.group(0)!r}"
                    )

    assert not violations, (
        "Potentially untranslated user-visible text in inline JS:\n"
        + "\n".join(violations)
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


# Locale-aware filter names — expressions using any of these already produce
# locale-correct output and must NOT be flagged by the raw-attribute-access scan.
_LOCALE_AWARE_FILTERS = (
    "get_title",
    "get_name",
    "get_category_name",
    "get_city_name",
    "get_lookup_name",
)


def test_no_raw_get_name_in_templates() -> None:
    """Templates must use ``|get_title:LANGUAGE_CODE``,
    ``|get_category_name:LANGUAGE_CODE``, ``|get_city_name:LANGUAGE_CODE``,
    or ``|get_lookup_name:LANGUAGE_CODE`` filters instead of raw
    ``{{ obj.get_name }}`` calls or raw ``.title``/``.name`` attribute access,
    which render in the default language regardless of the active UI locale.

    Exclusions (legitimate raw access that must NOT be flagged):
    - ``language.name_local`` — Django's language name (``\\b`` guard ensures
      ``.name`` does not match ``.name_local``).
    - Expressions already using a locale-aware filter (``|get_title`` etc.).
    - ``value="…"`` form-input attributes that round-trip to the base model
      field (e.g. ``<input value="{{ ad.title }}">`` writes back to ``ad.title``).
    """
    violations: list[str] = []

    for tpl_path in _collect_template_files():
        content = tpl_path.read_text(encoding="utf-8")
        rel_path = str(tpl_path.relative_to(settings.BASE_DIR))

        # 1. Raw .get_name() method calls — should use the |get_name filter.
        for match in re.findall(r"\{\{[^}]*\.get_name[^}]*\}\}", content):
            violations.append(
                f"{rel_path}: raw .get_name() call — use |get_name:LANGUAGE_CODE "
                f"filter instead: {match}"
            )

        # 2. Collect spans of value="..." / value='...' attributes so that
        #    form inputs (which round-trip to the base model field) are
        #    excluded from the attribute-access scan below.
        form_value_spans = [
            (m.start(), m.end())
            for m in re.finditer(
                r"""value=(["'])[^"']*\{\{[^}]*\}\}[^"']*\1""", content
            )
        ]

        # 3. Scan each {{ }} expression for raw .title / .name access.
        for m in re.finditer(r"\{\{[^}]*\}\}", content):
            expr = m.group(0)

            # Skip {{ }} inside a value="..."/"value='...'" form input.
            pos = m.start()
            if any(start <= pos < end for start, end in form_value_spans):
                continue

            # Skip expressions already using a locale-aware filter.
            if any(f in expr for f in _LOCALE_AWARE_FILTERS):
                continue

            if re.search(r"\.title\b", expr):
                violations.append(
                    f"{rel_path}: raw .title attribute access — use "
                    f"|get_title:LANGUAGE_CODE filter instead: "
                    f"{expr.strip()}"
                )

            if re.search(r"\.name\b", expr):
                violations.append(
                    f"{rel_path}: raw .name attribute access — use "
                    f"|get_category_name:LANGUAGE_CODE / "
                    f"|get_city_name:LANGUAGE_CODE / "
                    f"|get_lookup_name:LANGUAGE_CODE filter instead: "
                    f"{expr.strip()}"
                )

    assert not violations, (
        "Templates contain raw .get_name() calls or raw .title/.name "
        "attribute access that bypass locale-aware filters:\n"
        + "\n".join(violations)
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


def test_hreflang_present() -> None:
    """Every page template renders a ``<link rel="alternate" hreflang>`` link
    for every configured language (I18N-004).

    The alternates live in the shared ``components/locale_head.html`` partial
    (Option B), included by every page template.  Rendering the partial
    confirms one ``hreflang`` alternate per language is emitted for each
    available language.
    """
    request = RequestFactory().get("/")
    rendered = get_template("components/locale_head.html").render({"request": request})
    expected_langs = {code for code, _ in settings.LANGUAGES}
    found_langs = {
        lang for lang in expected_langs if f'hreflang="{lang}"' in rendered
    }
    missing = expected_langs - found_langs
    assert not missing, f"Missing hreflang tags for languages: {sorted(missing)}"

    # Spec §5f: ``x-default`` is intentionally excluded — every
    # ``<link rel="alternate">`` must map to a concrete content language
    # rather than a generic fallback.
    assert 'hreflang="x-default"' not in rendered, (
        "x-default hreflang must not be rendered (spec §5f: concrete language only)"
    )


# ---------------------------------------------------------------------------
# Page <title> localization (I18N-003)
# ---------------------------------------------------------------------------

_TITLE_TAG_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.DOTALL | re.IGNORECASE)

# Page templates whose <title> carries {% trans %}-wrapped text.  Under an
# empty Context({}) the list.html title resolves to its {% trans "Ads" %}
# branch (the query/category conditions are falsy).
_TITLE_TEMPLATES = (
    ("ads/list.html", "Ads", "Объявления", "Oglasi"),
    ("ads/dashboard.html", "Dashboard", "Панель управления", "Ploča"),
    ("ads/edit.html", "Edit Ad", "Редактировать объявление", "Uredi oglas"),
)


def _template_source(template_name: str) -> str:
    """Return the raw source of a template located in a configured DIR."""
    for tpl_cfg in settings.TEMPLATES:
        for d in tpl_cfg.get("DIRS", []):
            candidate = Path(d) / template_name
            if candidate.exists():
                return candidate.read_text(encoding="utf-8")
    pytest.fail(f"template not found in TEMPLATES DIRs: {template_name}")


def test_title_tags_translated() -> None:
    """Each page <title> localizes to the active UI locale (I18N-003).

    Extracts the ``<title>...</title>`` fragment from selected page templates,
    renders it under ``translation.override()`` with an empty ``Context({})``
    (matching the locale-switch test pattern), and asserts the rendered title
    differs per language — proving the ``{% trans %}`` msgids resolve through
    the active catalogue rather than a single hardcoded string.
    """
    for template_name, en_title, ru_title, bs_title in _TITLE_TEMPLATES:
        source = _template_source(template_name)
        titled = _TITLE_TAG_RE.search(source)
        assert titled, f"{template_name}: no <title> tag found"
        title_content = titled.group(1).strip()
        tpl = Template("{% load i18n %}" + title_content)

        rendered: dict[str, str] = {}
        for lang, expected in (("en", en_title), ("ru", ru_title), ("bs", bs_title)):
            with translation.override(lang):
                rendered[lang] = tpl.render(Context({}))
            assert expected in rendered[lang], (
                f"{template_name} [{lang}]: expected {expected!r} in "
                f"rendered title {rendered[lang]!r}"
            )

        assert len({rendered["en"], rendered["ru"], rendered["bs"]}) == 3, (
            f"{template_name}: <title> did not differ across en/ru/bs — "
            f"en={rendered['en']!r} ru={rendered['ru']!r} bs={rendered['bs']!r}"
        )


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


# ---------------------------------------------------------------------------
# Runtime plural-form selection (I18N-003)
# ---------------------------------------------------------------------------

# msgstr values read from each locale's django.po for the msgid
# "%(counter)s view" / "%(counter)s views" (sourced from ads/dashboard.html:95).
# en has an empty msgstr, so the msgid is used as the translation.
_EXPECTED_PLURALS = {
    "en": {1: "1 view", 2: "2 views", 5: "5 views"},
    "ru": {1: "1 просмотр", 2: "2 просмотра", 5: "5 просмотров"},
    "bs": {1: "1 pregled", 2: "2 pregleda", 5: "5 pregleda"},
}


def test_plural_forms_runtime() -> None:
    """``{% blocktrans count %}`` selects the correct plural form at runtime.

    Uses the live msgid from ``ads/dashboard.html:95`` (``"{{ counter }} view"``
    / ``"{{ counter }} views"``) and asserts the exact rendered output for
    n=1/2/5 in each locale, proving the CLDR plural index is recomputed per
    count rather than always picking form[0].
    """
    tpl = Template(
        "{% load i18n %}"
        "{% blocktrans count counter=count %}{{ counter }} view"
        "{% plural %}{{ counter }} views{% endblocktrans %}"
    )
    for lang, expected_by_n in _EXPECTED_PLURALS.items():
        rendered: dict[int, str] = {}
        for n in (1, 2, 5):
            with translation.override(lang):
                rendered[n] = tpl.render(Context({"count": n}))
            assert rendered[n] == expected_by_n[n], (
                f"{lang}: n={n} expected {expected_by_n[n]!r}, "
                f"got {rendered[n]!r}"
            )

        # Runtime plural-form selection proofs.
        assert rendered[1] != rendered[2], (
            f"{lang}: singular/plural not distinguished "
            f"(n=1={rendered[1]!r}, n=2={rendered[2]!r})"
        )
        if lang in ("ru", "bs"):
            # 3-form languages: n=2 (form[1]) and n=5 (form[2]) must differ.
            assert rendered[2] != rendered[5], (
                f"{lang}: plural form[1] and form[2] collapsed "
                f"(n=2={rendered[2]!r}, n=5={rendered[5]!r})"
            )
        else:
            # en: both n=2 and n=5 use the plural ("views") form.
            assert "views" in rendered[2] and "views" in rendered[5], (
                f"{lang}: plural form not selected for n=2/5"
            )


def test_all_languages_ltr() -> None:
    """Every configured language must be LTR (left-to-right).

    Guards the I18N-006 invariant: the spec's claim that Bosnian renders
    ``dir="rtl"`` is incorrect — Django's ``LANGUAGE_BIDI`` is ``False`` for
    ru, bs, and en, so the ``{{ LANGUAGE_BIDI|yesno:"rtl,ltr" }}`` template
    expression renders ``ltr`` for all three.  Activating each locale via
    ``translation.override`` and asserting ``get_language_bidi()`` is ``False``
    documents and enforces the LTR-only invariant at runtime.
    """
    lang_codes = [code for code, _ in settings.LANGUAGES]
    assert lang_codes == ["ru", "bs", "en"], (
        f"unexpected LANGUAGES: {lang_codes}"
    )
    for lang in lang_codes:
        with translation.override(lang):
            assert not translation.get_language_bidi(), (
                f"{lang}: expected LTR (LANGUAGE_BIDI=False)"
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

    # Per the empty-msgstr convention the English catalogue falls back to the
    # msgid, so "Dashboard" renders verbatim under the active en locale.
    with translation.override("en"):
        rendered = tpl.render(Context({}))
    assert "Dashboard" in rendered


# ---------------------------------------------------------------------------
# Part C — bot handler i18n gate tests
# ---------------------------------------------------------------------------

# Bot-handler methods whose first positional arg or ``text`` keyword carries
# user-visible text that must be wrapped in ``gettext`` (``_``).
_BOT_USER_FACING_METHODS = frozenset({
    "answer", "reply", "edit_text", "edit_caption", "send_message",
})

# Method names that accept a ``text`` keyword carrying user-visible text.
_BOT_KEYWORD_TEXT_METHODS = frozenset({"button"})

# Token set for strings that are intentionally left un-translated.
# Reuses the same set as above.
_NON_TRANSLATABLE = frozenset({"EUR", "RSD", "BAM"})


def _collect_bot_handler_files() -> list[Path]:
    """Return every ``*.py`` file under ``src/telegram_bot/handlers/``."""
    handlers_dir = settings.BASE_DIR / "telegram_bot" / "handlers"
    return sorted(handlers_dir.rglob("*.py"))


def _is_gettext_wrapped(node: ast.AST) -> bool:
    """Return True if *node* is a ``_()`` call wrapping a string."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_"
        and len(node.args) >= 1
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    )


def _is_translatable_text(value: str) -> bool:
    """Skip strings with no words (emoji-only) or known non-translatable tokens."""
    cleaned = re.sub(r"\W+", "", value, flags=re.UNICODE)
    if not cleaned:
        return False
    return cleaned.upper() not in _NON_TRANSLATABLE


def _find_untranslated(node: ast.AST) -> bool:
    """Return True if *node* is a bare string constant that should be wrapped."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return _is_translatable_text(node.value)
    # f-strings — also user-visible but not wrapped in gettext
    if isinstance(node, ast.JoinedStr):
        return True
    return False


def _check_call_for_unwrapped(call: ast.Call, source: str, lineno: int) -> list[str]:
    """Inspect a single Call node for an unwrapped user-facing string."""
    violations: list[str] = []
    func = call.func

    # message.answer("text") — first positional arg
    if (
        isinstance(func, ast.Attribute)
        and func.attr in _BOT_USER_FACING_METHODS
        and call.args
    ):
        arg = call.args[0]
        if _find_untranslated(arg) and not _is_gettext_wrapped(arg):
            violations.append(
                f"{source}:{lineno}: unwrapped user-facing string passed to "
                f".{func.attr}() — wrap in _()"
            )

    # builder.button(text="text") — text keyword arg
    if isinstance(func, ast.Attribute) and func.attr in _BOT_KEYWORD_TEXT_METHODS:
        for kw in call.keywords:
            if kw.arg == "text" and _find_untranslated(kw.value) and not _is_gettext_wrapped(kw.value):
                violations.append(
                    f"{source}:{lineno}: unwrapped button text — wrap in _()"
                )

    return violations


def test_bot_no_hardcoded_messages() -> None:
    """Bot handler user-facing strings must be wrapped in ``gettext``.

    AST-scans every ``.py`` file under ``telegram_bot/handlers/`` for calls to
    user-facing Bot/API methods (``answer``, ``reply``, ``edit_text``,
    ``edit_caption``, ``send_message``, ``KeyboardBuilder.button``) whose text
    argument is a bare string constant or f-string rather than a ``_()`` call.
    """
    all_violations: list[str] = []

    for py_file in _collect_bot_handler_files():
        source = str(py_file.relative_to(settings.BASE_DIR))
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=source)

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                all_violations.extend(
                    _check_call_for_unwrapped(node, source, node.lineno)
                )

    assert not all_violations, (
        "Unwrapped user-facing strings in bot handlers:\n"
        + "\n".join(all_violations)
    )


def test_no_cyrillic_msgids() -> None:
    """No ``msgid`` in any ``.po`` file may contain Cyrillic characters.

    Russian-as-msgid is forbidden — msgids must be English (project rule #16,
    spec I18N-004).  ``msgstr`` values for ru/bs are naturally Cyrillic and
    exempt.
    """
    cyrillic_re = re.compile(r"[\u0400-\u04FF]")

    for po_path in _po_files():
        text = po_path.read_text(encoding="utf-8")
        for msgid, _ in _parse_po_entries(text):
            if msgid and cyrillic_re.search(msgid):
                rel = po_path.relative_to(settings.BASE_DIR)
                pytest.fail(
                    f"{rel}: msgid contains Cyrillic (Russian-as-msgid): "
                    f"{msgid[:80]!r}"
                )


# ---------------------------------------------------------------------------
# I18N-001 gate: bot handlers/services must not bypass get_name/get_title
# ---------------------------------------------------------------------------

# Variable names that are NOT Django model instances — ``.name``/``.title``
# on these objects (e.g. ``message.from_user.name``) is legitimate and must
# not be flagged.
_ALLOWED_NAME_VARS = frozenset({
    "message",
    "callback",
    "request",
    "user",
    "data",
    "state",
    "payload",
})

# Model attribute names that carry user-visible text and must go through
# the locale-aware accessor (``get_name`` / ``get_title``) instead of raw
# field access.
_RAW_FIELD_ATTRS = frozenset({"name", "title", "description"})


def _collect_bot_source_files() -> list[Path]:
    """Return every ``*.py`` file under ``telegram_bot/handlers/`` and
    ``telegram_bot/services/``.
    """
    base = settings.BASE_DIR / "telegram_bot"
    files: list[Path] = []
    for sub in ("handlers", "services"):
        files.extend(sorted((base / sub).rglob("*.py")))
    return files


def _root_name(node: ast.AST) -> str | None:
    """Extract the root variable name from an attribute-access chain.

    e.g. ``message.from_user.name`` -> ``"message"``
         ``cat.name``            -> ``"cat"``
    """
    while isinstance(node, ast.Attribute):
        node = node.value
    if isinstance(node, ast.Name):
        return node.id
    return None


def _is_name_i18n_get_call(node: ast.AST) -> bool:
    """Return True for ``<obj>.name_i18n.get('<string_literal>', ...)``."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr != "get":
        return False
    if not isinstance(func.value, ast.Attribute) or func.value.attr != "name_i18n":
        return False
    if (
        node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    ):
        return True
    return False


def _is_raw_field_access(node: ast.AST) -> bool:
    """Return True for ``.name``, ``.title``, or ``.description`` on a likely
    model variable.

    Allows method-call results (``get_name``, ``get_title``, ``get_description``)
    by virtue of those having different ``attr`` values.
    Allows ``<allowed_var>.name`` via the variable-name heuristic.
    """
    if not isinstance(node, ast.Attribute) or node.attr not in _RAW_FIELD_ATTRS:
        return False
    root = _root_name(node)
    if root in _ALLOWED_NAME_VARS:
        return False
    return True


def _scan_bot_source_for_violations(source: str, tree: ast.Module) -> list[str]:
    """Collect all I18N-001 violations in a single parsed file."""
    violations: list[str] = []

    for node in ast.walk(tree):
        # 1. name_i18n.get("<string_literal>", ...) — hardcoded locale
        if _is_name_i18n_get_call(node):
            violations.append(
                f"{source}:{node.lineno}: hardcoded locale in name_i18n.get() "
                f"— use get_name(locale) instead"
            )

        # 2a. .name / .title inside an f-string FormattedValue
        if isinstance(node, ast.FormattedValue):
            if _is_raw_field_access(node.value):
                violations.append(
                    f"{source}:{node.lineno}: raw .name/.title field access "
                    f"in f-string — use get_name(locale)/get_title(locale)"
                )

        # 2b. .name / .title as a dict value in "% (...)" formatting
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
            if isinstance(node.right, ast.Dict):
                for value in node.right.values:
                    if _is_raw_field_access(value):
                        violations.append(
                            f"{source}:{value.lineno}: raw .name/.title "
                            f"field access in % dict value — use "
                            f"get_name(locale)/get_title(locale)"
                        )

        # 2c. .name / .title as the element of a list comprehension
        if isinstance(node, ast.ListComp):
            if _is_raw_field_access(node.elt):
                violations.append(
                    f"{source}:{node.lineno}: raw .name/.title field access "
                    f"in list comprehension — use get_name(locale)/"
                    f"get_title(locale)"
                )

        # 2d. .name / .title / .description as a keyword-argument value
        if isinstance(node, ast.keyword):
            if _is_raw_field_access(node.value):
                violations.append(
                    f"{source}:{node.value.lineno}: raw .{node.value.attr} field "
                    f"access as keyword argument — use "
                    f"get_name(get_language())/get_title(get_language())/"
                    f"get_description(get_language())"
                )

    return violations


def test_bot_no_raw_model_field_access() -> None:
    """Bot handlers and services must not bypass ``get_name``/``get_title``.

    AST-scans every ``.py`` file under ``telegram_bot/handlers/`` and
    ``telegram_bot/services/`` for:

    1. ``name_i18n.get("<literal>")`` calls — a hardcoded locale bypasses
       the active user locale.
    2. ``.name`` / ``.title`` / ``.description`` attribute access on model
       objects inside: f-string ``{…}`` segments, ``%`` dict values, list
       comprehensions, and keyword-argument values.

    Allowed patterns:
    - ``get_name(...)``, ``get_title(...)``, ``get_description(...)`` calls
    - ``.slug`` attribute access (legitimate)
    - ``.name``/``.title``/``.description`` on variables named ``message``,
      ``callback``, ``request``, ``user``, ``data``, ``state``, ``payload``
      (non-model objects; ``payload`` is a Pydantic DTO in ad_create/text.py)
    """
    all_violations: list[str] = []

    for py_file in _collect_bot_source_files():
        source = str(py_file.relative_to(settings.BASE_DIR))
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=source)
        all_violations.extend(_scan_bot_source_for_violations(source, tree))

    assert not all_violations, (
        "Raw model field access in bot handlers/services:\n"
        + "\n".join(all_violations)
    )
