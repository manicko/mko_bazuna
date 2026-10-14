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

Uses the shared ``make_ticket`` and ``make_contact`` fixtures from the bot
conftest (consolidated from previously-duplicated local helpers — B28-SUPP-2).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.core import mail
from django.test import override_settings

from apps.core.enums import SupportChannelType
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


class TestRecipientResolution:
    """Recipients come from settings first, then EMAIL-type contacts."""

    @pytest.mark.asyncio
    async def test_uses_settings_recipients_when_set(
        self, make_ticket: callable, make_contact: callable
    ) -> None:
        """Configured recipients take precedence over contacts."""
        ticket = await make_ticket()
        await make_contact(SupportChannelType.EMAIL, email="contact@example.com")

        with override_settings(
            SUPPORT_NOTIFICATION_RECIPIENTS=["admin@example.com"]
        ):
            await send_support_notification_email(ticket)

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ["admin@example.com"]
        assert "contact@example.com" not in mail.outbox[0].to

    @pytest.mark.asyncio
    async def test_falls_back_to_email_contacts(
        self, make_ticket: callable, make_contact: callable
    ) -> None:
        """Empty settings fall back to active EMAIL-type support contacts."""
        ticket = await make_ticket()
        await make_contact(SupportChannelType.EMAIL, email="support@example.com")

        with override_settings(SUPPORT_NOTIFICATION_RECIPIENTS=[]):
            await send_support_notification_email(ticket)

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ["support@example.com"]

    @pytest.mark.asyncio
    async def test_ignores_non_email_contacts(
        self, make_ticket: callable, make_contact: callable
    ) -> None:
        """Only EMAIL-channel contacts are used as recipients."""
        ticket = await make_ticket()
        await make_contact(SupportChannelType.EMAIL, email="support@example.com")
        await make_contact(
            SupportChannelType.TELEGRAM, telegram_id=12345
        )

        with override_settings(SUPPORT_NOTIFICATION_RECIPIENTS=[]):
            await send_support_notification_email(ticket)

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ["support@example.com"]


class TestEmailContent:
    """The delivered email carries ticket details and reference."""

    @pytest.mark.asyncio
    async def test_subject_contains_ticket_ref(self, make_ticket: callable) -> None:
        """Subject embeds the human-readable ticket reference."""
        ticket = await make_ticket(ticket_ref="SUP-202609-001")

        with override_settings(
            SUPPORT_NOTIFICATION_RECIPIENTS=["admin@example.com"]
        ):
            await send_support_notification_email(ticket)

        assert len(mail.outbox) == 1
        assert "SUP-202609-001" in mail.outbox[0].subject

    @pytest.mark.asyncio
    async def test_body_includes_ticket_details(self, make_ticket: callable) -> None:
        """Body contains ticket_ref, telegram_id, username, and message text."""
        ticket = await make_ticket(
            ticket_ref="SUP-202609-002",
            telegram_id=900000042,
            username="buyer_42",
            text="My order never arrived",
        )

        with override_settings(
            SUPPORT_NOTIFICATION_RECIPIENTS=["admin@example.com"]
        ):
            await send_support_notification_email(ticket)

        assert len(mail.outbox) == 1
        body = mail.outbox[0].body
        assert "SUP-202609-002" in body
        assert "900000042" in body
        assert "buyer_42" in body
        assert "My order never arrived" in body


class TestFailOpen:
    """Delivery never raises on missing recipients or email failures."""

    @pytest.mark.asyncio
    async def test_no_recipients_is_noop(self, make_ticket: callable) -> None:
        """Empty recipients log a warning and send nothing (fail-open)."""
        ticket = await make_ticket()

        with override_settings(SUPPORT_NOTIFICATION_RECIPIENTS=[]):
            await send_support_notification_email(ticket)

        assert mail.outbox == []

    @pytest.mark.asyncio
    async def test_send_mail_failure_is_swallowed(self, make_ticket: callable) -> None:
        """A raised ``send_mail`` is logged, not propagated (fail-open)."""
        ticket = await make_ticket()

        with override_settings(
            SUPPORT_NOTIFICATION_RECIPIENTS=["admin@example.com"]
        ):
            with patch(
                "telegram_bot.services.support_delivery_email._send_mail",
                side_effect=RuntimeError("SMTP down"),
            ):
                # Must not raise despite the email backend failure.
                await send_support_notification_email(ticket)

        assert mail.outbox == []
