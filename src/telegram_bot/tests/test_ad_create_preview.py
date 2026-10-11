"""
Unit tests for the ad-creation preview step handlers.

``_format_preview_price`` tests lock in the ``str(currency)`` fix (instead of
``currency.value``) so that the preview formatter handles both ``CurrencyCode``
(enum, MemoryStorage) and plain ``str`` (Redis-deserialized) inputs without
``AttributeError``.

``show_preview`` tests cover the full preview assembly with mocked lookup
services — no database, no Redis, no bot runtime.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.categories.models import Category
from apps.currencies.enums import CurrencyCode
from apps.locations.models import City
from apps.lookups.models import LookupItem
from telegram_bot.handlers.ad_create import _format_preview_price, show_preview

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


class TestShowPreview:
    """Tests for the ``show_preview`` ad-creation preview handler."""

    @pytest.mark.asyncio
    async def test_show_preview_with_complete_data(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """All IDs provided — preview text contains every value."""
        cat = MagicMock(spec=Category)
        cat.get_name.return_value = "Bicycles"

        city = MagicMock(spec=City)
        city.get_name.return_value = "Belgrade"

        purpose = MagicMock(spec=LookupItem)
        purpose.get_name.return_value = "For Sale"

        condition = MagicMock(spec=LookupItem)
        condition.get_name.return_value = "New"

        monkeypatch.setattr(
            "telegram_bot.handlers.ad_create.preview.get_category",
            AsyncMock(return_value=cat),
        )
        monkeypatch.setattr(
            "telegram_bot.handlers.ad_create.preview.get_city",
            AsyncMock(return_value=city),
        )
        monkeypatch.setattr(
            "telegram_bot.handlers.ad_create.preview.get_lookup_item",
            AsyncMock(side_effect=[purpose, condition]),
        )
        monkeypatch.setattr(
            "telegram_bot.handlers.ad_create.preview.get_feature_names",
            AsyncMock(return_value=["Spoiler", "Leather seats"]),
        )

        message = MagicMock()
        message.answer = AsyncMock()

        data = {
            "title": "Red bicycle",
            "description": "A red bicycle for sale",
            "price_amount": Decimal("99.99"),
            "price_currency": CurrencyCode.EUR,
            "category_id": 1,
            "city_id": 2,
            "listing_purpose_id": 3,
            "condition_id": 4,
            "feature_ids": [5, 6],
        }

        await show_preview(message, data)

        message.answer.assert_awaited_once()
        called_text = message.answer.call_args[0][0]
        assert "Red bicycle" in called_text
        assert "Bicycles" in called_text
        assert "Belgrade" in called_text
        assert "For Sale" in called_text
        assert "New" in called_text
        assert "Spoiler" in called_text
        assert "Leather seats" in called_text
        assert "99.99 EUR" in called_text

    @pytest.mark.asyncio
    async def test_show_preview_with_none_ids(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """None IDs produce 'N/A' fallbacks for category, city, purpose, condition."""
        monkeypatch.setattr(
            "telegram_bot.handlers.ad_create.preview.get_category",
            AsyncMock(return_value=None),
        )
        monkeypatch.setattr(
            "telegram_bot.handlers.ad_create.preview.get_city",
            AsyncMock(return_value=None),
        )
        monkeypatch.setattr(
            "telegram_bot.handlers.ad_create.preview.get_lookup_item",
            AsyncMock(return_value=None),
        )

        message = MagicMock()
        message.answer = AsyncMock()

        data = {
            "title": "Test Ad",
            "description": "Test description",
            "price_amount": Decimal("100.00"),
            "price_currency": CurrencyCode.EUR,
            "category_id": None,
            "city_id": None,
            "listing_purpose_id": None,
            "condition_id": None,
            "feature_ids": [],
        }

        await show_preview(message, data)

        message.answer.assert_awaited_once()
        called_text = message.answer.call_args[0][0]
        # category, city, purpose, condition all fall back to "N/A"
        assert called_text.count("N/A") == 4
        assert "100.00 EUR" in called_text

    @pytest.mark.asyncio
    async def test_show_preview_with_no_features(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty feature_ids shows 'None' for the features field."""
        cat = MagicMock(spec=Category)
        cat.get_name.return_value = "Bicycles"

        city = MagicMock(spec=City)
        city.get_name.return_value = "Belgrade"

        purpose = MagicMock(spec=LookupItem)
        purpose.get_name.return_value = "For Sale"

        condition = MagicMock(spec=LookupItem)
        condition.get_name.return_value = "New"

        monkeypatch.setattr(
            "telegram_bot.handlers.ad_create.preview.get_category",
            AsyncMock(return_value=cat),
        )
        monkeypatch.setattr(
            "telegram_bot.handlers.ad_create.preview.get_city",
            AsyncMock(return_value=city),
        )
        monkeypatch.setattr(
            "telegram_bot.handlers.ad_create.preview.get_lookup_item",
            AsyncMock(side_effect=[purpose, condition]),
        )
        get_feature_names_mock = AsyncMock()
        monkeypatch.setattr(
            "telegram_bot.handlers.ad_create.preview.get_feature_names",
            get_feature_names_mock,
        )

        message = MagicMock()
        message.answer = AsyncMock()

        data = {
            "title": "Test Ad",
            "description": "Test description",
            "price_amount": Decimal("100.00"),
            "price_currency": CurrencyCode.EUR,
            "category_id": 1,
            "city_id": 2,
            "listing_purpose_id": 3,
            "condition_id": 4,
            "feature_ids": [],
        }

        await show_preview(message, data)

        get_feature_names_mock.assert_not_awaited()
        message.answer.assert_awaited_once()
        called_text = message.answer.call_args[0][0]
        assert "Features: None" in called_text

    @pytest.mark.asyncio
    async def test_show_preview_with_missing_price(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Missing price_amount → 'N/A' price in the preview."""
        cat = MagicMock(spec=Category)
        cat.get_name.return_value = "Bicycles"

        city = MagicMock(spec=City)
        city.get_name.return_value = "Belgrade"

        purpose = MagicMock(spec=LookupItem)
        purpose.get_name.return_value = "For Sale"

        condition = MagicMock(spec=LookupItem)
        condition.get_name.return_value = "New"

        monkeypatch.setattr(
            "telegram_bot.handlers.ad_create.preview.get_category",
            AsyncMock(return_value=cat),
        )
        monkeypatch.setattr(
            "telegram_bot.handlers.ad_create.preview.get_city",
            AsyncMock(return_value=city),
        )
        monkeypatch.setattr(
            "telegram_bot.handlers.ad_create.preview.get_lookup_item",
            AsyncMock(side_effect=[purpose, condition]),
        )
        monkeypatch.setattr(
            "telegram_bot.handlers.ad_create.preview.get_feature_names",
            AsyncMock(return_value=["Spoiler"]),
        )

        message = MagicMock()
        message.answer = AsyncMock()

        data = {
            "title": "Test Ad",
            "description": "Test description",
            "category_id": 1,
            "city_id": 2,
            "listing_purpose_id": 3,
            "condition_id": 4,
            "feature_ids": [5],
        }

        await show_preview(message, data)

        message.answer.assert_awaited_once()
        called_text = message.answer.call_args[0][0]
        assert "Price: N/A" in called_text
