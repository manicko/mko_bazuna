"""
Tests for price-step FSM handlers (TST-012).

Covers:
- ``process_price_currency``: free → zero EUR + advance,
  valid currency → set currency + prompt amount,
  invalid currency → alert.
- ``process_price``: no currency set → re-prompt,
  no text → prompt, valid amount → save, invalid amount → error.
- ``_move_from_price_to_photos``: advances to photos state.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.currencies.enums import CurrencyCode
from telegram_bot.handlers.ad_create import AdCreateForm
from telegram_bot.schemas.callbacks import BotCallbackPrefix

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.integration,
    pytest.mark.concurrent,
]
pytestmark.append(pytest.mark.xdist_group("bot_concurrent"))


class TestProcessPriceCurrency:
    """Tests for the price-currency callback handler."""

    @pytest.mark.asyncio
    async def test_free_advances_to_photos(self) -> None:
        """Selecting 'Free' sets zero EUR and advances to photos."""
        from telegram_bot.handlers.ad_create.price import process_price_currency

        state = MagicMock()
        state.update_data = AsyncMock()

        callback = MagicMock()
        callback.data = BotCallbackPrefix.PRICE_FREE
        callback.answer = AsyncMock()
        callback.message = MagicMock()
        callback.message.answer = AsyncMock()

        with patch(
            "telegram_bot.handlers.ad_create.price._move_from_price_to_photos",
            new=AsyncMock(),
        ):
            await process_price_currency(callback, state)

        state.update_data.assert_awaited_with(
            price_amount=Decimal("0.00"),
            price_currency=CurrencyCode.EUR,
        )

    @pytest.mark.asyncio
    async def test_valid_currency_prompts_amount(self) -> None:
        """A valid currency sets it and prompts for the amount."""
        from telegram_bot.handlers.ad_create.price import process_price_currency

        state = MagicMock()
        state.update_data = AsyncMock()

        callback = MagicMock()
        callback.data = f"{BotCallbackPrefix.PRICE_CURRENCY}EUR"
        callback.answer = AsyncMock()
        callback.message = MagicMock()
        callback.message.answer = AsyncMock()

        await process_price_currency(callback, state)

        state.update_data.assert_awaited_with(price_currency=CurrencyCode.EUR)
        callback.message.answer.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalid_currency_alert(self) -> None:
        """An unrecognized currency triggers an alert."""
        from telegram_bot.handlers.ad_create.price import process_price_currency

        state = MagicMock()

        callback = MagicMock()
        callback.data = f"{BotCallbackPrefix.PRICE_CURRENCY}xx"
        callback.answer = AsyncMock()
        callback.message = MagicMock()

        await process_price_currency(callback, state)

        callback.answer.assert_awaited_once()
        assert callback.answer.call_args.kwargs.get("show_alert") is True


class TestProcessPrice:
    """Tests for the price amount message handler."""

    @pytest.mark.asyncio
    async def test_no_currency_set_reprompts(self) -> None:
        """When no currency is in state, the bot shows the currency keyboard."""
        from telegram_bot.handlers.ad_create.price import process_price

        with patch(
            "telegram_bot.handlers.ad_create.price.build_currency_keyboard",
            return_value=MagicMock(),
        ):
            state = MagicMock()
            state.get_data = AsyncMock(return_value={})

            message = MagicMock()
            message.text = "100"
            message.answer = AsyncMock()

            await process_price(message, state)

        message.answer.assert_awaited_once()
        call_kwargs = message.answer.call_args
        assert call_kwargs.kwargs.get("reply_markup") is not None

    @pytest.mark.asyncio
    async def test_no_text_prompts(self) -> None:
        """When the message has no text, the bot asks for the price."""
        from telegram_bot.handlers.ad_create.price import process_price

        state = MagicMock()
        state.get_data = AsyncMock(
            return_value={"price_currency": CurrencyCode.EUR}
        )

        message = MagicMock()
        message.text = None
        message.answer = AsyncMock()

        await process_price(message, state)

        message.answer.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_valid_amount_advances(self) -> None:
        """A valid numeric price saves and advances to photos."""
        from telegram_bot.handlers.ad_create.price import process_price

        state = MagicMock()
        state.update_data = AsyncMock()
        state.get_data = AsyncMock(
            return_value={"price_currency": CurrencyCode.EUR}
        )

        message = MagicMock()
        message.text = "42.50"
        message.answer = AsyncMock()

        with patch(
            "telegram_bot.handlers.ad_create.price._move_from_price_to_photos",
            new=AsyncMock(),
        ):
            await process_price(message, state)

        state.update_data.assert_awaited_with(
            price_amount=Decimal("42.50")
        )

    @pytest.mark.asyncio
    async def test_invalid_amount_shows_error(self) -> None:
        """A non-numeric price triggers an error message."""
        from telegram_bot.handlers.ad_create.price import process_price

        state = MagicMock()
        state.get_data = AsyncMock(
            return_value={"price_currency": CurrencyCode.EUR}
        )

        message = MagicMock()
        message.text = "not a number"
        message.answer = AsyncMock()

        with patch(
            "telegram_bot.handlers.ad_create.price._move_from_price_to_photos",
            new=AsyncMock(),
        ):
            await process_price(message, state)

        message.answer.assert_awaited_once()
        called_text = message.answer.call_args[0][0]
        assert "invalid" in called_text.lower()


class TestMoveFromPriceToPhotos:
    """Tests for the price → photos transition helper."""

    @pytest.mark.asyncio
    async def test_advances_to_photos(self) -> None:
        """The helper sets the state to ``photos`` and prompts for images."""
        from telegram_bot.handlers.ad_create.price import _move_from_price_to_photos

        state = MagicMock()
        state.set_state = AsyncMock()

        message = MagicMock()
        message.answer = AsyncMock()

        await _move_from_price_to_photos(message, state)

        state.set_state.assert_awaited_with(AdCreateForm.photos)
        message.answer.assert_awaited_once()
