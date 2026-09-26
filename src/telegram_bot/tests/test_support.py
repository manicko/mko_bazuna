"""
Tests for the support message intake flow (EC-9).

Covers:
- ``handle_support_start`` (SUPPORT_START callback): sets the FSM to
  ``AWAITING_MESSAGE`` and prompts for a message; bots rejected first (never
  consuming rate budget); rate-limited users get a cooldown message.
- ``handle_support_message`` (AWAITING_MESSAGE): persists a ``SupportTicket``
  (DB row with chat_id/telegram_id/username/text/status), delivers via email +
  Telegram, and confirms with the generated ``ticket_ref``.
- Validation guards: bots rejected (no persistence/delivery), empty text
  rejected, over-length text rejected.
- Anonymous senders leave the ``user`` FK null.
"""

from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage, StorageKey
from asgiref.sync import sync_to_async
from django.core.cache import cache

from telegram_bot.handlers.support import (
    SUPPORT_MESSAGE_MAX_LENGTH,
    SUPPORT_PROMPT_MESSAGE,
    SUPPORT_RATE_LIMITED_MESSAGE,
    SUPPORT_START_CALLBACK,
    handle_support_message,
    handle_support_start,
)
from telegram_bot.services.rate_limit import check_support_message_rate_limit
from telegram_bot.states import ContactUsState

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.integration,
]


