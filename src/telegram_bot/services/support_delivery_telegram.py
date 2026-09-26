"""
Telegram delivery service for support tickets.

DMs each active TELEGRAM-type ``SupportContact`` with a support-ticket
notification when a seller submits a support message. EMAIL-type contacts are
skipped (handled by ``support_delivery_email``).

Delivery is per-contact isolated: one blocked, offline, or rate-limited contact
never stops delivery to the others. A Telegram 429 (``TelegramRetryAfter``) is
handled locally by sleeping the mandated ``retry_after`` and retrying once, so
a flood-controlled outbound call is not silently dropped.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter
from django.utils.translation import gettext as _

from apps.core.enums import SupportChannelType

if TYPE_CHECKING:
    from apps.core.models import SupportContact, SupportTicket

logger = logging.getLogger(__name__)


async def send_support_notification_telegram(
    ticket: SupportTicket,
    bot: Bot,
    active_contacts: list[SupportContact],
) -> None:
    """Deliver a support-ticket notification to every active TELEGRAM contact.

    Iterates ``active_contacts``, skipping any whose ``channel_type`` is not
    ``SupportChannelType.TELEGRAM``, and sends a DM to each via ``bot``.
    Failures are isolated per contact: a raised exception (including a 429 that
    exceeds its single retry) is logged and delivery continues to the next
    contact. Never propagates an error so the caller's dialog is not disrupted.

    Args:
        ticket: The ``SupportTicket`` that triggered the notification.
        bot: The aiogram ``Bot`` used for outbound ``send_message`` calls.
        active_contacts: The active support contacts (EMAIL and TELEGRAM); only
            TELEGRAM-type contacts are messaged.
    """
    # 1. Extract ticket fields up front so the message is built from plain
    #    locals, keeping model-field access out of the user-facing string
    #    interpolation (i18n AST gate).
    ticket_ref = ticket.ticket_ref
    telegram_id = ticket.telegram_id
    username = ticket.username or ""
    text = ticket.text

    message = _(
        "New support ticket %(ref)s\n"
        "From: telegram_id=%(tid)s username=%(username)s\n"
        "\n%(text)s"
    ) % {
        "ref": ticket_ref,
        "tid": telegram_id,
        "username": username,
        "text": text,
    }

    # 2. Deliver to each active TELEGRAM contact, isolated per recipient so a
    #    single failure never stops delivery to the rest.
    for contact in active_contacts:
        if contact.channel_type != SupportChannelType.TELEGRAM:
            continue
        try:
            await bot.send_message(chat_id=contact.telegram_id, text=message)
        except TelegramRetryAfter as exc:
            # 429 flood control — sleep the mandated wait, then retry once.
            await asyncio.sleep(exc.retry_after)
            try:
                await bot.send_message(chat_id=contact.telegram_id, text=message)
            except Exception:
                logger.exception(
                    "Failed to DM support contact %s", contact.label
                )
        except Exception:
            logger.exception("Failed to DM support contact %s", contact.label)
            continue
