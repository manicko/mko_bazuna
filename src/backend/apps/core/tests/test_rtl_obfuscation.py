"""
Tests for Spec 18 Block B — CSS ``direction: rtl`` + ``bot-username-rtl`` +
``rtl_obfuscate`` filter, and ``privacy.html`` display-text migration.

Block B implements the visible-display-text obfuscation layer:
- The ``rtl_obfuscate`` filter reverses the bot username string and inserts
  Unicode Right-to-Left Marks (U+200F) between characters. Paired with the
  ``.bot-username-rtl`` CSS class (``direction: rtl; unicode-bidi: bidi-override``),
  the browser flips the reversed text back to correct visual order, while scrapers
  reading the raw HTML encounter a reversed, mark-streaked string.
- The ``.bot-username-rtl`` CSS rule is defined in ``input.css`` (and compiled
  into ``output.css``).
- The ``telegram_deep_link`` tag must NOT apply ``bot-username-rtl`` to its
  class attribute — the tag's visible text is a translatable label (e.g.,
  "Contact us"), not the bot username.
- ``privacy.html`` display text (``@{{ bot_username }}`` spans and the ``<code>``
  legal disclosure) is migrated to use ``rtl_obfuscate`` + ``sr-only`` pairing
  for accessibility.

All tests are pure unit level — no database access required.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from django.conf import settings
from django.template import Context, Template

pytestmark = [pytest.mark.unit]

# Unicode Right-to-Left Mark (U+200F), mirrors _RTL_MARK in telegram_tags.py.
_RTL_MARK = "\u200f"

# Path to the privacy.html template source (mirrors test_footer_contact_link.py).
_PRIVACY_PATH: Path = Path(settings.TEMPLATES[0]["DIRS"][0]) / "privacy.html"

# Paths to the Tailwind v4 CSS source and compiled output.
_INPUT_CSS_PATH: Path = (
    settings.BASE_DIR / "theme" / "static" / "theme" / "css" / "input.css"
)
_OUTPUT_CSS_PATH: Path = (
    settings.BASE_DIR / "theme" / "static" / "theme" / "css" / "output.css"
)


# ---------------------------------------------------------------------------
# rtl_obfuscate filter
# ---------------------------------------------------------------------------


def test_rtl_obfuscate_reverses_string_and_inserts_rtl_marks() -> None:
    """The filter reverses the string and inserts RLM marks between characters.

    For ``"bazuna_bot"`` the reversed form is ``"tob_anuzab"`` and joining
    with ``_RTL_MARK`` produces ``"t<RLM>o<RLM>b<RLM>_<RLM>...a<RLM>b"``.
    """
    from apps.core.templatetags.telegram_tags import rtl_obfuscate

    result = rtl_obfuscate("bazuna_bot")
    expected = _RTL_MARK.join("bazuna_bot"[::-1])
    assert result == expected


def test_rtl_obfuscate_reversed_character_order() -> None:
    """Characters appear in reversed order (before CSS flips them back).

    Splitting on the RLM mark yields the reversed string's characters.
    """
    from apps.core.templatetags.telegram_tags import rtl_obfuscate

    result = rtl_obfuscate("abc")
    chars = result.split(_RTL_MARK)
    assert chars == ["c", "b", "a"]


def test_rtl_obfuscate_contains_rtl_marks() -> None:
    """The output contains RLM marks for a multi-character input."""
    from apps.core.templatetags.telegram_tags import rtl_obfuscate

    result = rtl_obfuscate("bazuna_bot")
    assert _RTL_MARK in result
    # (len - 1) RLM marks for a string of len characters.
    assert result.count(_RTL_MARK) == len("bazuna_bot") - 1


def test_rtl_obfuscate_handles_empty_string() -> None:
    """An empty string returns empty (guarded before reversal)."""
    from apps.core.templatetags.telegram_tags import rtl_obfuscate

    assert rtl_obfuscate("") == ""


def test_rtl_obfuscate_via_template_engine() -> None:
    """The filter is usable in templates via ``{{ value|rtl_obfuscate }}``."""
    template = Template("{% load telegram_tags %}{{ bot_username|rtl_obfuscate }}")
    result = template.render(Context({"bot_username": "test_bot"}))
    assert result == _RTL_MARK.join("test_bot"[::-1])


def test_obfuscated_display_pattern_renders_correctly() -> None:
    """The full privacy.html display pattern (filter + CSS + sr-only) renders.

    Verifies that ``{{ bot_username|rtl_obfuscate }}`` inside a
    ``bot-username-rtl`` span produces the reversed+RLM string, and the
    adjacent ``sr-only`` span carries the clean username.
    """
    template = Template(
        "{% load telegram_tags %}"
        '@<span class="bot-username-rtl" aria-hidden="true">'
        "{{ bot_username|rtl_obfuscate }}</span>"
        '<span class="sr-only">{{ bot_username }}</span>'
    )
    result = template.render(Context({"bot_username": "test_bot"}))
    # Visible span: reversed + RLM (not the clean username)
    assert 'class="bot-username-rtl" aria-hidden="true"' in result
    # sr-only span: clean username for screen readers
    assert 'class="sr-only">test_bot</span>' in result
    # The reversed+RLM content is inside the visible span
    assert _RTL_MARK.join("test_bot"[::-1]) in result


# ---------------------------------------------------------------------------
# telegram_deep_link tag: bot-username-rtl must NOT be in class_attr
# ---------------------------------------------------------------------------


def _render_tag(
    command: str,
    *,
    classes: str = "",
    target: str = "",
    js_verified: bool = True,  # Kept for API compatibility; no longer affects output.
) -> str:
    """Render ``{% telegram_deep_link <command> %}`` with a mocked bot username.

    Args:
        command: The deep-link command (``contact_us``, ``create_ad``, etc.).
        classes: Extra utility classes to pass as the ``classes`` kwarg.
        target: Optional HTML ``target`` attribute value (e.g. ``_blank``).
        js_verified: Deprecated — the tag always renders the full interactive
            link regardless of this flag (kept only for call-site compatibility).

    Returns:
        The rendered HTML string.
    """
    with patch(
        "apps.core.templatetags.telegram_tags.get_bot_username",
        return_value="test_bot",
    ):
        template_str = (
            "{% load telegram_tags %}{% telegram_deep_link command classes=classes"
        )
        if target:
            template_str += " target=target"
        template_str += " %}"
        template = Template(template_str)
        context_dict: dict = {
            "command": command,
            "classes": classes,
        }
        if target:
            context_dict["target"] = target
        # js_verified is passed but no longer gates the tag output.
        context_dict["js_verified"] = js_verified
        return template.render(Context(context_dict))


def test_telegram_deep_link_omits_bot_username_rtl_class() -> None:
    """The ``contact_us`` deep-link tag must NOT emit ``bot-username-rtl``.

    The tag's visible ``<a>`` text is a translatable label ("Contact us"), not
    the bot username. Applying ``direction: rtl`` to the label would reverse it
    and break the UI. The username is base64-encoded in ``data-bot-encoded``.
    """
    html = _render_tag("contact_us")
    assert "bot-username-rtl" not in html


def test_telegram_deep_link_keeps_js_telegram_link_class() -> None:
    """The link anchor retains ``js-telegram-link`` (without the removed class)."""
    html = _render_tag("contact_us", classes="underline")
    assert 'class="js-telegram-link underline"' in html


def test_telegram_deep_link_degraded_omits_bot_username_rtl() -> None:
    """The link never emits ``bot-username-rtl`` — visible text is a label, not username.

    Even when ``js_verified=False`` (legacy degradation path), the tag renders
    the full interactive link with ``data-*`` attributes and the IIFE click
    handler. The obfuscation layer (base64-encoded username, no cleartext URL)
    provides scrape resistance regardless of the ``js_verified`` flag.
    """
    html = _render_tag("contact_us", js_verified=False)
    assert "bot-username-rtl" not in html


def test_telegram_deep_link_create_ad_omits_bot_username_rtl() -> None:
    """The ``create_ad`` deep-link tag also omits ``bot-username-rtl``."""
    html = _render_tag("create_ad")
    assert "bot-username-rtl" not in html


# ---------------------------------------------------------------------------
# CSS rule existence checks
# ---------------------------------------------------------------------------


def test_bot_username_rtl_css_rule_in_input_css() -> None:
    """``.bot-username-rtl`` with ``direction: rtl`` is defined in input.css."""
    content = _INPUT_CSS_PATH.read_text(encoding="utf-8")
    assert ".bot-username-rtl" in content
    assert "direction: rtl" in content
    assert "unicode-bidi: bidi-override" in content


def test_bot_username_rtl_css_rule_in_output_css() -> None:
    """The compiled ``output.css`` exists, is non-empty, and contains the selector.

    ``output.css`` is a minified Tailwind build whose exact property formatting
    (e.g. ``direction:rtl`` vs ``direction: rtl``) is toolchain-dependent and
    must not be asserted on.  We verify the file exists, is non-empty, and
    contains the ``.bot-username-rtl`` selector; the stable ``input.css``
    source assertions (see ``test_bot_username_rtl_css_rule_in_input_css``)
    carry the structural intent.
    """
    assert _OUTPUT_CSS_PATH.is_file(), "output.css must exist"
    content = _OUTPUT_CSS_PATH.read_text(encoding="utf-8")
    assert content.strip(), "output.css must not be empty"
    assert ".bot-username-rtl" in content


# ---------------------------------------------------------------------------
# privacy.html source-level checks
# ---------------------------------------------------------------------------


def test_privacy_html_loads_telegram_tags() -> None:
    """``privacy.html`` loads the ``telegram_tags`` library."""
    source = _PRIVACY_PATH.read_text(encoding="utf-8")
    assert "{% load telegram_tags %}" in source


def test_privacy_html_applies_rtl_obfuscate() -> None:
    """Display text in ``privacy.html`` uses the ``rtl_obfuscate`` filter."""
    source = _PRIVACY_PATH.read_text(encoding="utf-8")
    assert "rtl_obfuscate" in source


def test_privacy_html_uses_bot_username_rtl_class() -> None:
    """Display text spans in ``privacy.html`` use ``bot-username-rtl``."""
    source = _PRIVACY_PATH.read_text(encoding="utf-8")
    assert 'class="bot-username-rtl"' in source


def test_privacy_html_has_sr_only_pairing() -> None:
    """Every ``bot-username-rtl`` span is paired with an ``sr-only`` span."""
    source = _PRIVACY_PATH.read_text(encoding="utf-8")
    rtl_count = source.count('bot-username-rtl" aria-hidden="true"')
    sr_count = source.count("sr-only")
    # After Block C migration: only the L111 code-block disclosure remains
    # (the two display-link occurrences at L31 and L149 are replaced by the
    # telegram_deep_link tag, which does not emit bot-username-rtl/sr-only).
    assert rtl_count == 1  # L111 code only
    assert sr_count >= rtl_count  # at least one sr-only per obfuscated span


def test_privacy_html_no_bare_display_username() -> None:
    """No visible ``@{{ bot_username }}`` display text remains unobfuscated.

    All ``@{{ bot_username }}`` display occurrences are replaced by the
    ``{% telegram_deep_link %}`` tag. The only remaining ``bot_username``
    usage is the ``sr-only`` span in the L111 code-block disclosure (which
    is intentionally accessible to screen readers).
    """
    source = _PRIVACY_PATH.read_text(encoding="utf-8")
    # No bare "@{{ bot_username }}" display text — must be "@<span..." instead.
    assert "@{{ bot_username }}" not in source


# ---------------------------------------------------------------------------
# telegram_deep_link tag: target parameter
# ---------------------------------------------------------------------------


def test_telegram_deep_link_target_blank_emits_target_attr() -> None:
    """Tag with ``target="_blank"`` emits the ``target`` attribute on the ``<a>``."""
    html = _render_tag("contact_us", target="_blank")
    assert 'target="_blank"' in html


def test_telegram_deep_link_without_target_omits_target_attr() -> None:
    """Tag without ``target`` does NOT emit a ``target`` attribute."""
    html = _render_tag("contact_us")
    assert "target=" not in html


def test_telegram_deep_link_target_blank_degraded_emits_target_attr() -> None:
    """The link with ``js_verified=False`` still emits ``target`` and full markup.

    The tag always renders the complete interactive link (with click handler)
    regardless of ``js_verified`` — the flag no longer gates link functionality.
    """
    html = _render_tag("contact_us", target="_blank", js_verified=False)
    assert 'target="_blank"' in html
    # Full markup is always present even when js_verified=False
    assert "data-bot-encoded" in html
    assert "data-start" in html


def test_telegram_deep_link_target_blank_emits_window_open_in_iife() -> None:
    """The IIFE checks ``el.target === '_blank'`` and uses ``window.open``."""
    from apps.core.templatetags.telegram_tags import _JS_IIFE

    html = _render_tag("create_ad", target="_blank")
    # The IIFE is present in the rendered output.
    assert "window.open" in html
    assert "el.target === '_blank'" in html
    # Double-check the source constant too.
    assert "window.open" in _JS_IIFE
    assert "el.target === '_blank'" in _JS_IIFE


def test_telegram_deep_link_without_target_uses_location_href_in_iife() -> None:
    """Without ``target``, the IIFE falls back to ``window.location.href``."""
    from apps.core.templatetags.telegram_tags import _JS_IIFE

    html = _render_tag("contact_us")
    assert "window.location.href" in html
    assert "window.open" in _JS_IIFE  # IIFE constant is the same regardless of target
