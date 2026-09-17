"""
Template tags for Telegram deep-link rendering (Contact-Us anti-spam, CR-2/CR-6/CR-7).

Provides the ``{% telegram_deep_link %}`` tag, which emits an obfuscated
Telegram deep-link: the real ``t.me/<username>`` URL is never present in the
static HTML ``href``. Instead the bot username (admin-editable via SiteConfig)
is base64-encoded in a ``data-*`` attribute and assembled at click time by an
inline ``<script>`` IIFE that targets its preceding anchor via
``document.currentScript.previousElementSibling`` (mirroring
``components/favorite_heart.html``).

Also provides the ``|rtl_obfuscate`` filter for displaying the bot username as
inline text in a way that is visually readable but resistant to naive scraping.
The filter reverses the string and inserts Unicode Right-to-Left Mark characters
between each character; paired with the ``.bot-username-rtl`` CSS class
(``direction: rtl; unicode-bidi: bidi-override``), the browser flips the
reversed text back to its correct visual order, while scrapers reading the raw
HTML get a reversed, mark-streaked string instead of the clean username.

Templates must never reference ``settings.BOT_USERNAME`` or a bare
``{{ bot_username }}`` context variable — use this tag or filter instead.

The ``{% telegram_deep_link %}`` tag always renders the full interactive link
(with ``data-*`` attributes and click-handler IIFE) regardless of the
``js_verified`` context flag. The obfuscation layer (base64-encoded username,
click-time URL assembly, no cleartext ``t.me/<username>`` in the HTML) provides
scrape resistance. The ``js_verified`` flag is used separately by the footer's
cookie-setting script to prove JS execution for subsequent requests.
"""

from __future__ import annotations

import base64
import logging
from enum import StrEnum
from typing import Final, cast

from django import template
from django.utils.functional import Promise
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from apps.core.services.site_config import get_bot_username

register = template.Library()
logger = logging.getLogger(__name__)

# Unicode Right-to-Left Mark (U+200F) — invisible in LTR contexts, used to
# break up contiguous text runs so scrapers cannot trivially extract the
# bot username from rendered HTML text content.
_RTL_MARK: Final[str] = "\u200f"


class TelegramDeepLinkCommand(StrEnum):
    """Telegram deep-link ``start`` payloads (CR-2)."""

    CONTACT = "contact"
    CONTACT_US = "contact_us"
    CREATE_AD = "create_ad"
    LOGIN = "login"


# Visible label + aria-label (translatable; extracted by makemessages).
_LABELS: dict[TelegramDeepLinkCommand, str | Promise] = {
    TelegramDeepLinkCommand.CONTACT: _("Contact Seller"),
    TelegramDeepLinkCommand.CONTACT_US: _("Contact us"),
    TelegramDeepLinkCommand.CREATE_AD: _("Submit an ad"),
    TelegramDeepLinkCommand.LOGIN: _("Login via Telegram"),
}

# Commands that consume one positional argument (ad.id / raw_token).
_HAS_ARG: frozenset[TelegramDeepLinkCommand] = frozenset(
    {
        TelegramDeepLinkCommand.CONTACT,
        TelegramDeepLinkCommand.LOGIN,
    }
)

# Static inline-JS click handler (no untrusted data interpolated — safe to
# mark safe). Mirrors the per-component IIFE in components/favorite_heart.html.
_JS_IIFE: Final[str] = (
    '<script>(function() { "use strict";'
    "var el = document.currentScript.previousElementSibling;"
    "if (!el) return;"
    "el.addEventListener('click', function(e) {"
    "e.preventDefault();"
    "var username = atob(el.dataset.botEncoded);"
    "var url = 'https://t.me/' + username + '?start=' + encodeURIComponent(el.dataset.start);"
    "if (el.target === '_blank') { window.open(url, '_blank', 'noopener,noreferrer'); } else { window.location.href = url; }"
    "});"
    "})();</script>"
)


