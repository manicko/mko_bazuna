"""
Tests for ad copy handler (TST-012).

Covers:
- ``cmd_copy``: success with valid ad ID, permission error, no argument,
  invalid ad ID, unexpected error.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.utils import timezone

from apps.ads.models import Ad
from apps.currencies.enums import CurrencyCode

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.integration,
    pytest.mark.concurrent,
]
pytestmark.append(pytest.mark.xdist_group("bot_concurrent"))


@pytest.fixture
def source_ad(seller, category, city, db):
    """Create a published ad owned by ``seller``."""
    return Ad.objects.create(
        user=seller,
        category=category,
        city=city,
        title="Source ad for copy",
        description="Original description",
        price_amount=Decimal("10.00"),
        price_currency=CurrencyCode.EUR,
        published_at=timezone.now(),
        status="published",
    )


class TestCmdCopy:
    """Tests for /copy command handler."""

    @pytest.mark.asyncio
    async def test_copy_success(self, seller, source_ad) -> None:
        """Copying a valid ad creates a draft owned by the caller."""
        from telegram_bot.handlers.ad_copy import cmd_copy

        state = MagicMock()
        state.get_data = AsyncMock(return_value={"user_id": seller.id})
        state.set_state = AsyncMock()
        state.update_data = AsyncMock()

        message = MagicMock()
        message.from_user = MagicMock(id=seller.chat_id)
        message.text = f"/copy {source_ad.id}"
        message.answer = AsyncMock()

        mock_new_ad = MagicMock(
            id=999,
            category_id=source_ad.category_id,
            listing_purpose_id=1,
            get_title=MagicMock(return_value="Copied title"),
            get_description=MagicMock(return_value="Copied desc"),
            category=MagicMock(get_name=MagicMock(return_value="Test Category")),
        )

        with patch(
            "telegram_bot.handlers.ad_copy.copy_ad",
            new=MagicMock(return_value=mock_new_ad),
        ):
            await cmd_copy(message, state)

        state.set_state.assert_awaited_once()
        message.answer.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_copy_no_argument(self, seller) -> None:
        """When no ad ID is provided, the bot shows usage instructions."""
        from telegram_bot.handlers.ad_copy import cmd_copy

        state = MagicMock()
        state.get_data = AsyncMock(return_value={"user_id": seller.id})

        message = MagicMock()
        message.from_user = MagicMock(id=seller.chat_id)
        message.text = "/copy"
        message.answer = AsyncMock()

        await cmd_copy(message, state)

        message.answer.assert_awaited_once()
        called_text = message.answer.call_args[0][0]
        assert "/copy" in called_text

    @pytest.mark.asyncio
    async def test_copy_invalid_id_format(self, seller) -> None:
        """A non-numeric ad ID triggers an error message."""
        from telegram_bot.handlers.ad_copy import cmd_copy

        state = MagicMock()
        state.get_data = AsyncMock(return_value={"user_id": seller.id})

        message = MagicMock()
        message.from_user = MagicMock(id=seller.chat_id)
        message.text = "/copy notanumber"
        message.answer = AsyncMock()

        await cmd_copy(message, state)

        message.answer.assert_awaited_once()
        called_text = message.answer.call_args[0][0]
        assert "invalid" in called_text.lower() or "ad id" in called_text.lower()

    @pytest.mark.asyncio
    async def test_copy_permission_error(self, seller, source_ad) -> None:
        """Copying an ad the user doesn't own shows a permission error."""
        from telegram_bot.handlers.ad_copy import cmd_copy

        state = MagicMock()
        state.get_data = AsyncMock(return_value={"user_id": seller.id})

        message = MagicMock()
        message.from_user = MagicMock(id=950000999)
        message.text = f"/copy {source_ad.id}"
        message.answer = AsyncMock()

        with patch(
            "telegram_bot.handlers.ad_copy.copy_ad",
            new=MagicMock(side_effect=PermissionError("not the owner")),
        ):
            await cmd_copy(message, state)

        message.answer.assert_awaited_once()
        called_text = message.answer.call_args[0][0]
        assert "only copy" in called_text.lower() or "own" in called_text.lower()

    @pytest.mark.asyncio
    async def test_copy_unexpected_error(self, seller, source_ad) -> None:
        """An unexpected exception yields a generic error message."""
        from telegram_bot.handlers.ad_copy import cmd_copy

        state = MagicMock()
        state.get_data = AsyncMock(return_value={"user_id": seller.id})

        message = MagicMock()
        message.from_user = MagicMock(id=seller.chat_id)
        message.text = f"/copy {source_ad.id}"
        message.answer = AsyncMock()

        with patch(
            "telegram_bot.handlers.ad_copy.copy_ad",
            new=MagicMock(side_effect=ValueError("unexpected")),
        ):
            await cmd_copy(message, state)

        message.answer.assert_awaited_once()
        called_text = message.answer.call_args[0][0]
        assert "failed" in called_text.lower()

    @pytest.mark.asyncio
    async def test_copy_not_logged_in(self) -> None:
        """When user_id is absent from state, the bot prompts to log in."""
        from telegram_bot.handlers.ad_copy import cmd_copy

        state = MagicMock()
        state.get_data = AsyncMock(return_value={})

        message = MagicMock()
        message.from_user = MagicMock(id=123)
        message.text = "/copy 1"
        message.answer = AsyncMock()

        await cmd_copy(message, state)

        message.answer.assert_awaited_once()
        called_text = message.answer.call_args[0][0]
        assert "login" in called_text.lower()