@pytest.fixture(autouse=True)
def _clear_cache() -> Iterator[None]:
    """Clear the shared LocMemCache so rate-limit counters don't leak across tests."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def fsm_context() -> FSMContext:
    """A real FSMContext over in-memory storage (exercises real state I/O)."""
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=1, thread_id=0)
    return FSMContext(storage=storage, key=key)


def _mock_callback(user_id: int = 123, is_bot: bool = False) -> MagicMock:
    """Build a ``CallbackQuery`` double for ``handle_support_start``."""
    callback = MagicMock()
    callback.data = SUPPORT_START_CALLBACK
    callback.from_user = MagicMock()
    callback.from_user.id = user_id
    callback.from_user.is_bot = is_bot
    callback.answer = AsyncMock()
    callback.message = MagicMock()
    callback.message.answer = AsyncMock()
    return callback


def _mock_message(
    text: str = "Hello support",
    user_id: int = 123,
    is_bot: bool = False,
) -> MagicMock:
    """Build a ``Message`` double for ``handle_support_message``."""
    message = MagicMock()
    message.from_user = MagicMock()
    message.from_user.id = user_id
    message.from_user.is_bot = is_bot
    message.from_user.username = "ticket_user"
    message.chat = MagicMock()
    message.chat.id = 123
    message.text = text
    message.answer = AsyncMock()
    return message


def _mock_bot() -> MagicMock:
    """Build a ``Bot`` double with a resolvable ``get_me``."""
    bot = MagicMock()
    bot.get_me = AsyncMock()
    bot.get_me.return_value = MagicMock(username="mybot")
    return bot


async def _count_tickets() -> int:
    """Return the number of ``SupportTicket`` rows."""
    from apps.core.models import SupportTicket

    return await sync_to_async(SupportTicket.objects.count)()


async def _latest_ticket() -> Any:
    """Return the most recent ``SupportTicket`` row."""
    from apps.core.models import SupportTicket

    return await sync_to_async(SupportTicket.objects.latest)("id")


# ---------------------------------------------------------------------------
# handle_support_start — SUPPORT_START callback
# ---------------------------------------------------------------------------


class TestSupportStart:
    """``handle_support_start``: spinner -> bot guard -> rate limit -> prompt."""

    @pytest.mark.asyncio
    async def test_sets_state_and_prompts(self, fsm_context: FSMContext) -> None:
        """A normal user is moved to AWAITING_MESSAGE and prompted."""
        callback = _mock_callback(user_id=301)

        await handle_support_start(callback, fsm_context)

        callback.answer.assert_awaited_once()  # spinner dismissed
        assert await fsm_context.get_state() == ContactUsState.AWAITING_MESSAGE
        callback.message.answer.assert_awaited_once()
        sent_text = callback.message.answer.await_args.args[0]
        assert str(sent_text) == str(SUPPORT_PROMPT_MESSAGE)

    @pytest.mark.asyncio
    async def test_is_bot_skipped_without_budget(self, fsm_context: FSMContext) -> None:
        """Bots are rejected first (OQ1): no prompt, no rate budget consumed."""
        callback = _mock_callback(user_id=302, is_bot=True)

        await handle_support_start(callback, fsm_context)

        callback.message.answer.assert_not_awaited()
        assert await fsm_context.get_state() is None
        # A subsequent real call for the same id must NOT be rate-limited.
        assert await check_support_message_rate_limit(302) is True

    @pytest.mark.asyncio
    async def test_rate_limited_sends_cooldown(self, fsm_context: FSMContext) -> None:
        """6th support trigger within the window yields the cooldown message."""
        for _ in range(5):
            assert await check_support_message_rate_limit(303) is True

        callback = _mock_callback(user_id=303)

        await handle_support_start(callback, fsm_context)

        callback.message.answer.assert_awaited_once()
        sent_text = callback.message.answer.await_args.args[0]
        assert str(sent_text) == str(SUPPORT_RATE_LIMITED_MESSAGE)
        assert await fsm_context.get_state() is None


# ---------------------------------------------------------------------------
# handle_support_message — AWAITING_MESSAGE handler
# ---------------------------------------------------------------------------


class TestSupportMessage:
    """``handle_support_message``: validation -> persist -> deliver -> confirm."""

    @pytest.mark.asyncio
    async def test_persists_and_delivers(self, fsm_context: FSMContext) -> None:
        """A valid message persists a ticket, delivers, and confirms with ref."""
        await fsm_context.set_state(ContactUsState.AWAITING_MESSAGE)
        message = _mock_message(text="I lost my password", user_id=304)
        bot = _mock_bot()

        with (
            patch(
                "telegram_bot.handlers.support.send_support_notification_email",
                new=AsyncMock(),
            ) as mock_email,
            patch(
                "telegram_bot.handlers.support.send_support_notification_telegram",
                new=AsyncMock(),
            ) as mock_telegram,
            patch(
                "telegram_bot.handlers.support.get_support_contacts_async",
                new=AsyncMock(return_value=[]),
            ),
        ):
            await handle_support_message(message, bot, fsm_context)

        # DB row persisted with the expected attributes.
        assert await _count_tickets() == 1
        ticket = await _latest_ticket()
        assert ticket.chat_id == 123
        assert ticket.telegram_id == 304
        assert ticket.username == "ticket_user"
        assert ticket.text == "I lost my password"
        assert ticket.status == "open"
        assert ticket.ticket_ref.startswith("SUP-")

        # Delivered via both email and Telegram with the created ticket.
        mock_email.assert_awaited_once()
        delivered_ticket = mock_email.await_args.args[0]
        assert delivered_ticket.id == ticket.id
        assert mock_email.await_args.args[1] == "mybot"
        mock_telegram.assert_awaited_once()
        assert mock_telegram.await_args.args[0].id == ticket.id

        # Confirmation reply carries the ticket_ref.
        message.answer.assert_awaited_once()
        sent_text = message.answer.await_args.args[0]
        assert str(ticket.ticket_ref) in str(sent_text)

        # FSM reset back to IDLE.
        assert await fsm_context.get_state() == ContactUsState.IDLE

    @pytest.mark.asyncio
    async def test_anonymous_user_has_null_user_fk(self, fsm_context: FSMContext) -> None:
        """Anonymous senders (no user_id in state) get a null ``user`` FK."""
        await fsm_context.set_state(ContactUsState.AWAITING_MESSAGE)
        message = _mock_message(text="Hi", user_id=305)
        bot = _mock_bot()

        with (
            patch(
                "telegram_bot.handlers.support.send_support_notification_email",
                new=AsyncMock(),
            ),
            patch(
                "telegram_bot.handlers.support.send_support_notification_telegram",
                new=AsyncMock(),
            ),
            patch(
                "telegram_bot.handlers.support.get_support_contacts_async",
                new=AsyncMock(return_value=[]),
            ),
        ):
            await handle_support_message(message, bot, fsm_context)

        ticket = await _latest_ticket()
        assert ticket.user_id is None

    @pytest.mark.asyncio
    async def test_registered_user_is_attributed(self, fsm_context: FSMContext) -> None:
        """A registered user (user_id in state) is attributed to the ticket."""
        from apps.users.models import User

        user = await sync_to_async(User.objects.create)(
            telegram_id=900000100,
            chat_id=900000100,
            password="x",
        )
        await fsm_context.set_state(ContactUsState.AWAITING_MESSAGE)
        await fsm_context.update_data(user_id=user.id)
        message = _mock_message(text="I am registered", user_id=900000100)
        bot = _mock_bot()

        with (
            patch(
                "telegram_bot.handlers.support.send_support_notification_email",
                new=AsyncMock(),
            ),
            patch(
                "telegram_bot.handlers.support.send_support_notification_telegram",
                new=AsyncMock(),
            ),
            patch(
                "telegram_bot.handlers.support.get_support_contacts_async",
                new=AsyncMock(return_value=[]),
            ),
        ):
            await handle_support_message(message, bot, fsm_context)

        ticket = await _latest_ticket()
        assert ticket.user_id == user.id

    @pytest.mark.asyncio
    async def test_bot_rejected_no_persistence(self, fsm_context: FSMContext) -> None:
        """Bots are rejected: no ticket, no delivery, no confirmation."""
        await fsm_context.set_state(ContactUsState.AWAITING_MESSAGE)
        message = _mock_message(text="spam", is_bot=True)
        bot = _mock_bot()

        with (
            patch(
                "telegram_bot.handlers.support.send_support_notification_email",
                new=AsyncMock(),
            ) as mock_email,
            patch(
                "telegram_bot.handlers.support.send_support_notification_telegram",
                new=AsyncMock(),
            ) as mock_telegram,
        ):
            await handle_support_message(message, bot, fsm_context)

        assert await _count_tickets() == 0
        mock_email.assert_not_awaited()
        mock_telegram.assert_not_awaited()
        message.answer.assert_not_awaited()
        # State left untouched (still awaiting a real user message).
        assert await fsm_context.get_state() == ContactUsState.AWAITING_MESSAGE

    @pytest.mark.asyncio
    async def test_empty_message_rejected(self, fsm_context: FSMContext) -> None:
        """Empty/whitespace text is rejected with a friendly error."""
        await fsm_context.set_state(ContactUsState.AWAITING_MESSAGE)
        message = _mock_message(text="   ")
        bot = _mock_bot()

        with (
            patch(
                "telegram_bot.handlers.support.send_support_notification_email",
                new=AsyncMock(),
            ),
            patch(
                "telegram_bot.handlers.support.send_support_notification_telegram",
                new=AsyncMock(),
            ),
        ):
            await handle_support_message(message, bot, fsm_context)

        assert await _count_tickets() == 0
        message.answer.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_overlong_message_rejected(self, fsm_context: FSMContext) -> None:
        """A message over the max length is rejected with the cooldown-style error."""
        await fsm_context.set_state(ContactUsState.AWAITING_MESSAGE)
        overlong = "x" * (SUPPORT_MESSAGE_MAX_LENGTH + 1)
        message = _mock_message(text=overlong)
        bot = _mock_bot()

        with (
            patch(
                "telegram_bot.handlers.support.send_support_notification_email",
                new=AsyncMock(),
            ),
            patch(
                "telegram_bot.handlers.support.send_support_notification_telegram",
                new=AsyncMock(),
            ),
        ):
            await handle_support_message(message, bot, fsm_context)

        assert await _count_tickets() == 0
        message.answer.assert_awaited_once()
        sent_text = message.answer.await_args.args[0]
        assert "too long" in str(sent_text).lower()
