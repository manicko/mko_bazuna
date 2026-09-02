"""
Tests for PricePayload schema validation and the bot's Free-price callback path.

T-15 regression: the bot no longer offers a "Skip" option for price. A Free/Charity
ad enters ``Decimal("0")`` explicitly via the ``price_free`` callback. ``price_skip``
has been fully removed; ``price_free`` replaces it (verified in
``telegram_bot/handlers/ad_create.py``).

These tests verify:

- ``PricePayload(price_amount=None)`` raises ``ValidationError`` (Skip is gone).
- ``PricePayload(price_amount=Decimal("0"))`` succeeds, defaulting to EUR.
- The ``price_free`` callback_query in ``process_price_currency`` sets
  ``price_amount=0`` / ``price_currency=EUR`` and advances the FSM to photos.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from pydantic import ValidationError

from apps.currencies.enums import CurrencyCode
from telegram_bot.schemas.message_payloads import PricePayload

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.slow,
    pytest.mark.integration,
    pytest.mark.concurrent,
]
pytestmark.append(pytest.mark.xdist_group("bot_concurrent"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def fsm_context() -> FSMContext:
    """A real FSMContext over in-memory storage (exercises real state I/O)."""
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=1, thread_id=0)
    return FSMContext(storage=storage, key=key)


def _mock_callback(data: str) -> MagicMock:
    """Build a CallbackQuery double suitable for ``process_price_currency``."""
    callback = MagicMock()
    callback.data = data
    callback.message = MagicMock()
    callback.message.answer = AsyncMock()
    callback.answer = AsyncMock()
    return callback


# ---------------------------------------------------------------------------
# PricePayload validation — pure unit tests
# ---------------------------------------------------------------------------


class TestPricePayloadValidation:
    """PricePayload rejects None (Skip removed) and accepts zero (Free)."""

    def test_price_payload_none_raises(self) -> None:
        """``PricePayload(price_amount=None)`` must raise ``ValidationError``.

        The bot no longer offers a "Skip" price option; a Free/Charity ad
        enters ``Decimal("0")`` explicitly. ``None`` is rejected at schema
        validation time.
        """
        with pytest.raises(ValidationError):
            PricePayload(price_amount=None)

    def test_price_payload_zero_succeeds(self) -> None:
        """``PricePayload(price_amount=Decimal("0"))`` succeeds for Free ads."""
        payload = PricePayload(price_amount=Decimal("0"))
        assert payload.price_amount == Decimal("0")
        assert payload.price_currency == CurrencyCode.EUR

    def test_price_payload_default_currency_is_eur(self) -> None:
        """Omitting ``price_currency`` defaults to EUR."""
        payload = PricePayload(price_amount=Decimal("10"))
        assert payload.price_currency == CurrencyCode.EUR

    def test_price_payload_positive_with_explicit_currency(self) -> None:
        """A positive amount with an explicit currency validates correctly."""
        payload = PricePayload(
            price_amount=Decimal("99.99"),
            price_currency=CurrencyCode.RSD,
        )
        assert payload.price_amount == Decimal("99.99")
        assert payload.price_currency == CurrencyCode.RSD

    def test_price_payload_negative_raises(self) -> None:
        """Negative amounts violate the ``ge=0`` constraint."""
        with pytest.raises(ValidationError):
            PricePayload(price_amount=Decimal("-1"))


# ---------------------------------------------------------------------------
# Free-path FSM callback_query — exercises ``process_price_currency``
# ---------------------------------------------------------------------------


class TestFreePriceCallbackPath:
    """``price_free`` callback sets price_amount=0/EUR and advances to photos."""

    @pytest.mark.asyncio
    async def test_price_free_sets_zero_amount_and_advances_to_photos(
        self, fsm_context: FSMContext
    ) -> None:
        """Selecting 'Free' persists price 0/EUR and moves FSM to the photos step."""
        from telegram_bot.handlers.ad_create import AdCreateForm, process_price_currency

        await fsm_context.set_state(AdCreateForm.price)

        callback = _mock_callback("price_free")

        await process_price_currency(callback, fsm_context)

        data = await fsm_context.get_data()
        assert data["price_amount"] == Decimal("0.00")
        assert data["price_currency"] == CurrencyCode.EUR

        assert await fsm_context.get_state() == AdCreateForm.photos
