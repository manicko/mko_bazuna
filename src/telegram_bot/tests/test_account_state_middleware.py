"""
Tests for AccountStateMiddleware account-state gating (PC-002, PC-003).

Verifies that the middleware delegates to the shared ``get_account_state``
predicate (``apps.users.services.account_state``) and returns state-specific
(i18n-wrapped) denial messages for each blocked account state.

Test environment uses ``LANGUAGE_CODE = "en"`` (see config/settings/test.py),
so ``gettext`` returns the msgid (English source) — the substring assertions
below check English substrings, matching the msgid source text.
"""

import itertools
from typing import Any
from unittest.mock import AsyncMock

import pytest
from aiogram.types import Message, TelegramObject, Update
from asgiref.sync import sync_to_async
from django.utils import timezone

from apps.users.models import User
from apps.users.services import can_login
from telegram_bot.middlewares import AccountStateMiddleware

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.concurrent,
]
pytestmark.append(pytest.mark.xdist_group("bot_concurrent"))

_BASE_CHAT_ID = 900000200


async def _make_user(
    chat_id: int,
    *,
    is_banned: bool = False,
    is_deleted: bool = False,
    is_declined: bool = False,
    ads_auto_publish: bool = True,
    consent_revoked: bool = False,
) -> User:
    """Create a User with specific account-state flags via sync_to_async."""
    kwargs: dict[str, Any] = {
        "telegram_id": chat_id,
        "chat_id": chat_id,
        "password": "x",
        "is_banned": is_banned,
        "is_deleted": is_deleted,
        "is_declined": is_declined,
        "ads_auto_publish": ads_auto_publish,
    }
    if consent_revoked:
        kwargs["consent_revoked_at"] = timezone.now()
    return await sync_to_async(User.objects.create)(**kwargs)


_next_update_id = itertools.count(42)


def _make_message_update(chat_id: int, text: str = "") -> Update:
    """Construct a real aiogram Update wrapping a Message from a test user."""
    from aiogram.types import Chat, Message, Update, User as TelegramUser

    user = TelegramUser(id=chat_id, first_name="Test", is_bot=False)
    return Update(
        update_id=next(_next_update_id),
        message=Message(
            message_id=1,
            date=timezone.now(),
            chat=Chat(id=chat_id, type="private"),
            from_user=user,
            text=text,
        ),
    )


def _make_callback_update(chat_id: int) -> Update:
    """Construct a real aiogram Update wrapping a CallbackQuery from a test user."""
    from aiogram.types import (
        CallbackQuery,
        Chat,
        Message,
        Update,
        User as TelegramUser,
    )

    user = TelegramUser(id=chat_id, first_name="Test", is_bot=False)
    msg = Message(
        message_id=1,
        date=timezone.now(),
        chat=Chat(id=chat_id, type="private"),
        from_user=user,
    )
    return Update(
        update_id=next(_next_update_id),
        callback_query=CallbackQuery(
            id="cb_test",
            from_user=user,
            message=msg,
            chat_instance="-1",
            data="test_action",
        ),
    )


# ---------------------------------------------------------------------------
# State-specific denial messages
# ---------------------------------------------------------------------------


class TestCheckUserStateMessages:
    """Each blocked state yields a distinct, state-specific denial message."""

    @pytest.mark.asyncio
    async def test_banned_user(self) -> None:
        """Banned user is blocked with a restriction message."""
        chat_id = _BASE_CHAT_ID + 1
        await _make_user(chat_id, is_banned=True)

        middleware = AccountStateMiddleware()
        can_interact, message = await middleware._check_user_state(chat_id)

        assert can_interact is False
        assert "restrict" in message

    @pytest.mark.asyncio
    async def test_deleted_user(self) -> None:
        """Deleted user is blocked with a deletion message."""
        chat_id = _BASE_CHAT_ID + 2
        await _make_user(chat_id, is_deleted=True)

        middleware = AccountStateMiddleware()
        can_interact, message = await middleware._check_user_state(chat_id)

        assert can_interact is False
        assert "deleted" in message

    @pytest.mark.asyncio
    async def test_declined_user(self) -> None:
        """Declined user is blocked with a browse-only message."""
        chat_id = _BASE_CHAT_ID + 3
        await _make_user(chat_id, is_declined=True)

        middleware = AccountStateMiddleware()
        can_interact, message = await middleware._check_user_state(chat_id)

        assert can_interact is False
        assert "browse" in message or "browsing" in message

    @pytest.mark.asyncio
    async def test_consent_revoked_user(self) -> None:
        """Consent-withdrawn user is blocked with an erasure message."""
        chat_id = _BASE_CHAT_ID + 4
        await _make_user(chat_id, consent_revoked=True)

        middleware = AccountStateMiddleware()
        can_interact, message = await middleware._check_user_state(chat_id)

        assert can_interact is False
        assert "erased" in message or "withdrawn" in message

    @pytest.mark.asyncio
    async def test_normal_user(self) -> None:
        """A user with no restriction flags can interact without a message."""
        chat_id = _BASE_CHAT_ID + 5
        await _make_user(chat_id)

        middleware = AccountStateMiddleware()
        can_interact, message = await middleware._check_user_state(chat_id)

        assert can_interact is True
        assert message == ""

    @pytest.mark.asyncio
    async def test_unregistered_user(self) -> None:
        """A chat_id with no matching user returns (True, '')."""
        middleware = AccountStateMiddleware()
        can_interact, message = await middleware._check_user_state(999999999)

        assert can_interact is True
        assert message == ""


