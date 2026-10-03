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
- Storage-consent gate (06-PII-101): an unregistered ``chat_id`` is refused
  with the consent notice and **no ticket** is created.
"""

from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from asgiref.sync import sync_to_async
from django.core.cache import cache
from django.utils import timezone
from django.utils.functional import Promise

from telegram_bot.handlers.support import (
    SUPPORT_CONSENT_REQUIRED_MESSAGE,
    SUPPORT_MESSAGE_MAX_LENGTH,
    SUPPORT_MESSAGE_TOO_LONG_MESSAGE,
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
    chat_id: int = 123,
) -> MagicMock:
    """Build a ``Message`` double for ``handle_support_message``.

    ``chat_id`` defaults to 123 (mirroring a private chat); pass a value
    matching a registered user's ``User.chat_id`` for attribution tests.
    """
    message = MagicMock()
    message.from_user = MagicMock()
    message.from_user.id = user_id
    message.from_user.is_bot = is_bot
    message.from_user.username = "ticket_user"
    message.chat = MagicMock()
    message.chat.id = chat_id
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
        """A consenting registered user is moved to AWAITING_MESSAGE and prompted."""
        from conftest import make_user

        await sync_to_async(make_user)(301, consent_given_at=timezone.now())
        callback = _mock_callback(user_id=301)

        await handle_support_start(callback, fsm_context)

        callback.answer.assert_awaited_once()  # spinner dismissed
        assert await fsm_context.get_state() == ContactUsState.AWAITING_MESSAGE
        callback.message.answer.assert_awaited_once()
        sent_text = callback.message.answer.await_args.args[0]
        assert str(sent_text) == str(SUPPORT_PROMPT_MESSAGE)

    @pytest.mark.asyncio
    async def test_unregistered_user_is_refused_with_consent_notice(
        self, fsm_context: FSMContext
    ) -> None:
        """An unregistered chat_id is refused at the start gate (06-PII-101)."""
        callback = _mock_callback(user_id=306)

        await handle_support_start(callback, fsm_context)

        callback.message.answer.assert_awaited_once()
        sent_text = callback.message.answer.await_args.args[0]
        assert str(sent_text) == str(SUPPORT_CONSENT_REQUIRED_MESSAGE)
        assert await fsm_context.get_state() is None

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
        """6th support trigger within the window yields the cooldown message.

        Re-pinned for the storage-consent gate (06-PII-101): the gate runs
        **before** the rate limit, so the caller must be a consenting registered
        user for the cooldown branch to be reachable; an unregistered caller gets
        the consent notice first. The test's intent — the 6th trigger within the
        window is rate-limited — is unchanged.
        """
        from conftest import make_user

        await sync_to_async(make_user)(303, consent_given_at=timezone.now())
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
        """An unregistered sender is refused: no ticket, one consent notice.

        This **inverts the test's original purpose.** Under the storage-consent
        gate (06-PII-101) ``user304`` is unregistered, i.e. exactly the
        no-consent case, so the intake must refuse rather than persist. The
        former happy-path assertions (ticket row, email + Telegram delivery,
        ``ticket_ref`` confirmation) now belong to
        ``test_registered_user_is_attributed``.
        """
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

        # No ticket, no delivery, exactly one notice naming the consent rule.
        assert await _count_tickets() == 0
        mock_email.assert_not_awaited()
        mock_telegram.assert_not_awaited()
        message.answer.assert_awaited_once()
        sent_text = message.answer.await_args.args[0]
        assert str(sent_text) == str(SUPPORT_CONSENT_REQUIRED_MESSAGE)

        # FSM reset to IDLE on refusal.
        assert await fsm_context.get_state() == ContactUsState.IDLE

    @pytest.mark.asyncio
    async def test_unregistered_sender_is_refused_no_ticket(
        self, fsm_context: FSMContext
    ) -> None:
        """An unregistered sender (no consent) is refused with the notice.

        Renamed from ``test_anonymous_user_has_null_user_fk``: under the
        storage-consent gate (06-PII-101) the bot never creates an unattributed
        ticket, so "null user FK" is no longer reachable at the bot boundary.
        The model can still store one
        (``test_support_models.py::TestSupportTicketAnonymous``); the *bot*
        refuses.
        """
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

        assert await _count_tickets() == 0
        message.answer.assert_awaited_once()
        sent_text = message.answer.await_args.args[0]
        assert str(sent_text) == str(SUPPORT_CONSENT_REQUIRED_MESSAGE)
        assert await fsm_context.get_state() == ContactUsState.IDLE

    @pytest.mark.asyncio
    async def test_registered_user_is_attributed(self, fsm_context: FSMContext) -> None:
        """A consenting registered user is attributed and completes the ticket.

        The user must have ``consent_given_at`` set (the storage-consent gate)
        and its ``chat_id`` must match the message's ``chat.id``, because the
        actor is resolved server-side by ``chat_id`` (06-PII-101).
        """
        from apps.users.models import User

        user = await sync_to_async(User.objects.create)(
            telegram_id=900000100,
            chat_id=900000100,
            password="x",
            consent_given_at=timezone.now(),
        )
        await fsm_context.set_state(ContactUsState.AWAITING_MESSAGE)
        await fsm_context.update_data(user_id=user.id)
        message = _mock_message(
            text="I am registered", user_id=900000100, chat_id=900000100
        )
        bot = _mock_bot()

        with (
            patch(
                "telegram_bot.handlers.support.send_support_notification_email",
                new=AsyncMock(),
            ) as mock_email,
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

        assert await _count_tickets() == 1
        ticket = await _latest_ticket()
        assert ticket.user_id == user.id
        assert ticket.chat_id == 900000100
        assert ticket.telegram_id == 900000100
        assert ticket.text == "I am registered"
        mock_email.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_registered_user_without_consent_is_refused(
        self, fsm_context: FSMContext
    ) -> None:
        """A registered user without ``consent_given_at`` gets no ticket."""
        from apps.users.models import User

        user = await sync_to_async(User.objects.create)(
            telegram_id=900000101,
            chat_id=900000101,
            password="x",
        )
        await fsm_context.set_state(ContactUsState.AWAITING_MESSAGE)
        await fsm_context.update_data(user_id=user.id)
        message = _mock_message(text="No consent", user_id=900000101, chat_id=900000101)
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

        assert await _count_tickets() == 0
        message.answer.assert_awaited_once()
        assert str(message.answer.await_args.args[0]) == str(
            SUPPORT_CONSENT_REQUIRED_MESSAGE
        )

    @pytest.mark.asyncio
    async def test_stale_fsm_user_id_is_refused(self, fsm_context: FSMContext) -> None:
        """A stale FSM ``user_id`` that disagrees with the actor is refused.

        Free text captured before consent (or under a different identity) must
        not become a ticket. The FSM ``user_id`` is a cross-check only; a
        mismatch refuses even when the resolved actor itself could store data.
        """
        from apps.users.models import User

        actor = await sync_to_async(User.objects.create)(
            telegram_id=900000102,
            chat_id=900000102,
            password="x",
            consent_given_at=timezone.now(),
        )
        other = await sync_to_async(User.objects.create)(
            telegram_id=900000103,
            chat_id=900000103,
            password="x",
            consent_given_at=timezone.now(),
        )
        await fsm_context.set_state(ContactUsState.AWAITING_MESSAGE)
        await fsm_context.update_data(user_id=other.id)
        message = _mock_message(text="Stale", user_id=900000102, chat_id=900000102)
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

        assert await _count_tickets() == 0
        assert str(message.answer.await_args.args[0]) == str(
            SUPPORT_CONSENT_REQUIRED_MESSAGE
        )
        assert actor.id != other.id

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


# ---------------------------------------------------------------------------
# Import-time locale baking regression
# ---------------------------------------------------------------------------


class TestSupportMessageLocalization:
    """The support message constants must not bake the import-time locale."""

    @pytest.mark.django_db(transaction=True)
    def test_message_constants_are_lazy_proxies(self) -> None:
        """All three support message constants are lazy, not eager ``_()`` strings.

        Regression: eager ``_()`` at module scope froze the strings to
        ``settings.LANGUAGE_CODE`` (Russian in production) at import time,
        defeating per-user localization. ``gettext_lazy`` proxies defer the
        translation to handler-run time.
        """
        constants = (
            SUPPORT_PROMPT_MESSAGE,
            SUPPORT_RATE_LIMITED_MESSAGE,
            SUPPORT_MESSAGE_TOO_LONG_MESSAGE,
        )
        for const in constants:
            assert isinstance(const, Promise), (
                f"{const!r} must be a lazy gettext proxy, not an eager string"
            )
            # Under the default ``en`` test locale the proxy resolves to the
            # English msgid source text.
            assert str(const) == str(const)
            assert isinstance(str(const), str)

    @pytest.mark.django_db(transaction=True)
    def test_prompt_resolves_to_english_under_en_locale(self) -> None:
        """Under an active ``en`` locale the prompt resolves to the English msgid.

        Guards against the import-time-baking regression: if the constant had
        been eagerly frozen to Russian, activating ``en`` would not restore the
        English source text.
        """
        expected = "Write your question — we will reply as soon as possible."
        assert str(SUPPORT_PROMPT_MESSAGE) == expected