@register.simple_tag(takes_context=True)
def telegram_deep_link(
    context: template.Context,
    command: str,
    *args: str,
    classes: str = "",
    target: str = "",
) -> str:
    """Render an obfuscated Telegram deep-link.

    Usage::

        {% telegram_deep_link "create_ad" classes="..." %}
        {% telegram_deep_link "create_ad" classes="..." target="_blank" %}
        {% telegram_deep_link "contact" ad.id classes="..." %}
        {% telegram_deep_link "contact_us" classes="..." %}
        {% telegram_deep_link "login" raw_token classes="..." %}

    The real ``t.me/<username>`` URL is assembled in the browser from a
    base64-encoded username (``data-bot-encoded``) and a server-controlled
    ``start`` payload (``data-start``); neither the username nor the cleartext
    URL appears in the static ``href``. The inline ``<script>`` IIFE attaches a
    click handler that assembles the URL at click time, so real browsers always
    get a working link on first visit.

    The ``js_verified`` context flag (set by ``JSExecutionMiddleware``) is no
    longer used to gate the link itself — the obfuscation layer (base64-encoded
    username, no cleartext URL, click-time assembly) already resists scrapers.
    The flag remains available for the cookie-setting script in the footer
    template, which proves JS execution for subsequent requests.

    Args:
        context: Template context (``takes_context=True`` — ``js_verified`` is
            accepted but no longer gates the link output).
        command: One of ``TelegramDeepLinkCommand`` values.
        *args: Optional payload argument (ad.id for ``contact``, raw_token
            for ``login``).
        classes: Extra utility classes to append to ``js-telegram-link``.
            The tag displays a translatable label (e.g., "Contact us"), not the
            bot username, so no CSS ``direction: rtl`` class is applied.
        target: HTML ``target`` attribute value (e.g. ``_blank``). When set,
            the inline JS IIFE opens the deep-link via ``window.open(url, '_blank',
            'noopener,noreferrer')`` instead of ``window.location.href`` (CR-8).

    Returns:
        An HTML-escaped ``<a>`` with ``data-*`` attributes plus an inline
        ``<script>`` IIFE click handler. The ``href`` is always ``#`` (never
        a cleartext Telegram URL).
    """
    try:
        cmd = TelegramDeepLinkCommand(command)
    except ValueError:
        logger.warning("telegram_deep_link: unknown command %r", command)
        return ""

    label = str(_LABELS[cmd])

    # Assemble the Telegram start payload.
    if cmd in _HAS_ARG:
        arg = args[0] if args else ""
        data_start = f"{cmd}_{arg}"
    else:
        data_start = cmd.value

    # No bot-username-rtl class: the visible text is the translatable label,
    # not the bot username (which is base64-encoded in data-bot-encoded).
    class_attr = f"js-telegram-link {classes}".strip()
    encoded = base64.b64encode(get_bot_username().encode("utf-8")).decode("ascii")
    target_attr = mark_safe(f' target="{target}"') if target else ""

    return cast(
        str,
        format_html(
            '<a href="#"{} data-bot-encoded="{}" data-start="{}" class="{}" aria-label="{}">{}</a>{}',
            target_attr,
            encoded,
            data_start,
            class_attr,
            label,
            label,
            mark_safe(_JS_IIFE),
        ),
    )


@register.filter(name="rtl_obfuscate")
def rtl_obfuscate(value: str) -> str:
    """Reverse the string and insert RTL marks to resist scraper extraction.

    Applied to the bot username when displayed as inline text (e.g., in the
    privacy page footer links or the ``<code>`` legal disclosure). The technique
    is two-layered:

    1. **String reversal** (``value[::-1]``) — the reversed string lives in the
       HTML text node. Paired with the ``.bot-username-rtl`` CSS class
       (``direction: rtl; unicode-bidi: bidi-override``), the browser flips it
       back to correct visual order, so human readers see ``bazuna_bot`` even
       though the HTML source contains ``tob_anuzab``.
    2. **RTL Mark insertion** — ``_RTL_MARK`` (U+200F) is joined between each
       reversed character. The mark is invisible in an LTR context but breaks up
       the contiguous text run, so a simple ``response.content.decode().find()``
       or ``textContent`` scrape encounters the reversed, mark-streaked string
       instead of the clean username.

    The ``sr-only`` Tailwind utility is paired on an adjacent ``<span>``
    containing the clean username for screen-reader accessibility.

    Args:
        value: The bot username string to obfuscate.

    Returns:
        The reversed string with ``_RTL_MARK`` inserted between each character.
    """
    if not value:
        return ""
    return _RTL_MARK.join(value[::-1])