# ---------------------------------------------------------------------------
# Cross-predicate agreement
# ---------------------------------------------------------------------------


class TestCrossPredicateAgreement:
    """_check_user_state agrees with the explicit flag formula and can_login."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "row, is_banned, is_deleted, is_declined, consent_revoked, expected_can",
        [
            # Each individual flag blocks interaction.
            (1, True, False, False, False, False),
            (2, False, True, False, False, False),
            (3, False, False, True, False, False),
            (4, False, False, False, True, False),
            # All flags together still blocks.
            (5, True, True, True, True, False),
            # No flags allows interaction.
            (6, False, False, False, False, True),
            # Two flags (deleted + revoked) still blocks.
            (7, False, True, False, True, False),
        ],
    )
    async def test_matches_explicit_formula(
        self,
        row: int,
        is_banned: bool,
        is_deleted: bool,
        is_declined: bool,
        consent_revoked: bool,
        expected_can: bool,
    ) -> None:
        """can_interact matches: not(banned or deleted or declined or revoked).

        This is the single source of truth for interaction gating, matching
        the predicate used in ``get_account_state`` / the AccountState NamedTuple.
        """
        chat_id = _BASE_CHAT_ID + 100 + row
        await _make_user(
            chat_id,
            is_banned=is_banned,
            is_deleted=is_deleted,
            is_declined=is_declined,
            consent_revoked=consent_revoked,
        )

        middleware = AccountStateMiddleware()
        can_interact, _ = await middleware._check_user_state(chat_id)

        expected = not (is_banned or is_deleted or is_declined or consent_revoked)
        assert can_interact == expected
        assert can_interact == expected_can

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "row, is_banned, is_declined",
        [
            (1, True, False),
            (2, False, True),
            (3, True, True),
        ],
    )
    async def test_blocks_when_can_login_blocks(
        self,
        row: int,
        is_banned: bool,
        is_declined: bool,
    ) -> None:
        """When can_login(user) is False, _check_user_state also blocks.

        ``can_login`` gates on is_banned and is_declined only.  The middleware
        extends that gate with is_deleted and consent_revoked, so whenever
        ``can_login`` denies access the middleware must deny too (the middleware
        blocks a superset of the login predicate).
        """
        chat_id = _BASE_CHAT_ID + 200 + row
        user = await _make_user(
            chat_id,
            is_banned=is_banned,
            is_declined=is_declined,
        )

        assert can_login(user) is False

        middleware = AccountStateMiddleware()
        can_interact, message = await middleware._check_user_state(chat_id)

        assert can_interact is False
        assert message != ""

    @pytest.mark.asyncio
    async def test_normal_user_allows_when_can_login_allows(self) -> None:
        """A normal user passes both can_login and _check_user_state."""
        chat_id = _BASE_CHAT_ID + 300
        user = await _make_user(chat_id)

        assert can_login(user) is True

        middleware = AccountStateMiddleware()
        can_interact, message = await middleware._check_user_state(chat_id)

        assert can_interact is True
        assert message == ""


# ---------------------------------------------------------------------------
# __call__ pipeline integration tests (AUT-003)
#
# Before the fix, AccountStateMiddleware was registered on dp.message, which
# dispatches Message events.  The isinstance(event, Update) gate was always
# False (Message is not a subclass of Update), so the middleware silently
# short-circuited on every event.  These tests exercise the __call__ path with
# real Update objects — only meaningful after the registration move to dp.update.
# ---------------------------------------------------------------------------


class TestCallPipeline:
    """Integration tests for AccountStateMiddleware.__call__ with real Update events.

    These tests verify the full pipeline: isinstance(event, Update) gate ->
    message extraction -> user state check -> publish check -> handler chain.
    Before AUT-003, the middleware was registered on dp.message (receiving Message
    events), so the isinstance gate always short-circuited — these tests exercise
    the Update event path that only works after the registration fix.
    """

    @pytest.mark.asyncio
    async def test_call_passes_update_event(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A normal registered user's Update event reaches the handler.

        Before the fix: isinstance(event, Update) was always False (Message events),
        so the middleware short-circuited silently.  After the fix: the middleware
        receives Update events, the gate passes, and the handler is invoked.
        """
        chat_id = _BASE_CHAT_ID + 501
        await _make_user(chat_id)

        update = _make_message_update(chat_id)
        handler = AsyncMock(return_value="proceed")
        mock_answer = AsyncMock()
        monkeypatch.setattr(Message, "answer", mock_answer)

        result = await AccountStateMiddleware()(handler, update, {})

        assert result == "proceed"
        handler.assert_awaited_once_with(update, {})

    @pytest.mark.asyncio
    async def test_call_blocks_banned_user(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A banned user is blocked — handler NOT called, restriction message sent."""
        chat_id = _BASE_CHAT_ID + 502
        await _make_user(chat_id, is_banned=True)

        update = _make_message_update(chat_id)
        handler = AsyncMock(return_value="proceed")
        mock_answer = AsyncMock()
        monkeypatch.setattr(Message, "answer", mock_answer)

        result = await AccountStateMiddleware()(handler, update, {})

        assert result is None
        handler.assert_not_awaited()
        mock_answer.assert_awaited_once()
        assert "restrict" in mock_answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_call_blocks_declined_user(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A declined user is blocked — handler NOT called, browse-only message sent."""
        chat_id = _BASE_CHAT_ID + 503
        await _make_user(chat_id, is_declined=True)

        update = _make_message_update(chat_id)
        handler = AsyncMock(return_value="proceed")
        mock_answer = AsyncMock()
        monkeypatch.setattr(Message, "answer", mock_answer)

        result = await AccountStateMiddleware()(handler, update, {})

        assert result is None
        handler.assert_not_awaited()
        mock_answer.assert_awaited_once()
        assert "browse" in mock_answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_call_handles_callback_query_update(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A normal registered user's callback_query Update reaches the handler."""
        chat_id = _BASE_CHAT_ID + 504
        await _make_user(chat_id)

        update = _make_callback_update(chat_id)
        handler = AsyncMock(return_value="proceed")
        mock_answer = AsyncMock()
        monkeypatch.setattr(Message, "answer", mock_answer)

        result = await AccountStateMiddleware()(handler, update, {})

        assert result == "proceed"
        handler.assert_awaited_once_with(update, {})

    @pytest.mark.asyncio
    async def test_call_normal_user_proceeds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A normal registered user proceeds — handler called, no rejection message."""
        chat_id = _BASE_CHAT_ID + 505
        await _make_user(chat_id)

        update = _make_message_update(chat_id)
        handler = AsyncMock(return_value="proceed")
        mock_answer = AsyncMock()
        monkeypatch.setattr(Message, "answer", mock_answer)

        result = await AccountStateMiddleware()(handler, update, {})

        assert result == "proceed"
        handler.assert_awaited_once_with(update, {})
        mock_answer.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_call_unregistered_user_proceeds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An unregistered chat_id proceeds — handler called (handler's own gate rejects).

        _check_user_state returns (True, "") for unknown users, so the middleware
        does not block.  The handler proceeds; authentication is the handler's
        responsibility.
        """
        chat_id = 999999999
        update = _make_message_update(chat_id)
        handler = AsyncMock(return_value="proceed")
        mock_answer = AsyncMock()
        monkeypatch.setattr(Message, "answer", mock_answer)

        result = await AccountStateMiddleware()(handler, update, {})

        assert result == "proceed"
        handler.assert_awaited_once_with(update, {})
        mock_answer.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_call_non_update_event_falls_through(self) -> None:
        """A bare TelegramObject (not Update) short-circuits through to the handler.

        The isinstance(event, Update) gate returns False, so the middleware
        calls handler(event, data) immediately — no DB lookup, no state check.
        """
        handler = AsyncMock(return_value="fallback")
        event = TelegramObject()

        result = await AccountStateMiddleware()(handler, event, {})

        assert result == "fallback"
        handler.assert_awaited_once_with(event, {})

    @pytest.mark.asyncio
    async def test_data_get_state_never_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Passing a data dict without 'state' key does not raise — handler still called.

        The FSMContextMiddleware may not set data['state'] for edge-case updates.
        The middleware must use data.get('state') (not data['state']) so a missing
        key never raises KeyError.  This test passes {} as data and verifies no
        exception, with the handler still invoked.
        """
        chat_id = _BASE_CHAT_ID + 508
        await _make_user(chat_id)

        update = _make_message_update(chat_id)
        handler = AsyncMock(return_value="proceed")
        mock_answer = AsyncMock()
        monkeypatch.setattr(Message, "answer", mock_answer)

        result = await AccountStateMiddleware()(handler, update, {})

        assert result == "proceed"
        handler.assert_awaited_once_with(update, {})
