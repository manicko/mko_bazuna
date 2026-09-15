"""Regression tests for the bot condition-selection step (Spec 12 / Plan 36 T-05).

Verifies the condition single-select dimension in the Telegram ad-creation FSM:

- The condition inline keyboard is shown for categories that resolve conditions,
  and the FSM lands in ``AdCreateForm.condition``.
- Selecting ``condition:new`` persists ``condition_id`` in FSM state (the
  dormant persistence path activated by T-01).
- The features keyboard excludes the ``new``/``used`` condition slugs from the
  multi-select feature buttons (Spec 12 Task 4d / REQ-12.3).
- Categories without resolved conditions skip the condition step entirely.

These call the real handlers directly (matching the established suite pattern in
``test_ad_create.py``) with a real ``FSMContext`` over ``MemoryStorage`` so state
reads/writes are genuinely exercised. Importing ``process_condition`` at module
scope is itself the regression gate for T-01: before the fix it was a dead
nested function (not importable from the module), so these tests fail without
that fix.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

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


def _callback_data_set(markup) -> set[str]:
    """Collect every ``callback_data`` string from an inline keyboard markup."""
    if markup is None:
        return set()
    data: set[str] = set()
    for row in getattr(markup, "inline_keyboard", []) or []:
        for button in row:
            cd = getattr(button, "callback_data", None)
            if cd:
                data.add(cd)
    return data


def _mock_message() -> MagicMock:
    """A Message double whose ``answer`` is awaitable and recorded."""
    message = MagicMock()
    message.answer = AsyncMock()
    return message


# ---------------------------------------------------------------------------
# Fixtures — mirror test_catalog_filters.py's lookup/condition fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def condition_lookup() -> dict[str, object]:
    """Create the ``listing_condition`` group with ``new``/``used`` items."""
    from apps.lookups.models import LookupGroup, LookupItem

    group = LookupGroup.objects.create(code="listing_condition", is_system=True)
    new = LookupItem.objects.create(
        group=group,
        slug="new",
        name_i18n={"ru": "Новый", "en": "New"},
        is_active=True,
    )
    used = LookupItem.objects.create(
        group=group,
        slug="used",
        name_i18n={"ru": "Б/У", "en": "Used"},
        is_active=True,
    )
    return {"new": new, "used": used}


@pytest.fixture
def feature_lookup() -> dict[str, object]:
    """Create the ``listing_feature`` group with genuine features (no new/used)."""
    from apps.lookups.models import LookupGroup, LookupItem

    group = LookupGroup.objects.create(code="listing_feature", is_system=True)
    delivery = LookupItem.objects.create(
        group=group,
        slug="delivery",
        name_i18n={"ru": "Доставка", "en": "Delivery"},
        is_active=True,
    )
    negotiable = LookupItem.objects.create(
        group=group,
        slug="negotiable",
        name_i18n={"ru": "Торг уместен", "en": "Negotiable"},
        is_active=True,
    )
    return {"delivery": delivery, "negotiable": negotiable}


@pytest.fixture
def conditional_category(category, condition_lookup, feature_lookup):
    """Bind new/used conditions and genuine features to the test category."""
    from apps.categories.models import (
        CategoryListingCondition,
        CategoryListingFeature,
    )
    from apps.categories.services.lookup_resolution import CategoryLookupResolver

    CategoryListingCondition.objects.create(
        category=category, listing_condition=condition_lookup["new"]
    )
    CategoryListingCondition.objects.create(
        category=category, listing_condition=condition_lookup["used"]
    )
    CategoryListingFeature.objects.create(
        category=category, feature=feature_lookup["delivery"]
    )
    CategoryListingFeature.objects.create(
        category=category, feature=feature_lookup["negotiable"]
    )
    # Clear the resolver cache so the freshly-bound conditions/features are seen.
    CategoryLookupResolver.invalidate_category(category.id)
    return category


@pytest.fixture
def fsm_context() -> FSMContext:
    """A real FSMContext over in-memory storage (exercises real state I/O)."""
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=1, thread_id=0)
    return FSMContext(storage=storage, key=key)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBotConditionStep:
    """Condition single-select step (Spec 12 Task 4 / DoD #3)."""

    @pytest.mark.asyncio
    async def test_condition_keyboard_shown_for_conditional_category(
        self, conditional_category, fsm_context
    ) -> None:
        """A category with resolved conditions shows the condition keyboard."""
        from telegram_bot.handlers.ad_create import (
            AdCreateForm,
            proceed_to_features_or_city,
        )

        message = _mock_message()
        await proceed_to_features_or_city(message, fsm_context, conditional_category.id)

        # FSM must land in the condition state, not skip to features/city.
        assert await fsm_context.get_state() == AdCreateForm.condition

        call = message.answer.await_args_list[-1]
        assert "condition" in (call.args[0] if call.args else "")
        callbacks = _callback_data_set(call.kwargs.get("reply_markup"))
        assert "condition:new" in callbacks
        assert "condition:used" in callbacks

    @pytest.mark.asyncio
    async def test_condition_selection_persists_condition_id(
        self, conditional_category, condition_lookup, fsm_context
    ) -> None:
        """Selecting ``condition:new`` persists the LookupItem id in state."""
        from telegram_bot.handlers.ad_create import AdCreateForm, process_condition

        await fsm_context.set_state(AdCreateForm.condition)
        await fsm_context.update_data(category_id=conditional_category.id)

        callback = MagicMock()
        callback.data = "condition:new"
        callback.message = _mock_message()
        callback.answer = AsyncMock()

        await process_condition(callback, fsm_context)

        data = await fsm_context.get_data()
        assert data["condition_id"] == condition_lookup["new"].id

    @pytest.mark.asyncio
    async def test_feature_keyboard_excludes_new_and_used(
        self, condition_lookup, feature_lookup
    ) -> None:
        """The features keyboard never emits ``feature:`` buttons for new/used."""
        from telegram_bot.handlers.ad_create import build_feature_keyboard

        items = [
            condition_lookup["new"],
            condition_lookup["used"],
            feature_lookup["delivery"],
        ]
        markup = build_feature_keyboard(items, set())

        callbacks = _callback_data_set(markup)
        assert f"feature:{condition_lookup['new'].id}" not in callbacks
        assert f"feature:{condition_lookup['used'].id}" not in callbacks
        assert f"feature:{feature_lookup['delivery'].id}" in callbacks
        assert "features_done" in callbacks

    @pytest.mark.asyncio
    async def test_no_condition_keyboard_for_nonconditional_category(
        self, category, fsm_context
    ) -> None:
        """A category without conditions skips the condition step."""
        from telegram_bot.handlers.ad_create import (
            AdCreateForm,
            proceed_to_features_or_city,
        )

        message = _mock_message()
        await proceed_to_features_or_city(message, fsm_context, category.id)

        # Must not enter the condition state.
        assert await fsm_context.get_state() != AdCreateForm.condition
        # No message offers condition selection.
        answer_texts = [c.args[0] for c in message.answer.await_args_list if c.args]
        assert not any("condition" in t.lower() for t in answer_texts)
