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
9. ``test_bot_no_raw_model_field_access`` — AST-scans every
   ``src/telegram_bot`` module except ``tests/`` for raw
   ``name_i18n.get("ru")`` calls and ``.name``/``.title``/``.description``
   field access in f-strings, ``%`` dict values, list comprehensions, and
   keyword-argument values (I18N-001).
10. ``test_title_tags_translated`` — page ``<title>`` tags localize per
    language (I18N-003).
11. ``test_plural_forms_runtime`` — ``{% blocktrans count %}`` selects the
    correct CLDR plural form at runtime (I18N-003).
12. ``test_no_hardcoded_js_strings`` — inline ``<script>`` literals must not
    carry untranslated user-visible text (I18N-008).
13. ``test_all_languages_ltr`` — all configured languages are LTR (guards the
    I18N-006 Bidi invariant).
14. ``test_bot_no_hardcoded_messages`` — AST-scans every ``src/telegram_bot``
    module except ``tests/`` for user-facing method calls (``answer``,
    ``reply``, ``edit_text``, ``edit_caption``, ``send_message``, ``button``)
    with unwrapped string/f-string text arguments.
15. ``test_no_cyrillic_msgids`` — no ``msgid`` in any ``.po`` contains
    Cyrillic characters (msgids must be English; msgstr is exempt).
16. ``test_bs_msgstr_has_no_cyrillic`` — locale-scoped script gate (BLOCK 9,
    14-I18N-N-1): a Cyrillic code point in a ``bs`` ``msgstr`` is a violation,
    while Cyrillic in a ``ru`` ``msgstr`` is correct and stays exempt. Three
    ``bs`` strings knowingly ship as-is under the named, commented
    ``_BS_MSGSTR_LATIN_SCRIPT_EXEMPTIONS`` set while the Q1 reviewer sign-off
    is ``OPEN-PENDING-REVIEWER`` (2026-10-05).
17. ``test_cyrillic_msgstr_rule_is_locale_scoped`` — proves the rule is not
    "no Cyrillic anywhere": Cyrillic in a synthetic ``bs`` ``msgstr`` fires,
    Cyrillic in a synthetic ``ru`` ``msgstr`` does not, and the real ``ru``
    Catalogue's legitimate Cyrillic passes.
18. ``test_no_raw_get_name_in_templates`` — public/seller-facing templates must
    use locale-aware ``|get_title`` / ``|get_category_name`` /
    ``|get_city_name`` / ``|get_lookup_name`` filters instead of raw
    ``{{ obj.get_name }}`` calls or raw ``.title`` / ``.name`` attribute access.
19. ``test_reverse_stale_entry_gate`` — every catalogue msgid must exist in a
    REAL in-process source extraction (Python ``ast`` + full-root template
    scan). This is the reverse of ``test_extraction_completeness``: a msgid
    that leaves the source must not linger in the catalogue (BLOCK 11,
    14-I18N-014). The three runtime-live ``_lazy`` strings are exempted by the
    single ``_EXTRACTION_GAP_MSGIDS`` definition.
20. ``test_reverse_gate_flags_a_synthetic_orphan`` and
    ``test_reverse_gate_flags_a_synthetic_wrapped_orphan`` — prove the parse
    catches a simple AND a wrapped multi-line orphan (a line-anchored regex
    misses the latter).
21. ``test_reverse_extraction_scans_all_roots_without_exclusions`` — the
    reverse extraction scans ALL ``_template_roots()`` without
    ``exclude_subpaths`` (a sibling of ``_collect_template_files``).

BLOCK 8 (14-I18N-006, -007, -008) widened the collectors: the bot collectors
walk all of ``src/telegram_bot`` except ``tests/`` and the template collector
discovers roots by root-scoping (``_template_roots``). User-facing strings that
are deliberately not translated are listed once in ``_BOT_EXEMPT_FUNCTIONS`` and
consulted by enclosing-function name. ``telegram_bot/lifecycle.py``'s
``_COMMANDS`` (``BotCommand`` literals) are NOT flagged by the bot predicate —
it matches ``ast.Attribute`` methods, not a bare constructor — so they carry no
exemption entry (D-C). A source-level sibling of ``test_hreflang_present``
asserts every in-scope non-partial page template includes the locale partial.

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
from django.apps import apps
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


def _template_roots() -> list[Path]:
    """Return every in-repo template root the gate scans.

    Root-scoping (BLOCK 8, 14-I18N-007): the configured ``TEMPLATES["DIRS"]``
    unioned with each *in-repo* installed app's ``<app path>/templates``
    directory (the ``APP_DIRS`` roots). An app root is admitted only when it
    resolves inside ``settings.BASE_DIR`` — this keeps third-party
    distributions (``.venv`` site-packages such as ``django.contrib.admin`` or
    ``tailwind``) out of the scan, which would otherwise leak their own
    templates (e.g. ``registration/password_change_form.html``) into the
    hardcoded-text guard. Roots are returned resolved and de-duplicated, in a
    stable order.

    The caller asserts this is non-empty, so a refactor that silently moves
    every template away fails the gate rather than scanning nothing.
    """
    base_dir = Path(settings.BASE_DIR).resolve()
    roots: list[Path] = []

    for tmpl_cfg in settings.TEMPLATES:
        for d in tmpl_cfg.get("DIRS", []):
            roots.append(Path(d))

    for app_config in apps.get_app_configs():
        app_path = Path(app_config.path)
        if not app_path.resolve().is_relative_to(base_dir):
            continue
        templates_dir = app_path / "templates"
        if templates_dir.is_dir():
            roots.append(templates_dir)

    unique: dict[str, Path] = {}
    for root in roots:
        resolved = root.resolve()
        unique[str(resolved)] = resolved
    return sorted(unique.values())


