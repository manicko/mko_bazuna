"""
Unit tests for ``_format_preview_price`` in the ad-creation FSM handler.

``RedisStorage`` serializes FSM data via ``json.dumps``, which returns plain
``str`` for ``StrEnum`` members on deserialization. These tests lock in the
``str(currency)`` fix (instead of ``currency.value``) so that the preview
formatter handles both ``CurrencyCode`` (enum, MemoryStorage) and plain
``str`` (Redis-deserialized) inputs without ``AttributeError``.

All tests are pure unit tests — no database, no Redis, no bot runtime.
"""

from decimal import Decimal

import pytest

from apps.currencies.enums import CurrencyCode
from telegram_bot.handlers.ad_create import _format_preview_price

pytestmark = [pytest.mark.unit]


class TestFormatPreviewPrice:
    """Verify ``_format_preview_price`` handles enum, str, and None currency."""

    def test_format_preview_price_with_enum(self) -> None:
        """CurrencyCode.StrEnum input (MemoryStorage scenario) — str(enum) == enum.value."""
        data = {"price_amount": Decimal("99.99"), "price_currency": CurrencyCode.EUR}
        assert _format_preview_price(data) == "99.99 EUR"

    def test_format_preview_price_with_string(self) -> None:
        """Plain str input (Redis deserialized scenario) — str(str) == str."""
        data = {"price_amount": Decimal("99.99"), "price_currency": "EUR"}
        assert _format_preview_price(data) == "99.99 EUR"

    def test_format_preview_price_with_none_currency(self) -> None:
        """Missing price_currency key — output has no currency label."""
        data = {"price_amount": Decimal("99.99")}
        assert _format_preview_price(data) == "99.99"

    def test_format_preview_price_with_none_amount(self) -> None:
        """Missing price_amount key — returns the gettext msgid 'N/A'."""
        data: dict = {}
        assert _format_preview_price(data) == "N/A"
