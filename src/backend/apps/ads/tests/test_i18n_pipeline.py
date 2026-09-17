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
        empty = [msgid for msgid, msgstr in entries if msgid and not msgstr.strip()]
        if locale_code == "en":
            continue
        assert not empty, f"{po_path}: empty msgstr for msgids: {empty}"


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