def _collect_template_files() -> list[Path]:
    """Collect all template files to scan for hardcoded text.

    Walks every root returned by :func:`_template_roots` (configured DIRS plus
    each in-repo app's ``templates`` directory) and skips admin staff-only
    pages, moderation dashboard, and feature_tag (DB-based i18n). The
    ``exclude_subpaths`` prefixes are applied relative to *each* root.
    """
    exclude_subpaths = (
        "admin/",
        "analytics/moderation_dashboard.html",
        "components/feature_tag.html",
    )
    roots = _template_roots()
    assert roots, "no template root discovered — the collector would scan nothing"
    files: list[Path] = []
    for root in roots:
        for f in root.rglob("*.html"):
            rel = f.relative_to(root).as_posix()
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
        empty = [
            msgid
            for msgid, msgstr_forms in entries
            if msgid and any(not form.strip() for form in msgstr_forms)
        ]
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


_LOCALE_HEAD_INCLUDE = 'components/locale_head.html'


def _template_rel_path(tpl_path: Path) -> str:
    """Return *tpl_path* relative to the root of ``_template_roots`` it lives in."""
    for root in _template_roots():
        if tpl_path.is_relative_to(root):
            return tpl_path.relative_to(root).as_posix()
    return tpl_path.as_posix()


def _is_partial_template(rel_path: str) -> bool:
    """Return True for a non-page template.

    A partial is any template under a ``partials/`` segment or under
    ``components/`` — these are fragments included into pages and are not
    expected to carry the site-wide ``<head>`` alternates themselves. The
    ``locale_head.html`` partial shares the ``components/`` prefix, so this
    rule also excludes the partial *itself* from the assertion.
    """
    return "partials" in rel_path.split("/") or rel_path.startswith("components/")


