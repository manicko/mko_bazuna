"""
Tests for the i18n pipeline and the ``component_tag`` template filter (Spec_29 T-13).

Covers two concerns:
  A. ``.po`` files have every ``msgstr`` filled (no empty translations remain)
     and compiled ``.mo`` files exist (compilemessages ran successfully).
  B. The ``component_tag`` template filter renders a feature tag span with the
     lookup item's localized name and ``data-feature-id`` attribute.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from django import template
from django.conf import settings
from django.template import Context

from apps.lookups.models import LookupItem


pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_po_entries(text: str) -> list[tuple[str, str]]:
    """Parse ``.po`` text into ``(msgid, msgstr)`` tuples.

    Handles multi-line quoted strings and skips the header entry (empty
    ``msgid``).
    """
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
