"""
Tests for the i18n pipeline and the ``component_tag`` template filter (Spec_29 T-13).

Covers two concerns:
  A. ``.po`` files have every ``msgstr`` filled (no empty translations remain)
     and compiled ``.mo`` files exist (compilemessages ran successfully).
  B. The ``component_tag`` template filter renders a feature tag span with the
     lookup item's localized name and ``data-feature-id`` attribute.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from django import template
from django.conf import settings
from django.template import Context

from apps.lookups.models import LookupItem
from testing.i18n_helpers import _parse_po_entries

pytestmark = [pytest.mark.unit]


def _po_files() -> list[Path]:
    """Return every ``django.po`` under the configured ``LOCALE_PATHS``."""
    paths: list[Path] = []
    for base in settings.LOCALE_PATHS:
        paths.extend(sorted(Path(str(base)).rglob("django.po")))
    return paths


# ---------------------------------------------------------------------------
# Part A — i18n pipeline
# ---------------------------------------------------------------------------


def test_po_files_exist_for_all_languages() -> None:
    """A ``django.po`` exists for every configured language."""
    configured = {code for code, _ in settings.LANGUAGES}
    on_disk = {p.parent.parent.name for p in _po_files()}
    missing = configured - on_disk
    assert not missing, f"Missing .po files for languages: {missing}"


def test_no_empty_msgstr() -> None:
    """Every non-header ``msgid`` has a non-empty ``msgstr``.

    The ``en`` locale is exempt — its ``msgid`` is already English, so
    ``msgstr`` may remain empty.
    """
    for po_path in _po_files():
        locale_code = po_path.parent.parent.name
        text = po_path.read_text(encoding="utf-8")
        entries = _parse_po_entries(text)
        empty = [
            msgid
            for msgid, msgstr_forms in entries
            if msgid and any(not form.strip() for form in msgstr_forms)
        ]
        if locale_code == "en":
            continue
        assert not empty, f"{po_path}: empty msgstr for msgids: {empty}"


def test_parse_po_entries_reports_blank_non_final_form() -> None:
    """A blank non-final ``msgstr[N]`` form is reported as a violation.

    Uses a synthetic plural entry (never a catalogue) whose ``msgstr[0]`` is
    blank while ``msgstr[1]`` is filled.  Before the parser kept every form,
    only the last one survived, so this blank form was invisible.
    """
    sample = (
        'msgid "%(counter)s view"\n'
        'msgid_plural "%(counter)s views"\n'
        'msgstr[0] ""\n'
        'msgstr[1] "%(counter)s views filled"\n'
    )
    entries = _parse_po_entries(sample)

    forms_by_msgid = {msgid: forms for msgid, forms in entries if msgid}
    assert forms_by_msgid["%(counter)s view"] == ["", "%(counter)s views filled"], (
        "parser must carry every msgstr form in order"
    )

    empty = [
        msgid
        for msgid, msgstr_forms in entries
        if msgid and any(not form.strip() for form in msgstr_forms)
    ]
    assert empty == ["%(counter)s view", "%(counter)s views"], (
        f"blank msgstr[0] not reported: {empty!r}"
    )


def test_mo_files_exist() -> None:
    """Compiled ``.mo`` files exist for every ``.po`` (compilemessages ran).

    The test entrypoint runs ``compilemessages`` before pytest, so ``.mo``
    files are guaranteed to be present.  This test guards against accidental
    deletion or misnamed ``.mo`` files that would break ``{% trans %}`` at
    runtime.
    """
    for po_path in _po_files():
        mo_path = po_path.with_suffix(".mo")
        assert mo_path.exists(), f"Missing compiled file: {mo_path}"


def test_pot_creation_date_sync() -> None:
    """All three ``.po`` files must share the same ``POT-Creation-Date``.

    ``makemessages`` runs with all locale flags in a single invocation
    (Makefile line 176-177), so a fresh extraction produces a single
    timestamp.
    """
    dates: dict[str, str] = {}
    for po_path in _po_files():
        text = po_path.read_text(encoding="utf-8")
        match = re.search(r'"POT-Creation-Date:\s*(.+?)\\n"', text, re.DOTALL)
        assert match, f"{po_path}: no POT-Creation-Date header found"
        dates[po_path.parent.parent.name] = match.group(1).strip()
    unique_dates = set(dates.values())
    assert len(unique_dates) == 1, f"POT-Creation-Date mismatch: {dates}"


# ---------------------------------------------------------------------------
# BLOCK 11 (14-I18N-014, N-2) — obsolete-symmetry assertion
# ---------------------------------------------------------------------------
# BLOCK 10 resolved the obsolete dimension once (a one-shot prune); this is the
# durable gate. It asserts ZERO ``#~`` obsolete blocks in EVERY catalogue — the
# post-prune invariant across all three. It reads the obsolete dimension ONLY:
# per BC-3 it must not require an obsolete ``msgstr`` to be non-empty (the ``en``
# obsolete entry shipped with an empty ``msgstr`` legitimately, as every ``en``
# entry does), so no msgstr content is inspected.

# ``#~ msgid `` is the exact form xgettext/msgattrib emit for an obsolete singular
# entry; it anchors the obsolete count without matching active ``msgid`` lines.
_OBSOLETE_MSGID_RE = re.compile(r"^#~ msgid ", re.MULTILINE)


def _obsolete_msgid_count(text: str) -> int:
    """Return the number of ``#~ msgid `` obsolete blocks in *text*.

    Reads the obsolete dimension only — the ``msgstr`` content of an obsolete
    entry is never inspected (BC-3).
    """
    return len(_OBSOLETE_MSGID_RE.findall(text))


def test_no_obsolete_entries_in_any_catalogue() -> None:
    """No catalogue carries a ``#~`` obsolete block (BLOCK 11, 14-I18N-014).

    Durable form of BLOCK 10's prune. The assertion covers ALL THREE catalogues:
    the asymmetry (``ru``/``bs`` at 7, ``en`` at 1 pre-prune) *is* the finding,
    and gating only two locales would let ``en`` drift the other way. The
    post-prune target is zero in every catalogue; ``7/7/1`` justified the block
    but is not the invariant asserted. No count is hard-coded.
    """
    for po_path in _po_files():
        lang = po_path.parent.parent.name
        text = po_path.read_text(encoding="utf-8")
        count = _obsolete_msgid_count(text)
        assert count == 0, (
            f"{lang}/django.po: {count} obsolete '#~ msgid' block(s) — a fresh "
            f"extraction must leave every catalogue obsolete-free"
        )


def test_obsolete_count_helper_flags_a_synthetic_block_per_locale() -> None:
    """A synthetic ``#~`` block fires :func:`_obsolete_msgid_count` for ru/bs/en.

    Proves the guard fails for a ``#~`` block in EACH of the three locales, not
    only the two that carried seven pre-prune (BC-3: proving it only on
    ``ru``/``bs`` demonstrates the half that was already true). The helper reads
    the obsolete dimension only — the entry's empty ``msgstr`` is irrelevant.
    """
    obsolete_entry = (
        "#: synthetic\n"
        "#~ msgid \"Withdrawn string\"\n"
        'msgstr ""\n'
    )
    for lang in ("ru", "bs", "en"):
        assert _obsolete_msgid_count(obsolete_entry) == 1, (
            f"a synthetic '#~' block must be counted for {lang}"
        )

    # A catalogue with no obsolete block reports zero.
    assert _obsolete_msgid_count('msgid "Active"\nmsgstr "Активно"\n') == 0


# ---------------------------------------------------------------------------
# Part B — component_tag Filter
# ---------------------------------------------------------------------------


def test_component_tag_renders_feature_name() -> None:
    """``component_tag`` outputs a span containing the localized name."""
    feature = LookupItem(
        slug="wifi",
        name_i18n={"ru": "Wi-Fi", "en": "Wi-Fi"},
    )
    tpl = template.Template("{% load global_tags %}{{ feature|component_tag }}")
    rendered = tpl.render(Context({"feature": feature}))
    assert "Wi-Fi" in rendered


def test_component_tag_includes_feature_id() -> None:
    """The rendered tag carries a ``data-feature-id`` attribute."""
    feature = LookupItem(
        slug="wifi",
        id=42,
        name_i18n={"ru": "Wi-Fi", "en": "Wi-Fi"},
    )
    tpl = template.Template("{% load global_tags %}{{ feature|component_tag }}")
    rendered = tpl.render(Context({"feature": feature}))
    assert 'data-feature-id="42"' in rendered
