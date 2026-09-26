"""
Tests for the support-ticket Telegram delivery service (EC-7 / source plan B13).

Covers ``send_support_notification_telegram``:
- delivery to every active TELEGRAM-type contact, skipping EMAIL-type ones;
- per-contact isolation: one contact raising does not stop delivery to others;
- 429 handling: ``TelegramRetryAfter`` triggers a single retry after the
  mandated ``retry_after`` sleep;
- the DM body carries the ticket_ref, telegram_id, username, and message text.

The ``bot`` fixture is a real aiogram ``Bot`` (token from settings); its
outbound ``send_message`` is mocked per-test with an ``AsyncMock`` so no
Telegram network call is ever made.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramRetryAfter
from asgiref.sync import sync_to_async

from apps.core.enums import SupportChannelType
from apps.core.models import SupportContact, SupportTicket
from telegram_bot.services.support_delivery_telegram import (
    send_support_notification_telegram,
)

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.integration,
]


@pytest.fixture
def bot() -> AsyncMock:
    """A fake bot exposing a mockable ``send_message``.

    The service only ever calls ``bot.send_message``, so a plain ``AsyncMock``
    is sufficient and avoids constructing a real aiogram ``Bot`` (whose token
    validation fails with the placeholder test ``BOT_TOKEN``).
    """
    fake = AsyncMock()
    fake.send_message = AsyncMock(return_value=None)
    return fake


async def _make_ticket(**kwargs: object) -> SupportTicket:
    """Create a SupportTicket row with sensible defaults (off the event loop)."""
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


async def _make_contact(
    channel_type: SupportChannelType,
    *,
    telegram_id: int | None = None,
    active: bool = True,
) -> SupportContact:
    """Create an active SupportContact row with the given channel type."""
    return await sync_to_async(SupportContact.objects.create)(
        channel_type=channel_type,
        label=f"Support {channel_type.value}",
        telegram_id=telegram_id,
        email=None if telegram_id is not None else "support@example.com",
        is_active=active,
    )


class TestDeliveryToContacts:
    """Sends to TELEGRAM contacts, skips EMAIL contacts."""

    @pytest.mark.asyncio
    async def test_sends_to_every_active_telegram_contact(self, bot) -> None:
        """Every active TELEGRAM contact receives the DM."""
        ticket = await _make_ticket()
        contact_a = await _make_contact(
            SupportChannelType.TELEGRAM, telegram_id=11111
        )
        contact_b = await _make_contact(
            SupportChannelType.TELEGRAM, telegram_id=22222
        )

        await send_support_notification_telegram(
            ticket, bot, [contact_a, contact_b]
        )

        send_mock = bot.send_message
        assert send_mock.await_count == 2
        sent_ids = {call.kwargs["chat_id"] for call in send_mock.await_args_list}
        assert sent_ids == {11111, 22222}

    @pytest.mark.asyncio
    async def test_skips_email_contacts(self, bot) -> None:
        """EMAIL-type contacts are not messaged."""
        ticket = await _make_ticket()
        telegram_contact = await _make_contact(
            SupportChannelType.TELEGRAM, telegram_id=33333
        )
        email_contact = await _make_contact(SupportChannelType.EMAIL)

        await send_support_notification_telegram(
            ticket, bot, [telegram_contact, email_contact]
        )

        send_mock = bot.send_message
        assert send_mock.await_count == 1
        assert send_mock.await_args.kwargs["chat_id"] == 33333


class TestPerContactIsolation:
    """One failing contact does not stop delivery to the others."""

    @pytest.mark.asyncio
    async def test_failing_contact_does_not_block_others(self, bot) -> None:
        """A raised send_message on the first contact is isolated."""
        ticket = await _make_ticket()
        contact_a = await _make_contact(
            SupportChannelType.TELEGRAM, telegram_id=11111
        )
        contact_b = await _make_contact(
            SupportChannelType.TELEGRAM, telegram_id=22222
        )

        async def _flaky(chat_id: int, **kwargs: object) -> None:
            if chat_id == 11111:
                raise RuntimeError("Contact blocked the bot")
            return None

        bot.send_message = AsyncMock(side_effect=_flaky)

        # Must not raise despite the first contact failing.
        await send_support_notification_telegram(
            ticket, bot, [contact_a, contact_b]
        )

        assert bot.send_message.await_count == 2


class TestRetryAfterHandling:
    """A 429 triggers one retry after the mandated sleep."""

    @pytest.mark.asyncio
    async def test_retries_after_telegram_retry_after(self, bot, monkeypatch) -> None:
        """First send raises 429, second succeeds after retry_after sleep."""
        ticket = await _make_ticket()
        contact = await _make_contact(
            SupportChannelType.TELEGRAM, telegram_id=44444
        )

        calls = 0

        async def _flaky(chat_id: int, **kwargs: object) -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise TelegramRetryAfter(
                    method=None, message="flood", retry_after=1
                )
            return None

        send_mock = AsyncMock(side_effect=_flaky)
        bot.send_message = send_mock

        # Patch asyncio.sleep so the test doesn't actually wait a second.
        sleeps: list[float] = []
        async def _fake_sleep(delay: float) -> None:
            sleeps.append(delay)

        monkeypatch.setattr(
            "telegram_bot.services.support_delivery_telegram.asyncio.sleep",
            _fake_sleep,
        )

        await send_support_notification_telegram(ticket, bot, [contact])

        assert send_mock.await_count == 2
        assert sleeps == [1]


class TestMessageBody:
    """The DM body carries ticket details."""

    @pytest.mark.asyncio
    async def test_body_includes_ticket_details(self, bot) -> None:
        """Body contains ticket_ref, telegram_id, username, and message text."""
        ticket = await _make_ticket(
            ticket_ref="SUP-202609-003",
            telegram_id=900000042,
            username="buyer_42",
            text="My order never arrived",
        )
        contact = await _make_contact(
            SupportChannelType.TELEGRAM, telegram_id=55555
        )

        send_mock = AsyncMock(return_value=None)
        bot.send_message = send_mock

        await send_support_notification_telegram(ticket, bot, [contact])

        assert send_mock.await_count == 1
        body = send_mock.await_args.kwargs["text"]
        assert "SUP-202609-003" in body
        assert "900000042" in body
        assert "buyer_42" in body
        assert "My order never arrived" in body
