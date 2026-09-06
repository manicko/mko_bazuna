"""
Tests for Spec 18 Block A — footer "Contact us" deep-link + JS-execution cookie.

CR-11 anti-scrape flow:
- The footer embeds an obfuscated "Contact us" deep-link via the
  ``{% telegram_deep_link "contact_us" %}`` tag (the real ``t.me/<bot>`` URL is
  never in the static HTML; the bot username is base64-encoded and assembled in
  the browser by an inline IIFE).
- The link is visible to *all* visitors regardless of consent/JS state — it is
  NOT wrapped in a ``{% if js_verified %}`` gate. When JS is not yet verified the
  tag degrades to an inert anchor (no ``data-*`` attributes, no script).
- A one-line inline ``<script>`` sets a ``js=true`` session cookie proving the
  browser executed JS. Non-JS clients never send it, so they never receive the
  full deep-link.

These are pure unit tests: the bot username is mocked and ``site_name`` is
supplied manually, so **no database access** is required.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from django.conf import settings
from django.template.loader import render_to_string

pytestmark = [pytest.mark.unit]

_FOOTER_PATH: Path = (
    Path(settings.TEMPLATES[0]["DIRS"][0]) / "components" / "footer.html"
)

# Canonical cookie assignment emitted by the footer's inline script.
_COOKIE_ASSIGNMENT = 'document.cookie = "js=true; SameSite=Lax; Secure; path=/"'


# ---------------------------------------------------------------------------
# Source-level structural checks (static template, no rendering)
# ---------------------------------------------------------------------------


def _footer_source() -> str:
    """Return the raw footer.html template source."""
    return _FOOTER_PATH.read_text(encoding="utf-8")


def _nav_block(source: str) -> str:
    """Extract the footer ``<nav>...</nav>`` block from the template source."""
    start = source.index("<nav")
    end = source.index("</nav>") + len("</nav>")
    return source[start:end]


def test_footer_loads_telegram_tags_library() -> None:
    """``{% load telegram_tags %}`` is present alongside ``{% load i18n %}``."""
    source = _footer_source()
    assert "{% load i18n %}" in source
    assert "{% load telegram_tags %}" in source


def test_footer_renders_contact_us_via_tag() -> None:
    """The "Contact us" link is produced by the ``contact_us`` deep-link tag."""
    assert '{% telegram_deep_link "contact_us"' in _footer_source()


def test_contact_link_sits_after_cookie_settings_before_nav_close() -> None:
    """The contact link follows "Cookie settings" and precedes ``</nav>``."""
    lines = _footer_source().splitlines()
    link_idx = next(
        i for i, line in enumerate(lines) if "{% telegram_deep_link" in line
    )
    prev = lines[link_idx - 1]
    assert "Cookie settings" in prev
    assert "</nav>" in lines[link_idx + 1]


def test_contact_link_not_gated_by_consent() -> None:
    """The contact link renders unconditionally — no ``{% if %}`` gate in nav."""
    nav = _nav_block(_footer_source())
    assert "{% if" not in nav
    assert "{% endif" not in nav
    assert '{% telegram_deep_link "contact_us"' in nav


def test_footer_sets_js_true_cookie() -> None:
    """The footer emits the ``js=true`` session cookie via an inline script."""
    source = _footer_source()
    assert _COOKIE_ASSIGNMENT in source
    # CR-11: the cookie setter is a single inline ``<script>`` (one line).
    cookie_lines = [ln for ln in source.splitlines() if "document.cookie" in ln]
    assert len(cookie_lines) == 1
    line = cookie_lines[0]
    assert "<script" in line
    assert "</script>" in line


# ---------------------------------------------------------------------------
# Rendered-output checks (bot username mocked; no database access)
# ---------------------------------------------------------------------------


def _render_footer(js_verified: bool) -> str:
    """Render the footer component with ``js_verified`` and a mocked bot."""
    with patch(
        "apps.core.templatetags.telegram_tags.get_bot_username",
        return_value="test_bot",
    ):
        return render_to_string(
            "components/footer.html",
            {"site_name": "TestSite", "js_verified": js_verified},
        )


def test_rendered_footer_contains_contact_link_markup() -> None:
    """Rendered footer has the obfuscated contact anchor (``js_verified=True``)."""
    html = _render_footer(js_verified=True)
    assert "js-telegram-link" in html
    assert "data-bot-encoded" in html
    assert "data-start" in html
    # Visible label + accessible label both say "Contact us".
    assert "Contact us" in html


def test_rendered_contact_link_uses_contact_us_payload() -> None:
    """``data-start`` carries the ``contact_us`` command (no ad-id argument)."""
    html = _render_footer(js_verified=True)
    assert 'data-start="contact_us"' in html


def test_rendered_footer_contains_js_cookie_script() -> None:
    """The ``js=true`` cookie-setting inline script is present in the output."""
    html = _render_footer(js_verified=True)
    assert _COOKIE_ASSIGNMENT in html
    assert "<script" in html


def test_contact_link_remains_visible_when_js_not_verified() -> None:
    """Link is visible but inert when ``js_verified`` is False (no consent gate).

    Per spec Block A the link is visible to ALL visitors regardless of consent
    state. With ``js_verified=False`` the tag degrades to a bare anchor (no
    ``data-bot-encoded``/``data-start``, no click-handler IIFE), while the
    static cookie script still runs to prove JS execution for a subsequent
    request.
    """
    html = _render_footer(js_verified=False)
    assert "js-telegram-link" in html
    assert "Contact us" in html
    # Degraded to inert: no obfuscated payload, no deep-link script.
    assert "data-bot-encoded" not in html
    assert "data-start" not in html
    # Cookie script is static HTML — present regardless of js_verified.
    assert _COOKIE_ASSIGNMENT in html
