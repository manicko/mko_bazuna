"""
Email delivery service for support tickets.

Delivers support-ticket notifications to admin-configured email recipients
when a seller submits a support message. Recipients resolve from
``settings.SUPPORT_NOTIFICATION_RECIPIENTS`` when set, otherwise from active
EMAIL-channel ``SupportContact`` rows via ``get_email_contacts_async``.

Delivery fails open: if no recipients are configured, or ``send_mail`` raises,
the service logs and returns without propagating an error so the bot dialog is
never disrupted by email infrastructure problems.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.mail import send_mail
from django.utils.translation import gettext as _

if TYPE_CHECKING:
    from apps.core.models import SupportTicket

logger = logging.getLogger(__name__)


@sync_to_async
def _send_mail(
    subject: str, body: str, recipient_list: list[str]
) -> int:
    """Send an email synchronously off the async event loop.

    ``send_mail`` performs blocking SMTP I/O and must never be called directly
    in the async event loop; this wrapper runs it on Django's sync worker thread.
    """
    return send_mail(
        subject,
        body,
        settings.DEFAULT_FROM_EMAIL,
        recipient_list,
        fail_silently=False,
    )


async def send_support_notification_email(
    ticket: SupportTicket, bot_username: str
) -> None:
    """Deliver a support-ticket notification to configured email recipients.

    Resolves recipients from ``settings.SUPPORT_NOTIFICATION_RECIPIENTS`` when
    non-empty, otherwise falls back to active EMAIL-type support contacts. Fails
    open: missing recipients or a raised ``send_mail`` error are logged, never
    propagated.

    Args:
        ticket: The ``SupportTicket`` that triggered the notification.
        bot_username: The bot's username, included for context.
    """
    # 1. Resolve recipients: settings first, then EMAIL-type contacts.
    recipients = list(settings.SUPPORT_NOTIFICATION_RECIPIENTS)
    if not recipients:
        from apps.core.services.support import get_email_contacts_async

        contacts = await get_email_contacts_async()
        recipients = [c.email for c in contacts if c.email]

    # 2. Fail open when no recipients are configured.
    if not recipients:
        logger.warning(
            "No email recipients configured; skipping support email for ticket %s",
            ticket.ticket_ref,
        )
        return

    # 3. Build the subject (gettext-wrapped, English msgid source).
    subject = _("[%(ref)s] New support request") % {"ref": ticket.ticket_ref}

    # 4. Extract fields up front so the body is built from plain values, keeping
    #    model-field access out of the user-facing string interpolation (i18n AST gate).
    ticket_ref = ticket.ticket_ref
    telegram_id = ticket.telegram_id
    username = ticket.username or ""
    text = ticket.text

    body = _(
        "Support ticket %(ref)s\n"
        "From: telegram_id=%(tid)s username=%(username)s\n"
        "\n%(text)s"
    ) % {
        "ref": ticket_ref,
        "tid": telegram_id,
        "username": username,
        "text": text,
    }

    # 5. Deliver, logging (not re-raising) on failure (fail-open).
    try:
        await _send_mail(subject, body, recipients)
    except Exception:
        logger.exception(
            "Failed to send support email for ticket %s", ticket.ticket_ref
        )
