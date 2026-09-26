"""
Tests for the support-ticket email delivery service (EC-6 / source plan B12).

Covers ``send_support_notification_email``:
- recipient resolution: ``settings.SUPPORT_NOTIFICATION_RECIPIENTS`` when set,
  falling back to active EMAIL-type ``SupportContact`` rows otherwise;
- the delivered email: one message in ``mail.outbox`` whose body carries the
  ticket_ref, telegram_id, username, and message text, and whose subject
  contains the ticket_ref;
- fail-open behavior: no exception when the recipients list is empty, and no
  propagation when ``send_mail`` itself raises.

Uses the locmem email backend forced by the test settings
(``django.core.mail.backends.locmem.EmailBackend``) which captures sent
messages in ``django.core.mail.outbox``.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from asgiref.sync import sync_to_async
from django.core import mail
from django.test import override_settings

from apps.core.enums import SupportChannelType
from apps.core.models import SupportContact, SupportTicket
from telegram_bot.services.support_delivery_email import (
    send_support_notification_email,
)

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.integration,
]


@pytest.fixture(autouse=True)
def _clear_mail_outbox() -> None:
    """Reset the locmem outbox so sent messages don't leak between tests."""
    mail.outbox.clear()


async def _make_ticket(**kwargs: object) -> SupportTicket:
    """Create a SupportTicket row with sensible defaults (off the event loop).

    ``SupportTicket.save`` always auto-generates ``ticket_ref`` on first save,
    so an explicitly requested reference is applied via a follow-up save.
    """
    explicit_ref = kwargs.pop("ticket_ref", None)
    defaults: dict[str, object] = {
        "chat_id": 900000001,
        "telegram_id": 900000001,
        "username": "ticket_user",
        "text": "Help me please",
    }
    defaults.update(kwargs)
    ticket = await sync_to_async(SupportTicket.objects.create)(**defaults)
    if explicit_ref is not None:
        ticket.ticket_ref = str(explicit_ref)
        await sync_to_async(ticket.save)(update_fields=["ticket_ref"])
    return ticket


async def _make_email_contact(
    email: str, *, active: bool = True
) -> SupportContact:
    """Create an active EMAIL-type SupportContact row."""
    return await sync_to_async(SupportContact.objects.create)(
        channel_type=SupportChannelType.EMAIL,
        label="Support email",
        email=email,
        is_active=active,
    )


class TestRecipientResolution:
    """Recipients come from settings first, then EMAIL-type contacts."""

    @pytest.mark.asyncio
    async def test_uses_settings_recipients_when_set(self) -> None:
        """Configured recipients take precedence over contacts."""
        ticket = await _make_ticket()
        await _make_email_contact("contact@example.com")

        with override_settings(
            SUPPORT_NOTIFICATION_RECIPIENTS=["admin@example.com"]
        ):
            await send_support_notification_email(ticket, bot_username="bot")

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ["admin@example.com"]
        assert "contact@example.com" not in mail.outbox[0].to

    @pytest.mark.asyncio
    async def test_falls_back_to_email_contacts(self) -> None:
        """Empty settings fall back to active EMAIL-type support contacts."""
        ticket = await _make_ticket()
        await _make_email_contact("support@example.com")

        with override_settings(SUPPORT_NOTIFICATION_RECIPIENTS=[]):
            await send_support_notification_email(ticket, bot_username="bot")

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ["support@example.com"]

    @pytest.mark.asyncio
    async def test_ignores_non_email_contacts(self) -> None:
        """Only EMAIL-channel contacts are used as recipients."""
        ticket = await _make_ticket()
        await _make_email_contact("support@example.com")
        await sync_to_async(SupportContact.objects.create)(
            channel_type=SupportChannelType.TELEGRAM,
            label="Telegram support",
            telegram_id=12345,
        )

        with override_settings(SUPPORT_NOTIFICATION_RECIPIENTS=[]):
            await send_support_notification_email(ticket, bot_username="bot")

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ["support@example.com"]


class TestEmailContent:
    """The delivered email carries ticket details and reference."""

    @pytest.mark.asyncio
    async def test_subject_contains_ticket_ref(self) -> None:
        """Subject embeds the human-readable ticket reference."""
        ticket = await _make_ticket(ticket_ref="SUP-202609-001")

        with override_settings(
            SUPPORT_NOTIFICATION_RECIPIENTS=["admin@example.com"]
        ):
            await send_support_notification_email(ticket, bot_username="bot")

        assert len(mail.outbox) == 1
        assert "SUP-202609-001" in mail.outbox[0].subject

    @pytest.mark.asyncio
    async def test_body_includes_ticket_details(self) -> None:
        """Body contains ticket_ref, telegram_id, username, and message text."""
        ticket = await _make_ticket(
            ticket_ref="SUP-202609-002",
            telegram_id=900000042,
            username="buyer_42",
            text="My order never arrived",
        )

        with override_settings(
            SUPPORT_NOTIFICATION_RECIPIENTS=["admin@example.com"]
        ):
            await send_support_notification_email(ticket, bot_username="bot")

        assert len(mail.outbox) == 1
        body = mail.outbox[0].body
        assert "SUP-202609-002" in body
        assert "900000042" in body
        assert "buyer_42" in body
        assert "My order never arrived" in body


class TestFailOpen:
    """Delivery never raises on missing recipients or email failures."""

    @pytest.mark.asyncio
    async def test_no_recipients_is_noop(self) -> None:
        """Empty recipients log a warning and send nothing (fail-open)."""
        ticket = await _make_ticket()

        with override_settings(SUPPORT_NOTIFICATION_RECIPIENTS=[]):
            await send_support_notification_email(ticket, bot_username="bot")

        assert mail.outbox == []

    @pytest.mark.asyncio
    async def test_send_mail_failure_is_swallowed(self) -> None:
        """A raised ``send_mail`` is logged, not propagated (fail-open)."""
        ticket = await _make_ticket()

        with override_settings(
            SUPPORT_NOTIFICATION_RECIPIENTS=["admin@example.com"]
        ):
            with patch(
                "telegram_bot.services.support_delivery_email._send_mail",
                side_effect=RuntimeError("SMTP down"),
            ):
                # Must not raise despite the email backend failure.
                await send_support_notification_email(ticket, bot_username="bot")

        assert mail.outbox == []
