"""
Tests for alerts handler callback handlers (TST-012).

Covers:
- ``handle_unsubscribe_callback``: owned token → disables + swaps button,
  unknown token → alert, non-owner → alert (no state leak).
- ``handle_reenable_callback``: owned token → enables + swaps button,
  unknown token → alert.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from asgiref.sync import sync_to_async

from apps.search.models import SavedSearch
from apps.users.models import User
from telegram_bot.schemas.callbacks import BotCallbackPrefix

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.integration,
    pytest.mark.concurrent,
]
pytestmark.append(pytest.mark.xdist_group("bot_concurrent"))


# The ``owner`` / ``stranger`` fixtures are provided by the bot-suite conftest
# (conftest.py), which defines the canonical pair (telegram_id 950 000 301 /
# 950 000 302).  This file previously duplicated them with identical IDs — the
# local copies have been removed to keep a single source of truth (B28-1.3).


@pytest.fixture
def saved_search(owner: User) -> SavedSearch:
    return SavedSearch.objects.create(
        user=owner, query="laptop", is_active=True
    )


class TestHandleUnsubscribeCallback:
    """Tests for ``handle_unsubscribe_callback``."""

    @pytest.mark.asyncio
    async def test_owned_token_disables(
        self, owner, saved_search
    ) -> None:
        """An owned unsubscribe token disables the search and swaps the button."""
        from telegram_bot.handlers.alerts import handle_unsubscribe_callback

        bot = AsyncMock()

        callback = MagicMock()
        callback.data = f"{BotCallbackPrefix.UNSUB}{saved_search.unsubscribe_token}"
        callback.from_user = MagicMock(id=owner.chat_id)
        callback.message = MagicMock()
        callback.message.chat = MagicMock(id=owner.chat_id)
        callback.message.message_id = 42
        callback.answer = AsyncMock()

        await handle_unsubscribe_callback(callback, bot)

        # The DB state-flip is verified in test_unsubscribe.py::test_owned_search_disabled,
        # which tests ``resolve_unsubscribe`` directly. Here we focus on the callback
        # handler's observable behaviour: the button-swap and the answer text.
        bot.edit_message_reply_markup.assert_awaited_once()
        callback.answer.assert_awaited_with("Notifications disabled")

    @pytest.mark.asyncio
    async def test_unknown_token_alert(self, owner) -> None:
        """An unknown token triggers a failure alert."""
        from telegram_bot.handlers.alerts import handle_unsubscribe_callback

        bot = AsyncMock()

        callback = MagicMock()
        callback.data = f"{BotCallbackPrefix.UNSUB}nonexistent_token_32chars_a"
        callback.from_user = MagicMock(id=owner.chat_id)
        callback.message = MagicMock()
        callback.message.chat = MagicMock(id=owner.chat_id)
        callback.message.message_id = 42
        callback.answer = AsyncMock()

        await handle_unsubscribe_callback(callback, bot)

        callback.answer.assert_awaited_once()
        called_text = callback.answer.call_args[0][0]
        assert "fail" in called_text.lower()

    @pytest.mark.asyncio
    async def test_non_owner_rejected(self, owner, stranger, saved_search) -> None:
        """A non-owner's token triggers a failure alert (no state leak)."""
        from telegram_bot.handlers.alerts import handle_unsubscribe_callback

        bot = AsyncMock()

        callback = MagicMock()
        callback.data = f"{BotCallbackPrefix.UNSUB}{saved_search.unsubscribe_token}"
        callback.from_user = MagicMock(id=stranger.chat_id)
        callback.message = MagicMock()
        callback.message.chat = MagicMock(id=stranger.chat_id)
        callback.message.message_id = 42
        callback.answer = AsyncMock()

        await handle_unsubscribe_callback(callback, bot)

        callback.answer.assert_awaited_once()
        called_text = callback.answer.call_args[0][0]
        assert "fail" in called_text.lower()

        # Verify the search was NOT modified.
        ss = await sync_to_async(SavedSearch.objects.get)(pk=saved_search.pk)
        assert ss.is_active is True


class TestHandleReenableCallback:
    """Tests for ``handle_reenable_callback``."""

    @pytest.mark.asyncio
    async def test_owned_token_reenabled(
        self, owner, saved_search
    ) -> None:
        """An owned re-enable token activates the search and swaps the button."""
        from telegram_bot.handlers.alerts import handle_reenable_callback
        from telegram_bot.schemas.callbacks import BotCallbackPrefix

        # Disable first so re-enable is meaningful.
        await sync_to_async(
            SavedSearch.objects.filter(pk=saved_search.pk).update
        )(is_active=False)

        bot = AsyncMock()

        callback = MagicMock()
        callback.data = f"{BotCallbackPrefix.UNSUB_ON}{saved_search.unsubscribe_token}"
        callback.from_user = MagicMock(id=owner.chat_id)
        callback.message = MagicMock()
        callback.message.chat = MagicMock(id=owner.chat_id)
        callback.message.message_id = 42
        callback.answer = AsyncMock()

        await handle_reenable_callback(callback, bot)

        bot.edit_message_reply_markup.assert_awaited_once()
        callback.answer.assert_awaited_with("Notifications enabled")

        ss = await sync_to_async(SavedSearch.objects.get)(pk=saved_search.pk)
        assert ss.is_active is True

    @pytest.mark.asyncio
    async def test_unknown_token_alert(self, owner) -> None:
        """An unknown re-enable token triggers a failure alert."""
        from telegram_bot.handlers.alerts import handle_reenable_callback
        from telegram_bot.schemas.callbacks import BotCallbackPrefix

        bot = AsyncMock()

        callback = MagicMock()
        callback.data = f"{BotCallbackPrefix.UNSUB_ON}nonexistent_token_32chars_a"
        callback.from_user = MagicMock(id=owner.chat_id)
        callback.message = MagicMock()
        callback.message.chat = MagicMock(id=owner.chat_id)
        callback.message.message_id = 42
        callback.answer = AsyncMock()

        await handle_reenable_callback(callback, bot)

        callback.answer.assert_awaited_once()
        called_text = callback.answer.call_args[0][0]
        assert "fail" in called_text.lower()
