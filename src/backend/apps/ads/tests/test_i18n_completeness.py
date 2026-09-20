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
   and ``.name``/``.title`` field access in f-strings, ``%`` dict values,
   and list comprehensions (I18N-001).

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
})

# Model attribute names that carry user-visible text and must go through
# the locale-aware accessor (``get_name`` / ``get_title``) instead of raw
# field access.
_RAW_FIELD_ATTRS = frozenset({"name", "title"})


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
    """Return True for ``.name`` or ``.title`` on a likely model variable.

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

    return violations


def test_bot_no_raw_model_field_access() -> None:
    """Bot handlers and services must not bypass ``get_name``/``get_title``.

    AST-scans every ``.py`` file under ``telegram_bot/handlers/`` and
    ``telegram_bot/services/`` for:

    1. ``name_i18n.get("<literal>")`` calls — a hardcoded locale bypasses
       the active user locale.
    2. ``.name`` / ``.title`` attribute access on model objects inside:
       f-string ``{…}`` segments, ``%`` dict values, and list comprehensions.

    Allowed patterns:
    - ``get_name(...)``, ``get_title(...)``, ``get_description(...)`` calls
    - ``.slug`` attribute access (legitimate)
    - ``.name``/``.title`` on variables named ``message``, ``callback``,
      ``request``, ``user``, ``data``, ``state`` (non-model objects)
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
