"""
Tests for text-step FSM handlers (TST-012).

Covers:
- ``process_title``: no text → prompt, valid title → save + advance,
  invalid title → error.
- ``process_description``: no text → prompt, valid description → save + advance,
  invalid description → error.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.handlers.ad_create import AdCreateForm

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.integration,
    pytest.mark.concurrent,
]
pytestmark.append(pytest.mark.xdist_group("bot_concurrent"))


class TestProcessTitle:
    """Tests for the title message handler."""

    @pytest.mark.asyncio
    async def test_no_text_prompts(self) -> None:
        """When the message has no text, the bot asks for the title."""
        from telegram_bot.handlers.ad_create.text import process_title

        state = MagicMock()
        state.get_data = AsyncMock(return_value={})
        message = MagicMock()
        message.text = None
        message.answer = AsyncMock()

        await process_title(message, state)

        message.answer.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_valid_title_advances(self) -> None:
        """A valid title saves to state and moves to description."""
        from telegram_bot.handlers.ad_create.text import process_title

        state = MagicMock()
        state.get_data = AsyncMock(return_value={})
        state.update_data = AsyncMock()
        state.set_state = AsyncMock()

        message = MagicMock()
        message.text = "A valid ad title"
        message.answer = AsyncMock()

        await process_title(message, state)

        state.update_data.assert_awaited_with(title="A valid ad title")
        state.set_state.assert_awaited_with(AdCreateForm.description)
        message.answer.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalid_title_shows_error(self) -> None:
        """A title that fails Pydantic validation shows an error message."""
        from telegram_bot.handlers.ad_create.text import process_title

        state = MagicMock()
        state.get_data = AsyncMock(return_value={})
        message = MagicMock()
        message.text = "x" * 300  # exceeds max length
        message.answer = AsyncMock()

        with patch(
            "telegram_bot.handlers.ad_create.text.TitlePayload",
            side_effect=ValueError("too long"),
        ):
            await process_title(message, state)

        message.answer.assert_awaited_once()
        called_text = message.answer.call_args[0][0]
        assert "invalid" in called_text.lower()


class TestProcessDescription:
    """Tests for the description message handler."""

    @pytest.mark.asyncio
    async def test_no_text_prompts(self) -> None:
        """When the message has no text, the bot asks for the description."""
        from telegram_bot.handlers.ad_create.text import process_description

        state = MagicMock()
        state.get_data = AsyncMock(return_value={})
        message = MagicMock()
        message.text = None
        message.answer = AsyncMock()

        await process_description(message, state)

        message.answer.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_valid_description_advances(self) -> None:
        """A valid description saves to state and moves to price."""
        from telegram_bot.handlers.ad_create.text import process_description

        state = MagicMock()
        state.get_data = AsyncMock(return_value={})
        state.update_data = AsyncMock()
        state.set_state = AsyncMock()

        message = MagicMock()
        message.text = "A valid description for the ad."
        message.answer = AsyncMock()

        await process_description(message, state)

        state.update_data.assert_awaited_with(description="A valid description for the ad.")
        state.set_state.assert_awaited_with(AdCreateForm.price)
        message.answer.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalid_description_shows_error(self) -> None:
        """A description that fails Pydantic validation shows an error."""
        from telegram_bot.handlers.ad_create.text import process_description

        state = MagicMock()
        state.get_data = AsyncMock(return_value={})
        message = MagicMock()
        message.text = "x" * 3000  # exceeds max length
        message.answer = AsyncMock()

        with patch(
            "telegram_bot.handlers.ad_create.text.DescriptionPayload",
            side_effect=ValueError("too long"),
        ):
            await process_description(message, state)

        message.answer.assert_awaited_once()
        called_text = message.answer.call_args[0][0]
        assert "invalid" in called_text.lower()
