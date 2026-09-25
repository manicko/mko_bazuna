"""
Tests for city-step FSM handler (TST-012).

Covers:
- ``process_city``: no text → prompt, exact match → proceed, no match → error.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.integration,
    pytest.mark.concurrent,
]
pytestmark.append(pytest.mark.xdist_group("bot_concurrent"))


class TestProcessCity:
    """Tests for the city message handler."""

    @pytest.mark.asyncio
    async def test_no_text_prompts(self) -> None:
        """When the message has no text, the bot asks for a city name."""
        from telegram_bot.handlers.ad_create.city import process_city

        state = MagicMock()
        message = MagicMock()
        message.text = None
        message.answer = AsyncMock()

        await process_city(message, state)

        message.answer.assert_awaited_once()
        called_text = message.answer.call_args[0][0]
        assert "city" in called_text.lower() or "name" in called_text.lower()

    @pytest.mark.asyncio
    async def test_exact_match_proceeds(self) -> None:
        """An exact city match updates state and moves to title."""
        from telegram_bot.handlers.ad_create.city import process_city
        from telegram_bot.handlers.ad_create import AdCreateForm

        city = MagicMock(id=10, get_name=MagicMock(return_value="Podgorica"))

        with patch(
            "telegram_bot.handlers.ad_create.city.get_city_by_name",
            new=AsyncMock(return_value=city),
        ):
            state = MagicMock()
            state.update_data = AsyncMock()
            state.set_state = AsyncMock()

            message = MagicMock()
            message.text = "Podgorica"
            message.answer = AsyncMock()

            await process_city(message, state)

        state.update_data.assert_awaited_with(city_id=10)
        state.set_state.assert_awaited_with(AdCreateForm.title)
        message.answer.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_match_shows_error(self) -> None:
        """When no city is found, the bot shows an error message."""
        from telegram_bot.handlers.ad_create.city import process_city

        with patch(
            "telegram_bot.handlers.ad_create.city.get_city_by_name",
            new=AsyncMock(return_value=None),
        ):
            with patch(
                "telegram_bot.handlers.ad_create.city.get_all_cities",
                new=AsyncMock(return_value=[]),
            ):
                state = MagicMock()
                message = MagicMock()
                message.text = "Nonexistent"
                message.answer = AsyncMock()

                await process_city(message, state)

        message.answer.assert_awaited_once()
        called_text = message.answer.call_args[0][0]
        assert "not found" in called_text.lower() or "exact" in called_text.lower()

    @pytest.mark.asyncio
    async def test_close_match_used(self) -> None:
        """When exact match fails but a close match exists, it is used."""
        from telegram_bot.handlers.ad_create.city import process_city
        from telegram_bot.handlers.ad_create import AdCreateForm

        city = MagicMock(id=15, get_name=MagicMock(return_value="Podgorica"))

        async def fake_get_city_by_name(name: str):
            if name == "Podgoric":
                return None
            return city

        with patch(
            "telegram_bot.handlers.ad_create.city.get_city_by_name",
            new=AsyncMock(side_effect=fake_get_city_by_name),
        ):
            with patch(
                "telegram_bot.handlers.ad_create.city.get_all_cities",
                new=AsyncMock(
                    return_value=[MagicMock(get_name=MagicMock(return_value="Podgorica"))]
                ),
            ):
                state = MagicMock()
                state.update_data = AsyncMock()
                state.set_state = AsyncMock()

                message = MagicMock()
                message.text = "Podgoric"
                message.answer = AsyncMock()

                await process_city(message, state)

        state.update_data.assert_awaited_with(city_id=15)
        state.set_state.assert_awaited_with(AdCreateForm.title)
