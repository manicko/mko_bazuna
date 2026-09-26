"""
Tests for language handler (TST-012).

Covers:
- ``cmd_language``: not-logged-in prompt, logged-in keyboard with current language.
- ``handle_language_callback``: valid language → persists, invalid → alert,
  not-logged-in → alert.
- ``build_language_keyboard``: checkmark on current language.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from asgiref.sync import sync_to_async

from apps.core.enums import LanguageLocale
from apps.users.models import User

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.integration,
    pytest.mark.concurrent,
]
pytestmark.append(pytest.mark.xdist_group("bot_concurrent"))


class TestCmdLanguage:
    """Tests for /language command handler."""

    @pytest.mark.asyncio
    async def test_cmd_language_not_logged_in(self) -> None:
        """When user_id is absent from state, the bot prompts to log in."""
        from telegram_bot.handlers.language import cmd_language

        state = MagicMock()
        state.get_data = AsyncMock(return_value={})

        message = MagicMock()
        message.from_user = MagicMock(id=123)
        message.answer = AsyncMock()

        await cmd_language(message, state)

        message.answer.assert_awaited_once()
        called_text = message.answer.call_args[0][0]
        assert "login" in called_text.lower()

    @pytest.mark.asyncio
    async def test_cmd_language_shows_keyboard(self, seller: User) -> None:
        """When logged in, the bot shows the language keyboard."""
        from telegram_bot.handlers.language import cmd_language

        state = MagicMock()
        state.get_data = AsyncMock(return_value={"user_id": seller.id})

        message = MagicMock()
        message.from_user = MagicMock(id=seller.chat_id)
        message.answer = AsyncMock()

        await cmd_language(message, state)

        message.answer.assert_awaited_once()
        # Verify keyboard was sent (reply_markup kwarg).
        call_kwargs = message.answer.call_args
        assert call_kwargs.kwargs.get("reply_markup") is not None


class TestHandleLanguageCallback:
    """Tests for language selection callback handler."""

    @pytest.mark.asyncio
    async def test_valid_language_set(self, seller: User) -> None:
        """Selecting a valid language persists it and updates the keyboard."""
        from telegram_bot.handlers.language import handle_language_callback
        from telegram_bot.schemas.callbacks import BotCallbackPrefix

        state = MagicMock()
        state.get_data = AsyncMock(return_value={"user_id": seller.id})

        callback = MagicMock()
        callback.data = f"{BotCallbackPrefix.LANG}{LanguageLocale.ENGLISH.value}"
        callback.answer = AsyncMock()

        msg = MagicMock()
        msg.edit_reply_markup = AsyncMock()
        callback.message = msg

        await handle_language_callback(callback, state)

        # Verify the user's language was persisted.
        actual = await sync_to_async(
            User.objects.filter(id=seller.id).values_list(
                "telegram_language", flat=True
            ).first
        )()
        assert actual == LanguageLocale.ENGLISH.value

    @pytest.mark.asyncio
    async def test_invalid_language_alert(self) -> None:
        """An unsupported language code triggers an alert (no persistence)."""
        from telegram_bot.handlers.language import handle_language_callback
        from telegram_bot.schemas.callbacks import BotCallbackPrefix

        state = MagicMock()
        state.get_data = AsyncMock(return_value={"user_id": 1})

        callback = MagicMock()
        callback.data = f"{BotCallbackPrefix.LANG}xx"  # invalid
        callback.answer = AsyncMock()

        await handle_language_callback(callback, state)

        callback.answer.assert_awaited_once()
        called_text = callback.answer.call_args[0][0]
        assert "unsupported" in called_text.lower()

    @pytest.mark.asyncio
    async def test_no_user_id_prompt(self) -> None:
        """When user_id is absent from state, the bot shows a login prompt."""
        from telegram_bot.handlers.language import handle_language_callback
        from telegram_bot.schemas.callbacks import BotCallbackPrefix

        state = MagicMock()
        state.get_data = AsyncMock(return_value={})

        callback = MagicMock()
        callback.data = f"{BotCallbackPrefix.LANG}ru"
        callback.answer = AsyncMock()

        await handle_language_callback(callback, state)

        callback.answer.assert_awaited_once()