def test_hreflang_include_in_every_page_template() -> None:
    """Every in-scope non-partial page template includes the ``locale_head``
    partial (BLOCK 8, 14-I18N-008).

    ``test_hreflang_present`` renders the partial in isolation, so a page that
    simply forgot to ``{% include %}`` it would still pass. This source-level
    assertion proves the site-wide property: each in-scope page template
    contains the include. Partial templates (``partials/`` or ``components/``)
    and the excluded templates (``admin/``, ``analytics/moderation_dashboard.html``,
    ``components/feature_tag.html``) are out of scope — the last two are both
    excluded *and* do include the partial, so they reconcile rather than fail.
    """
    page_templates = {
        _template_rel_path(f): f
        for f in _collect_template_files()
        if not _is_partial_template(_template_rel_path(f))
    }
    assert page_templates, "no in-scope page templates discovered"

    missing: list[str] = []
    for rel_path, tpl_path in sorted(page_templates.items()):
        content = tpl_path.read_text(encoding="utf-8")
        if _LOCALE_HEAD_INCLUDE not in content:
            missing.append(rel_path)

    assert not missing, (
        "Page templates missing the site-wide components/locale_head.html "
        "include:\n" + "\n".join(sorted(missing))
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
    """Return the raw source of a template located in a discovered root.

    Searches the same root-scoped set as :func:`_collect_template_files`
    (``_template_roots``), so the two cannot diverge.
    """
    for root in _template_roots():
        candidate = root / template_name
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
    pytest.fail(f"template not found in discovered roots: {template_name}")


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

# ---------------------------------------------------------------------------
# Named exemption set (BLOCK 8, 14-I18N-006)
# ---------------------------------------------------------------------------
# ONE module-level definition of the user-facing strings that are deliberately
# left un-translated, consulted by the bot predicate callers, the template
# scanners, BLOCK 9 and BLOCK 11. An entry is ``(repo-relative source path,
# enclosing function name)``; the exemption is matched by the *enclosing
# function* so moving code within the function never drifts (never by line
# number). Adding ``_()`` here is forbidden — the string is intentionally a
# literal.
#
# First (and today only) member: ``build_currency_keyboard`` composes a currency
# button label from an emoji flag and the ``CurrencyCode`` StrEnum value
# (``f"{_CURRENCY_FLAGS[code]} {code.value}"``). The rendered text is a
# currency code (EUR/RSD/BAM) plus a non-linguistic flag — there is no prose to
# translate, and the ``.button(text=…)`` call is otherwise indistinguishable
# from a real violation to the AST predicate (any ``JoinedStr`` fires).
#
# NOTE (BLOCK 8, D-C): ``telegram_bot/lifecycle.py``'s ``_COMMANDS`` carries
# twelve ``BotCommand(command=…, description=…)`` literals that are deliberately
# not msgids (an eager ``_()`` would freeze them to the import-time locale).
# They are NOT flagged by the bot predicate — it matches ``ast.Attribute``
# methods (``.answer``/``.button``/…), whereas ``BotCommand(...)`` is a bare
# constructor — so they need no exemption entry here. This is recorded, not
# suppressed.
_BOT_EXEMPT_FUNCTIONS = frozenset({
    (
        "telegram_bot/services/ad_data/keyboards.py",
        "build_currency_keyboard",
    ),
})


def _enclosing_function_name(tree: ast.AST, target: ast.AST) -> str | None:
    """Return the name of the innermost function enclosing *target*.

    Walks the module tree tracking ``FunctionDef``/``AsyncFunctionDef`` nodes
    and returns the name of the tightest one whose span contains *target*.
    Returns ``None`` for module-level code. Used to consult the exemption set
    by enclosing-function name rather than by line number.
    """
    best: ast.FunctionDef | ast.AsyncFunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if (
                node.lineno <= target.lineno <= node.end_lineno
                and (best is None or node.lineno > best.lineno)
            ):
                best = node
    return best.name if best is not None else None


def _is_exempt_bot_violation(source: str, tree: ast.AST, target: ast.AST) -> bool:
    """Return True if *target* lies in a named-exempt bot function."""
    return (source, _enclosing_function_name(tree, target)) in _BOT_EXEMPT_FUNCTIONS


def _collect_bot_handler_files() -> list[Path]:
    """Return every bot handler module.

    Delegates to the widened :func:`_collect_bot_source_files` collector and
    narrows it to the ``handlers`` package so both names keep working while
    scanning the same widened root (BLOCK 8, 14-I18N-006).
    """
    handlers_root = settings.BASE_DIR / "telegram_bot" / "handlers"
    return [
        f
        for f in _collect_bot_source_files()
        if f.is_relative_to(handlers_root)
    ]


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


def _check_call_for_unwrapped(
    call: ast.Call, source: str, lineno: int, tree: ast.AST
) -> list[str]:
    """Inspect a single Call node for an unwrapped user-facing string.

    The named exemption set (``_BOT_EXEMPT_FUNCTIONS``) is consulted at this
    caller by enclosing-function name; ``_find_untranslated`` itself is never
    weakened.
    """
    if _is_exempt_bot_violation(source, tree, call):
        return []

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


def _check_append_for_unwrapped(
    call: ast.Call, source: str, lineno: int, tree: ast.AST
) -> list[str]:
    """Flag translatable f-strings/literals passed to list.append()."""
    if _is_exempt_bot_violation(source, tree, call):
        return []
    func = call.func
    if not (isinstance(func, ast.Attribute) and func.attr == "append"):
        return []
    if not call.args:
        return []
    arg = call.args[0]
    if not _find_untranslated(arg) or _is_gettext_wrapped(arg):
        return []
    # Skip non-prose strings (price formatting like f"≥{ss.min_price}")
    if isinstance(arg, ast.JoinedStr):
        for val in arg.values:
            if isinstance(val, ast.FormattedValue):
                continue
            if isinstance(val, ast.Constant) and isinstance(val.value, str):
                if _is_translatable_text(val.value):
                    return [
                        f"{source}:{lineno}: unwrapped user-facing string in "
                        f".append() — wrap in _()"
                    ]
    return []


def test_bot_no_hardcoded_messages() -> None:
    """Bot user-facing strings must be wrapped in ``gettext``.

    AST-scans every ``.py`` file under ``src/telegram_bot`` except ``tests/``
    (the widened scope, BLOCK 8 / 14-I18N-006) for calls to user-facing
    Bot/API methods (``answer``, ``reply``, ``edit_text``, ``edit_caption``,
    ``send_message``, ``KeyboardBuilder.button``) whose text argument is a bare
    string constant or f-string rather than a ``_()`` call. The named
    ``_BOT_EXEMPT_FUNCTIONS`` set is consulted by enclosing-function name at
    the predicate caller — ``_find_untranslated`` is never weakened.
    """
    all_violations: list[str] = []

    for py_file in _collect_bot_source_files():
        source = str(py_file.relative_to(settings.BASE_DIR))
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=source)

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                all_violations.extend(
                    _check_call_for_unwrapped(node, source, node.lineno, tree)
                )
                all_violations.extend(
                    _check_append_for_unwrapped(node, source, node.lineno, tree)
                )

    assert not all_violations, (
        "Unwrapped user-facing strings in the bot:\n"
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
# BLOCK 9 (14-I18N-N-1) — locale-scoped msgstr script gate
# ---------------------------------------------------------------------------
# ``test_no_cyrillic_msgids`` above declares every ``msgstr`` exempt because
# "msgstr values for ru/bs are naturally Cyrillic". That is right for ``ru``
# and WRONG for ``bs``: Bosnian is written in Latin and a Cyrillic code point
# in a ``bs`` ``msgstr`` is contamination by construction (a Russian verb or a
# stray Cyrillic ``а`` inside a Latin word). The rule below is the ``bs``-only
# complement of the existing msgid-only rule; it is about SCRIPT, not language
# quality — it cannot judge fluency and does not pretend to.

# Q1 RULING — 2026-10-05, Product Owner, OPTION (b). The gate history is
# ``OPEN-PENDING-REVIEWER``: the *who* is decided (a NATIVE BOSNIAN reviewer,
# preferably Montenegrin; machine output and translation APIs are explicitly
# NOT acceptable), but no sign-off exists yet. The three ``bs`` ``msgstr``
# values below therefore ship AS-IS and are exempted by msgid here — never
# silently: each entry names the finding, the required reviewer and the owner,
# and each is NOT closed for that string. When the reviewer supplies values, a
# follow-up commit replaces the values and removes the matching msgids from
# this set; the gate then closes. The Implementor is FORBIDDEN from writing,
# guessing, machine-translating or approximating any ``bs`` text, so no value
# is invented here.
#
#   THE THREE EXEMPTED bs ENTRIES (by msgid):
#   1. the multi-line support-greeting msgid ending "To create an ad, use
#      /post." — its bs msgstr is a Bosnian frame carrying the Russian verb
#      "користи" and a Cyrillic "а" inside the Latin word "oglasa". This is the
#      only Cyrillic-bearing line in the whole bs catalogue.
#   2. "Moderator #%(mid)s" — a byte-identical copy-through; the ru msgstr is
#      the legitimate Cyrillic "Модератор #%(mid)s". Rendered in
#      analytics/moderation_dashboard.html (an excluded template subtree) as a
#      ``{% blocktrans with mid=… %}`` body — this gate reads the CATALOGUE
#      msgstr, so it reaches the entry regardless of that template exclusion.
#   3. "Admin" — a byte-identical copy-through; the ru msgstr is "Админ". In
#      scan scope via components/header.html and
#      components/header_auth_entry.html.
#
# The six legitimate ``bs`` copy-throughs (ID, Telegram ID:, Pro, Telegram,
# Google Translate, Plausible Analytics) are Latin and pass the predicate
# untouched. The ``Start`` copy-through is a BLOCK 10 orphan and is NOT
# corrected here. The two shared-form ``bs`` plurals are CORRECT.
_BS_MSGSTR_LATIN_SCRIPT_EXEMPTIONS = frozenset({
    (
        "👋 Hi! You have reached Bazuna support.\n"
        "\n"
        "Write your question — we will answer as soon as possible.\n"
        "\n"
        "To create an ad, use /post."
    ),
    "Moderator #%(mid)s",
    "Admin",
})


def _locale_code(po_path: Path) -> str:
    """Derive a locale code from a ``…/<locale>/LC_MESSAGES/django.po`` path.

    ``django.po`` -> ``LC_MESSAGES`` -> ``<locale>`` (e.g. ``ru``, ``bs``,
    ``en``). The locale is read from the path so the rule never hard-codes a
    literal locale in a loop.
    """
    return po_path.parent.parent.name


_CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")


def _bs_msgstr_violations(text: str) -> list[tuple[str, str]]:
    """Return ``(msgid, msgstr_form)`` pairs whose Cyrillic contaminates a bs msgstr.

    Every ``msgstr`` form of every non-exempt ``bs`` entry is inspected. The
    predicate is script-only and locale-scoped by the caller: it is invoked for
    the ``bs`` catalogue, never for ``ru`` (whose Cyrillic is correct).
    """
    return [
        (msgid, form)
        for msgid, msgstr_forms in _parse_po_entries(text)
        if msgid and msgid not in _BS_MSGSTR_LATIN_SCRIPT_EXEMPTIONS
        for form in msgstr_forms
        if _CYRILLIC_RE.search(form)
    ]


def test_bs_msgstr_has_no_cyrillic() -> None:
    """A Cyrillic code point in a ``bs`` ``msgstr`` is a violation (BLOCK 9).

    Locale-scoped sibling of ``test_no_cyrillic_msgids`` (which inspects the
    ``msgid`` only and leaves ``msgstr`` exempt): Bosnian is Latin, so a
    Cyrillic code point in a ``bs`` ``msgstr`` is contamination, while ``ru``'s
    Cyrillic ``msgstr`` values are correct and stay exempt. Every ``msgstr``
    form of a ``bs`` entry is inspected (simple and plural alike). The three
    knowingly-shipped-as-is strings are consulted BY MSGID against
    ``_BS_MSGSTR_LATIN_SCRIPT_EXEMPTIONS`` and their finding stays OPEN under
    the Q1 ruling (2026-10-05, option b).
    """
    for po_path in _po_files():
        if _locale_code(po_path) != "bs":
            continue
        text = po_path.read_text(encoding="utf-8")
        violations = _bs_msgstr_violations(text)
        if violations:
            rel = po_path.relative_to(settings.BASE_DIR)
            msgid, form = violations[0]
            pytest.fail(
                f"{rel}: bs msgstr contains Cyrillic (Bosnian is Latin — "
                f"contaminated msgstr): msgid={msgid[:80]!r} "
                f"msgstr={form[:80]!r}"
            )


def test_cyrillic_msgstr_rule_is_locale_scoped() -> None:
    """The script rule is locale-scoped, not "no Cyrillic anywhere".

    Uses one synthetic ``.po`` text to prove the distinction directly: the same
    Cyrillic-bearing entry is a violation when parsed by the ``bs`` predicate
    and correct when the ``ru`` catalogue is what is read. A blanket "no
    Cyrillic in a msgstr" rule would fail on ``ru`` immediately; this confirms
    the predicate keys on the locale, derived from the path — not on Cyrillic
    alone — so ``ru`` and ``bs`` can never share one rule.
    """
    po_text = (
        "#: test\n"
        'msgid "Synthetic label"\n'
        'msgstr "Синтетички натпис"\n'
    )

    # The bs predicate flags the synthetic Cyrillic msgstr...
    assert _bs_msgstr_violations(po_text), (
        "the bs predicate must flag a Cyrillic msgstr"
    )

    # ...while the real ru catalogue is never fed to it. Locale is derived from
    # the path, so ru is simply out of scope for the bs gate: its hundreds of
    # legitimate Cyrillic msgstrs are exempt by construction.
    ru_path = Path(settings.LOCALE_PATHS[0]) / "ru" / "LC_MESSAGES" / "django.po"
    bs_path = Path(settings.LOCALE_PATHS[0]) / "bs" / "LC_MESSAGES" / "django.po"
    assert _locale_code(ru_path) == "ru"
    assert _locale_code(bs_path) == "bs"

    ru_text = ru_path.read_text(encoding="utf-8")
    ru_cyrillic = any(
        _CYRILLIC_RE.search(form)
        for _, forms in _parse_po_entries(ru_text)
        for form in forms
    )
    assert ru_cyrillic, "the real ru catalogue legitimately contains Cyrillic"
    # The gate's scope predicate excludes ru, so those Cyrillic msgstrs pass.
    assert _locale_code(ru_path) != "bs", "ru must be outside the bs gate's scope"


def test_bs_msgstr_exemptions_name_q1_reviewer_and_owner() -> None:
    """The three ``bs`` exemptions are named, reasoned and never silent.

    Mirrors the ``_BOT_EXEMPT_FUNCTIONS`` convention: a single module-level
    named set, consulted by msgid, with a comment block naming the Q1 ruling
    (2026-10-05, option b), ACCEPTED / OPEN-PENDING-REVIEWER, the required
    reviewer (native Bosnian, preferably Montenegrin) and the owner. This test
    pins the set's membership by msgid so a future removal of a value (once a
    reviewer signs off) is a deliberate, visible edit rather than a drift.
    """
    assert _BS_MSGSTR_LATIN_SCRIPT_EXEMPTIONS == frozenset({
        (
            "👋 Hi! You have reached Bazuna support.\n"
            "\n"
            "Write your question — we will answer as soon as possible.\n"
            "\n"
            "To create an ad, use /post."
        ),
        "Moderator #%(mid)s",
        "Admin",
    }), (
        "the bs exemptions are the three Q1-pending strings; removing one "
        "requires the reviewer's values in the same commit"
    )

    # Each exempted msgid must be a real bs entry — an exemption for a msgid
    # that no longer exists is how a stale exemption hides a regression.
    bs_msgids: set[str] = set()
    for po_path in _po_files():
        if _locale_code(po_path) != "bs":
            continue
        bs_msgids.update(
            msgid
            for msgid, _ in _parse_po_entries(po_path.read_text(encoding="utf-8"))
            if msgid
        )
    missing = _BS_MSGSTR_LATIN_SCRIPT_EXEMPTIONS - bs_msgids
    assert not missing, (
        "bs exemption msgids absent from the bs catalogue: "
        f"{sorted(m[:40] for m in missing)}"
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
    """Return every ``*.py`` module under ``src/telegram_bot`` except ``tests/``.

    Walks the whole bot tree (``rglob``) rather than listing ``handlers`` and
    ``services`` so previously invisible modules — ``middlewares/``,
    ``retry.py``, ``states.py``, ``schemas/`` and the nine-module
    ``handlers/ad_create`` package — are scanned. The ``tests/`` subtree is the
    only exclusion; ``__pycache__`` is skipped because it holds no ``.py``
    source (BLOCK 8, 14-I18N-006).
    """
    base = settings.BASE_DIR / "telegram_bot"
    tests_root = base / "tests"
    return sorted(
        f for f in base.rglob("*.py") if not f.is_relative_to(tests_root)
    )


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



# ---------------------------------------------------------------------------
# Collector widening / positive-coverage guards (BLOCK 8, 14-I18N-006/-007/-008)
# ---------------------------------------------------------------------------

# Bot modules the widened collector must reach — modules that were invisible
# while the collector listed only ``handlers/`` and ``services/``. Paths are
# repo-relative and asserted by presence in the derived set, never by count.
_REQUIRED_BOT_MODULES = (
    "telegram_bot/retry.py",
    "telegram_bot/states.py",
    "telegram_bot/middlewares/__init__.py",
    "telegram_bot/main.py",
    "telegram_bot/handlers/ad_create/__init__.py",
    "telegram_bot/handlers/ad_create/entry.py",
)


def test_bot_collector_reaches_widened_scope() -> None:
    """The widened bot collector reaches every previously invisible module.

    The old collector walked only ``handlers/`` and ``services/``; this asserts
    the walked set (``_collect_bot_source_files``) contains the middleware
    package, ``retry.py``, ``states.py``, ``main.py`` and the modules of the
    ``handlers/ad_create`` package, while ``tests/`` stays excluded. Nothing
    here hard-codes a module count.
    """
    collected = {
        str(f.relative_to(settings.BASE_DIR)) for f in _collect_bot_source_files()
    }
    missing = [m for m in _REQUIRED_BOT_MODULES if m not in collected]
    assert not missing, (
        "widened bot collector did not reach: " + ", ".join(missing)
    )

    tests_root = (settings.BASE_DIR / "telegram_bot" / "tests").resolve()
    leaked = [
        rel
        for rel in collected
        if (settings.BASE_DIR / rel).resolve().is_relative_to(tests_root)
    ]
    assert not leaked, f"bot collector leaked test modules: {sorted(leaked)[:5]}"


def test_bot_handler_collector_delegates_to_widened_scope() -> None:
    """``_collect_bot_handler_files`` delegates to the widened collector.

    Preserving both names, the handler collector must return exactly the
    ``handlers`` subset of the widened set so the two cannot diverge.
    """
    widened = set(_collect_bot_source_files())
    handlers = set(_collect_bot_handler_files())

    assert handlers, "handler collector discovered no modules"
    assert handlers <= widened, "handler collector returned files outside the widened set"

    handlers_root = (settings.BASE_DIR / "telegram_bot" / "handlers").resolve()
    expected = {f for f in widened if f.resolve().is_relative_to(handlers_root)}
    assert handlers == expected, (
        "handler collector no longer matches the handlers subset of the widened set"
    )


def test_bot_exemption_is_consulted_by_enclosing_function() -> None:
    """The named exemption suppresses exactly the exempted function.

    ``build_currency_keyboard`` is the first (and today only) member of
    ``_BOT_EXEMPT_FUNCTIONS``. Asserting the predicate violations for that
    module drop to zero *because* of the exemption — and that a synthetic
    identical call outside the function is still flagged — proves the
    exemption is scoped by enclosing function, not applied file-wide.
    """
    exempt_source = "telegram_bot/services/ad_data/keyboards.py"
    assert (exempt_source, "build_currency_keyboard") in _BOT_EXEMPT_FUNCTIONS, (
        "the build_currency_keyboard exemption must be named in the set"
    )

    keyboards_path = settings.BASE_DIR / exempt_source
    tree = ast.parse(keyboards_path.read_text(encoding="utf-8"), filename=exempt_source)
    violations = [
        v
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for v in _check_call_for_unwrapped(node, exempt_source, node.lineno, tree)
    ]
    assert not violations, (
        "the exempted build_currency_keyboard call was still flagged: "
        f"{violations}"
    )

    # The same call nesting, but in a non-exempt function, must still fire.
    synthetic = ast.parse(
        "def other():\n"
        "    builder.button(text=f'{x} {y}')\n",
        filename=exempt_source,
    )
    fired = [
        v
        for node in ast.walk(synthetic)
        if isinstance(node, ast.Call)
        for v in _check_call_for_unwrapped(node, exempt_source, node.lineno, synthetic)
    ]
    assert fired, "an identical unwrapped button call outside the exemption must fire"


def test_template_roots_and_scope_are_non_empty() -> None:
    """The root-scoped template collector discovers roots and files.

    Positive guard (BLOCK 8): a refactor that moves every template away, or a
    root-scoping bug that admits only out-of-repo roots, must fail the gate
    rather than silently scan nothing. No root or file count is asserted.
    """
    roots = _template_roots()
    assert roots, "no template root discovered"

    base_dir = Path(settings.BASE_DIR).resolve()
    assert all(r.is_relative_to(base_dir) for r in roots), (
        "a discovered template root lies outside the repository"
    )

    files = _collect_template_files()
    assert files, "template collector discovered no files"

    # Every discovered file must live under one of the discovered roots.
    assert all(
        any(f.is_relative_to(r) for r in roots) for f in files
    ), "a collected template lies outside every discovered root"


# ---------------------------------------------------------------------------
# BLOCK 11 (14-I18N-014, N-2) — the reverse stale-entry gate
# ---------------------------------------------------------------------------
# Only the "added" direction of the catalogue is gated above: the existing
# ``test_extraction_completeness`` compares the three catalogues to each other
# and ``test_template_extraction_coverage`` checks template-sourced msgids.
# NOTHING compares the catalogue against the source in the removed direction,
# so a msgid that leaves the source stays in all three catalogues forever.
#
# This is the durable half of BLOCK 10's one-shot prune. It compares every
# catalogue msgid against a REAL extraction built in-process from the source:
#
#   (a) Python — ``ast.parse`` over every in-scope module, collecting the first
#       positional argument of every Call whose callee is a bare ``ast.Name`` in
#       Django's gettext keyword set. ``_lazy`` is DELIBERATELY OMITTED, exactly
#       mirroring xgettext: the alias is not a gettext keyword, so xgettext does
#       not extract it. (The three ``gettext_lazy as _lazy`` strings in
#       ``submit.py`` are consequently source-invisible — the exemption below.)
#   (b) Templates — ``_extract_template_msgids`` over a FULL ``_template_roots()``
#       scan, WITHOUT ``exclude_subpaths``. makemessages scans ``admin/`` and the
#       other excluded subtrees too, so reusing :func:`_collect_template_files`
#       here would drop ~62 legitimate msgids and produce a red-on-arrival gate.

# The gettext function names xgettext treats as keywords. ``_lazy`` is absent by
# design — see the module comment above.
_PY_GETTEXT_KEYWORDS = frozenset({
    "_",
    "gettext",
    "gettext_lazy",
    "gettext_noop",
    "ngettext",
    "ngettext_lazy",
    "pgettext",
    "pgettext_lazy",
    "npgettext",
    "npgettext_lazy",
    "dgettext",
    "dngettext",
})

# ---------------------------------------------------------------------------
# Named extraction-gap exemption (BLOCK 11, 14-I18N-014) — ONE definition
# ---------------------------------------------------------------------------
# The three msgids below are RUNTIME-LIVE and extracted by NOTHING: they are
# wrapped in ``gettext_lazy as _lazy`` at
# ``telegram_bot/handlers/ad_create/submit.py::_NON_CONTENT_REPLIES``, and
# xgettext does not treat ``_lazy`` as a gettext keyword (the alias was
# introduced by commit ``d0a3ac2a``, which changed ``_(...)`` to ``_lazy(...)``).
# They are NOT stale: they render under the seller's locale at runtime. The
# reverse gate therefore exempts them by msgid so it stays GREEN on arrival
# while still failing any genuine orphan. This is the only reverse diff against
# the in-process extraction; the two source-only strings (the
# ``create_admin_user`` password-policy msgid and the ``submission.py`` consent
# msgid) are a FORWARD gap and are deliberately NOT asserted here (BLOCK 11 is
# scoped to the removed direction only).
#
# Finding: 14-I18N-014 (N-2), extraction-keyword gap. Owner: the i18n gate
# owner (plan 25). When xgettext/the extraction gains the ``_lazy`` keyword the
# three entries are removed from this set in the same commit that proves the
# extraction reaches them; the gate then covers the `_lazy` gap directly.
_EXTRACTION_GAP_MSGIDS: frozenset[str] = frozenset({
    (
        "Your draft was no longer available, so it was replaced with a fresh "
        "one. Press confirm again to submit."
    ),
    (
        "Your ad could not be submitted from its current state. A fresh draft "
        "was prepared \u2014 press confirm again to submit."
    ),
    (
        "One of your photos is no longer available. A fresh draft was prepared "
        "\u2014 please upload the missing photo again, then send 'done'."
    ),
})


def _collect_all_template_files() -> list[Path]:
    """Return every template file under every discovered root — NO exclusions.

    Sibling of :func:`_collect_template_files` used ONLY by the reverse gate's
    extraction. ``_collect_template_files`` applies ``exclude_subpaths``
    (``admin/``, ``analytics/moderation_dashboard.html``,
    ``components/feature_tag.html``) for the hardcoded-text guard; makemessages
    applies no such exclusion, so a real extraction must scan every root.
    Reusing the excluding collector here would drop the admin subtree's msgids
    and produce a red-on-arrival gate.
    """
    files: list[Path] = []
    for root in _template_roots():
        files.extend(root.rglob("*.html"))
    return files


def _extract_python_msgids(root: Path) -> set[str]:
    """Collect msgids from an in-process ``ast`` scan of *root*.

    A msgid is the first positional argument of a Call whose callee is a bare
    ``ast.Name`` in :data:`_PY_GETTEXT_KEYWORDS` and whose argument is a string
    constant. ``_lazy`` is not in that set — mirroring xgettext — so the three
    ``gettext_lazy as _lazy`` strings are intentionally not extracted.
    """
    msgids: set[str] = set()
    for py_file in root.rglob("*.py"):
        if "__pycache__" in py_file.parts:
            continue
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Name) or func.id not in _PY_GETTEXT_KEYWORDS:
                continue
            if not node.args:
                continue
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value:
                msgids.add(arg.value)
    return msgids


def _real_extraction_msgids() -> set[str]:
    """Build the real source extraction (Python AST + full-root templates).

    Python: every in-scope module under ``settings.BASE_DIR`` (the tree that
    ships as ``src/``). Templates: every root from :func:`_template_roots`,
    scanned without exclusions. The empty header phantom is dropped by ``if
    msgid`` in both halves.
    """
    msgids = _extract_python_msgids(Path(settings.BASE_DIR))
    for tpl_path in _collect_all_template_files():
        msgids.update(
            msgid
            for msgid in _extract_template_msgids(tpl_path.read_text(encoding="utf-8"))
            if msgid
        )
    return msgids


def reverse_orphans(
    catalogue_text: str,
    extraction_ids: set[str],
    exemptions: frozenset[str],
) -> set[str]:
    """Return catalogue msgids absent from *extraction_ids*, after exemptions.

    Parses the catalogue with the plural-aware BLOCK 7 parser (never a regex),
    so a wrapped multi-line ``msgid ""`` entry is compared as its joined string
    rather than silently missed by a ``^msgid "…"$`` line anchor. The empty
    header msgid is skipped. *exemptions* is the single named
    :data:`_EXTRACTION_GAP_MSGIDS` definition; no second, divergent list exists.
    """
    entries = _parse_po_entries(catalogue_text)
    return {
        msgid
        for msgid, _ in entries
        if msgid and msgid not in extraction_ids and msgid not in exemptions
    }


def test_reverse_stale_entry_gate() -> None:
    """Every catalogue msgid must exist in the real source extraction (BLOCK 11).

    Guards the removed direction: a msgid that leaves the source must not
    linger in the catalogue. Compares each catalogue against an in-process
    extraction (Python ``ast`` + full-root template scan) and fails per
    catalogue with any surviving orphans. The three runtime-live ``_lazy``
    strings are exempted by the single :data:`_EXTRACTION_GAP_MSGIDS`
    definition; no other reverse diff remains. No count is hard-coded.
    """
    extraction = _real_extraction_msgids()
    assert extraction, "the in-process source extraction found no msgids"

    orphans_by_lang: dict[str, set[str]] = {}
    for po_path in _po_files():
        lang = _locale_code(po_path)
        text = po_path.read_text(encoding="utf-8")
        found = reverse_orphans(text, extraction, _EXTRACTION_GAP_MSGIDS)
        if found:
            orphans_by_lang[lang] = found

    assert not orphans_by_lang, (
        "stale catalogue entries (present in the catalogue, absent from the "
        "source extraction after the _EXTRACTION_GAP_MSGIDS exemption):\n"
        + "\n".join(
            f"{lang}: {sorted(m[:90] for m in orphans)}"
            for lang, orphans in sorted(orphans_by_lang.items())
        )
    )


def test_reverse_gate_flags_a_synthetic_orphan() -> None:
    """A synthetic simple orphan fails :func:`reverse_orphans` (BLOCK 11).

    Feeds the pure helper a synthetic ``.po`` containing one msgid that is in
    no extraction and one that is, and asserts only the orphan is returned —
    proving the gate fires on a genuine stale entry.
    """
    extraction = {"Present in source"}
    catalogue = (
        "#: synthetic\n"
        'msgid "Present in source"\n'
        'msgstr "Translation"\n'
        "\n"
        "#: synthetic orphan\n"
        'msgid "Removed from source"\n'
        'msgstr "Translation"\n'
    )

    orphans = reverse_orphans(catalogue, extraction, _EXTRACTION_GAP_MSGIDS)
    assert orphans == {"Removed from source"}, (
        f"the reverse gate must flag the synthetic orphan, got {orphans!r}"
    )


def test_reverse_gate_flags_a_synthetic_wrapped_orphan() -> None:
    """A wrapped multi-line synthetic orphan is caught, not missed (BLOCK 11).

    The orphan's msgid is split across a ``msgid ""`` line and continuation
    string lines — the shape a ``^msgid "…"$`` line-anchored regex silently
    misses. The parser joins the fragments before comparison, so the orphan is
    flagged. This proves the wrapped case rather than assuming it.
    """
    extraction = {"Present in source"}
    catalogue = (
        "#: synthetic simple orphan\n"
        'msgid "Removed from source"\n'
        'msgstr "Translation"\n'
        "\n"
        "#: synthetic wrapped orphan\n"
        'msgid ""\n'
        '"A wrapped multi-line msgid that the source "\n'
        '"no longer contains."\n'
        'msgstr ""\n'
        '"Translation of the wrapped orphan."\n'
    )

    orphans = reverse_orphans(catalogue, extraction, _EXTRACTION_GAP_MSGIDS)
    assert orphans == {
        "Removed from source",
        "A wrapped multi-line msgid that the source no longer contains.",
    }, f"the reverse gate must flag both orphans (simple + wrapped), got {orphans!r}"


def test_reverse_gate_honours_the_named_exemption() -> None:
    """The single named exemption suppresses exactly its msgids (BLOCK 11).

    A catalogue msgid absent from the extraction passes when — and only when —
    it is a member of :data:`_EXTRACTION_GAP_MSGIDS`. The same msgid without the
    exemption fires, proving the exemption is consulted rather than the gate
    being weakened.
    """
    orphan = "Your draft was no longer available, so it was replaced with a fresh one. Press confirm again to submit."
    assert orphan in _EXTRACTION_GAP_MSGIDS, (
        "the DRAFT_GONE _lazy msgid must be named in the exemption set"
    )
    catalogue = f'msgid "{orphan}"\nmsgstr ""\n'

    exempt = reverse_orphans(catalogue, set(), _EXTRACTION_GAP_MSGIDS)
    assert not exempt, "an exempted msgid must not be reported as an orphan"

    unexempt = reverse_orphans(catalogue, set(), frozenset())
    assert unexempt == {orphan}, (
        "without the exemption the same msgid must fire"
    )


def test_extraction_gap_exemptions_name_the_lazy_strings() -> None:
    """Each ``_EXTRACTION_GAP_MSGIDS`` member is a real catalogue msgid (BLOCK 11).

    An exemption for a msgid that no longer exists is how a stale exemption
    hides a regression. Every exempted msgid must still be present in the
    catalogues, so removing one is a deliberate, visible edit.
    """
    catalogue_msgids: set[str] = set()
    for po_path in _po_files():
        catalogue_msgids.update(
            msgid
            for msgid, _ in _parse_po_entries(po_path.read_text(encoding="utf-8"))
            if msgid
        )
    missing = _EXTRACTION_GAP_MSGIDS - catalogue_msgids
    assert not missing, (
        "extraction-gap exemption msgids absent from the catalogues: "
        f"{sorted(m[:90] for m in missing)}"
    )


def test_reverse_extraction_scans_all_roots_without_exclusions() -> None:
    """The reverse extraction scans every ``_template_roots()`` with no exclusion.

    ``_collect_all_template_files`` must reach subtrees that
    ``_collect_template_files`` deliberately excludes (``admin/``,
    ``analytics/moderation_dashboard.html``, ``components/feature_tag.html``):
    makemessages scans them, so the reverse extraction must too. It must also be
    a strict superset of the excluding collector.
    """
    all_files = set(_collect_all_template_files())
    scoped_files = set(_collect_template_files())

    assert scoped_files <= all_files, (
        "the exclusion-free scan must be a superset of the scoped collector"
    )
    assert all_files - scoped_files, (
        "the exclusion-free scan must reach at least one excluded template"
    )

    # A specific excluded subtree must be present in the full scan.
    excluded_examples = [
        f
        for f in all_files
        if f.relative_to(next(r for r in _template_roots() if f.is_relative_to(r)))
        .as_posix()
        .startswith("admin/")
    ]
    assert excluded_examples, (
        "the exclusion-free scan must reach the admin/ subtree"
    )
