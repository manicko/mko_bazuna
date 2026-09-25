"""
Tests for category-step FSM handlers (TST-012).

Covers:
- ``process_category``: no text → prompt, single match → auto-select,
  no matches → fallback message, multiple matches → suggestions list.
- ``process_purpose``: valid callback → proceed to features/city,
  unknown slug → alert.
- ``process_condition``: valid callback → proceed to features/city,
  unknown slug → alert.
- ``process_features``: ``FEATURES_DONE`` → advance to city,
  feature toggle → update selection + keyboard.
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


class TestProcessCategory:
    """Tests for the category message handler."""

    @pytest.mark.asyncio
    async def test_no_text_prompts(self) -> None:
        """When the message has no text, the bot asks for a keyword."""
        from telegram_bot.handlers.ad_create.category import process_category

        state = MagicMock()
        message = MagicMock()
        message.text = None
        message.answer = AsyncMock()

        await process_category(message, state)

        message.answer.assert_awaited_once()
        called_text = message.answer.call_args[0][0]
        assert "keyword" in called_text.lower() or "category" in called_text.lower()

    @pytest.mark.asyncio
    async def test_single_match_auto_selects(self) -> None:
        """A single search result auto-selects and proceeds."""
        from telegram_bot.handlers.ad_create.category import process_category

        category = MagicMock(id=42)

        with patch(
            "telegram_bot.handlers.ad_create.category.search_categories",
            new=AsyncMock(return_value=[category]),
        ):
            state = MagicMock()
            state.update_data = AsyncMock()
            state.set_state = AsyncMock()

            message = MagicMock()
            message.text = "electronics"
            message.answer = AsyncMock()

            with patch(
                "telegram_bot.handlers.ad_create.category.process_category_selected",
                new=AsyncMock(),
            ):
                await process_category(message, state)

        state.update_data.assert_awaited_with(category_id=42)

    @pytest.mark.asyncio
    async def test_no_matches_shows_fallback(self) -> None:
        """When search returns no results, the bot shows fallback message."""
        with patch(
            "telegram_bot.handlers.ad_create.category.search_categories",
            new=AsyncMock(return_value=[]),
        ):
            state = MagicMock()
            message = MagicMock()
            message.text = "xyz"
            message.answer = AsyncMock()

            from telegram_bot.handlers.ad_create.category import process_category

            await process_category(message, state)

        message.answer.assert_awaited_once()
        called_text = message.answer.call_args[0][0]
        assert "no categories" in called_text.lower() or "try" in called_text.lower()

    @pytest.mark.asyncio
    async def test_multiple_matches_shows_suggestions(self) -> None:
        """When multiple results are found, the bot shows numbered suggestions."""
        cat1 = MagicMock(id=1)
        cat1.get_name.return_value = "Electronics"
        cat2 = MagicMock(id=2)
        cat2.get_name.return_value = "Electronics Store"

        with patch(
            "telegram_bot.handlers.ad_create.category.search_categories",
            new=AsyncMock(return_value=[cat1, cat2]),
        ):
            state = MagicMock()
            message = MagicMock()
            message.text = "electro"
            message.answer = AsyncMock()

            from telegram_bot.handlers.ad_create.category import process_category

            await process_category(message, state)

        message.answer.assert_awaited_once()
        called_text = message.answer.call_args[0][0]
        assert "1. Electronics" in called_text
        assert "2. Electronics Store" in called_text


class TestProcessPurpose:
    """Tests for the purpose callback handler."""

    @pytest.mark.asyncio
    async def test_valid_purpose_proceeds(self) -> None:
        """A valid purpose slug updates state and proceeds."""
        from telegram_bot.handlers.ad_create.category import process_purpose
        from telegram_bot.schemas.callbacks import BotCallbackPrefix

        purpose = MagicMock(id=7, slug="sell")

        with patch(
            "telegram_bot.handlers.ad_create.category.get_lookup_item_by_slug",
            new=AsyncMock(return_value=purpose),
        ):
            state = MagicMock()
            state.update_data = AsyncMock()
            state.get_data = AsyncMock(return_value={"category_id": 42})

            callback = MagicMock()
            callback.data = f"{BotCallbackPrefix.PURPOSE}sell"
            callback.message = MagicMock()
            callback.answer = AsyncMock()

            with patch(
                "telegram_bot.handlers.ad_create.category.proceed_to_features_or_city",
                new=AsyncMock(),
            ):
                await process_purpose(callback, state)

        state.update_data.assert_awaited_with(listing_purpose_id=7)

    @pytest.mark.asyncio
    async def test_unknown_purpose_alert(self) -> None:
        """An unrecognized slug triggers an alert."""
        from telegram_bot.handlers.ad_create.category import process_purpose
        from telegram_bot.schemas.callbacks import BotCallbackPrefix

        with patch(
            "telegram_bot.handlers.ad_create.category.get_lookup_item_by_slug",
            new=AsyncMock(return_value=None),
        ):
            state = MagicMock()
            callback = MagicMock()
            callback.data = f"{BotCallbackPrefix.PURPOSE}unknown"
            callback.answer = AsyncMock()

            await process_purpose(callback, state)

        callback.answer.assert_awaited_once()
        called_text = callback.answer.call_args[0][0]
        assert "not found" in called_text.lower()


class TestProcessCondition:
    """Tests for the condition callback handler."""

    @pytest.mark.asyncio
    async def test_valid_condition_proceeds(self) -> None:
        """A valid condition slug updates state and proceeds."""
        from telegram_bot.handlers.ad_create.category import process_condition
        from telegram_bot.schemas.callbacks import BotCallbackPrefix

        condition = MagicMock(id=3, slug="used")

        with patch(
            "telegram_bot.handlers.ad_create.category.get_lookup_item_by_slug",
            new=AsyncMock(return_value=condition),
        ):
            state = MagicMock()
            state.update_data = AsyncMock()
            state.get_data = AsyncMock(return_value={"category_id": 42})

            callback = MagicMock()
            callback.data = f"{BotCallbackPrefix.CONDITION}used"
            callback.answer = AsyncMock()

            with patch(
                "telegram_bot.handlers.ad_create.category._show_features_or_city_step",
                new=AsyncMock(),
            ):
                await process_condition(callback, state)

        state.update_data.assert_awaited_with(condition_id=3)

    @pytest.mark.asyncio
    async def test_unknown_condition_alert(self) -> None:
        """An unrecognized condition slug triggers an alert."""
        from telegram_bot.handlers.ad_create.category import process_condition
        from telegram_bot.schemas.callbacks import BotCallbackPrefix

        with patch(
            "telegram_bot.handlers.ad_create.category.get_lookup_item_by_slug",
            new=AsyncMock(return_value=None),
        ):
            state = MagicMock()
            callback = MagicMock()
            callback.data = f"{BotCallbackPrefix.CONDITION}unknown"
            callback.answer = AsyncMock()

            await process_condition(callback, state)

        callback.answer.assert_awaited_once()
        called_text = callback.answer.call_args[0][0]
        assert "not found" in called_text.lower()


class TestProcessFeatures:
    """Tests for the features callback handler."""

    @pytest.mark.asyncio
    async def test_features_done_advances_to_city(self) -> None:
        """``features_done`` saves selections and moves to city state."""
        from telegram_bot.handlers.ad_create.category import process_features
        from telegram_bot.schemas.callbacks import BotCallbackPrefix
        from telegram_bot.handlers.ad_create import AdCreateForm

        state = MagicMock()
        state.update_data = AsyncMock()
        state.set_state = AsyncMock()
        state.get_data = AsyncMock(return_value={"feature_ids": [1, 2]})

        callback = MagicMock()
        callback.data = BotCallbackPrefix.FEATURES_DONE
        callback.message = MagicMock()
        callback.message.answer = AsyncMock()
        callback.answer = AsyncMock()

        await process_features(callback, state)

        state.update_data.assert_awaited_with(feature_ids=[1, 2])
        state.set_state.assert_awaited_with(AdCreateForm.city)
        callback.message.answer.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_feature_toggle_adds_to_selection(self) -> None:
        """Toggling a feature adds it to the selection set."""
        from telegram_bot.handlers.ad_create.category import process_features
        from telegram_bot.schemas.callbacks import BotCallbackPrefix

        feature = MagicMock(slug="premium")

        with patch(
            "telegram_bot.handlers.ad_create.category.get_resolved_features",
            new=AsyncMock(return_value=[feature]),
        ):
            with patch(
                "telegram_bot.handlers.ad_create.category.build_feature_keyboard",
                return_value=MagicMock(),
            ):
                state = MagicMock()
                state.update_data = AsyncMock()
                state.get_data = AsyncMock(return_value={"feature_ids": [], "category_id": 1})

                callback = MagicMock()
                callback.data = f"{BotCallbackPrefix.FEATURE}5"
                callback.message = MagicMock()
                callback.message.edit_reply_markup = AsyncMock()
                callback.answer = AsyncMock()

                await process_features(callback, state)

        state.update_data.assert_awaited_with(feature_ids=[5])
        callback.message.edit_reply_markup.assert_awaited_once()
