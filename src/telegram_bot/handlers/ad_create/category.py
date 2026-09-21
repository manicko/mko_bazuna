"""Category-step FSM handlers for the Telegram bot ad-creation flow.

Extracted verbatim from ``telegram_bot/handlers/ad_create/__init__.py``
(10-QLT-003 B11). These handlers resolve the category, its listing purposes,
item conditions and features, and route the FSM toward the city step. They share
the package-level ``router`` and ``AdCreateForm`` state group (imported, not
redefined) so all handlers register against the same Router instance.
"""

from aiogram import types
from aiogram.fsm.context import FSMContext
from django.utils.translation import get_language, gettext as _

from apps.categories.models import Category
from telegram_bot.handlers.ad_create import AdCreateForm, router
from telegram_bot.schemas.callbacks import BotCallbackPrefix
from telegram_bot.services.ad_data import (
    build_condition_keyboard,
    build_feature_keyboard,
    build_purpose_keyboard,
    get_default_purpose,
    get_lookup_item_by_slug,
    get_resolved_conditions,
    get_resolved_features,
    get_resolved_purposes,
    search_categories,
)


@router.message(AdCreateForm.category)
async def process_category(message: types.Message, state: FSMContext) -> None:
    """Process category selection."""

    if not message.text:
        await message.answer(
            _("Please send a category keyword or name.")
        )

        return

    keyword = message.text.strip().lower()

    # Search categories by keyword

    categories = await search_categories(keyword)

    if not categories:
        await message.answer(
            _(
                "No categories found. Please try another keyword. "
                "Top-level categories: Goods, Services, Real Estate"
            )
        )

        return

    if len(categories) == 1:
        await state.update_data(category_id=categories[0].id)

        # Resolve listing purposes for this category

        await process_category_selected(message, state, categories[0])

        return

    # Show top 3-5 suggestions

    suggestions = categories[:5]

    suggestion_text = "\n".join(
        f"{i + 1}. {cat.get_name(get_language())}" for i, cat in enumerate(suggestions)
    )

    await message.answer(
        _(
            "Please choose a category:\n%(suggestions)s\n"
            "Reply with the number or full category name."
        )
        % {"suggestions": suggestion_text}
    )


async def process_category_selected(
    message: types.Message, state: FSMContext, category: Category
) -> None:
    """Handle category selection: resolve purposes and determine next step."""

    purposes = await get_resolved_purposes(category.id)

    if not purposes:
        # Fallback: no purposes configured — use sell as default

        default_purpose = await get_lookup_item_by_slug("sell")

        if default_purpose:
            await state.update_data(listing_purpose_id=default_purpose.id)

            await proceed_to_features_or_city(message, state, category.id)

        else:
            await message.answer(
                _(
                    "No listing purposes configured for this category. "
                    "Please contact support."
                )
            )

        return

    if len(purposes) == 1:
        # Single purpose: auto-select, skip to features

        await state.update_data(listing_purpose_id=purposes[0].id)

        await proceed_to_features_or_city(message, state, category.id)

        return

    # Multiple purposes: show choice

    default_purpose = await get_default_purpose(category.id, purposes)

    keyboard = build_purpose_keyboard(
        purposes,
        default_purpose.slug if default_purpose else None,
        locale=get_language(),
    )

    await state.set_state(AdCreateForm.purpose)

    await message.answer(
        _("Category: %(name)s\nSelect the purpose of your listing:")
        % {"name": category.get_name(get_language())},
        reply_markup=keyboard,
    )


async def proceed_to_features_or_city(
    message: types.Message, state: FSMContext, category_id: int
) -> None:
    """Resolve conditions, then features, and either show them or skip to city.


    Condition is shown as a single-select step before features (PO-4).

    After condition is selected, :func:`_show_features_or_city_step` handles

    the feature multi-select or city fallback.

    """

    conditions = await get_resolved_conditions(category_id)

    if conditions:
        await state.set_state(AdCreateForm.condition)

        await state.update_data(condition_id=None)

        keyboard = build_condition_keyboard(conditions, locale=get_language())

        await message.answer(
            _("Select item condition:"),
            reply_markup=keyboard,
        )

        return

    await _show_features_or_city_step(message, state, category_id)


async def _show_features_or_city_step(
    message: types.Message, state: FSMContext, category_id: int
) -> None:
    """Show features keyboard (excluding condition slugs) or skip to city."""

    features = await get_resolved_features(category_id)

    if features:
        # Exclude new/used from features — they are now condition-specific

        non_condition_features = [f for f in features if f.slug not in ("new", "used")]

        if non_condition_features:
            await state.set_state(AdCreateForm.features)

            await state.update_data(feature_ids=[])

            keyboard = build_feature_keyboard(
                non_condition_features, set(), locale=get_language()
            )

            await message.answer(
                _(
                    "Select features for your listing (optional):\n"
                    "Tap to toggle, then tap Done."
                ),
                reply_markup=keyboard,
            )

        else:
            await state.set_state(AdCreateForm.city)

            await message.answer(_("Now select a city. Send a city name."))

    else:
        # No features: skip to city

        await state.set_state(AdCreateForm.city)

        await message.answer(_("Now select a city. Send a city name."))


@router.callback_query(
    AdCreateForm.purpose,
    lambda c: c.data and c.data.startswith(BotCallbackPrefix.PURPOSE),
)
async def process_purpose(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Process purpose selection from inline keyboard."""

    if not callback.data or not callback.message:
        return

    slug = callback.data.replace(BotCallbackPrefix.PURPOSE, "")

    purpose_item = await get_lookup_item_by_slug(slug)

    if not purpose_item:
        await callback.answer(_("Purpose not found."))

        return

    await state.update_data(listing_purpose_id=purpose_item.id)

    data = await state.get_data()

    await callback.answer()

    await proceed_to_features_or_city(callback.message, state, data.get("category_id"))


@router.callback_query(
    AdCreateForm.condition,
    lambda c: c.data and c.data.startswith(BotCallbackPrefix.CONDITION),
)
async def process_condition(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Process condition selection from inline keyboard."""
    if not callback.data or not callback.message:
        return

    slug = callback.data.replace(BotCallbackPrefix.CONDITION, "")
    condition_item = await get_lookup_item_by_slug(slug)
    if not condition_item:
        await callback.answer(_("Condition not found."))
        return

    await state.update_data(condition_id=condition_item.id)
    data = await state.get_data()
    await callback.answer()

    # Proceed to features (or city if no features)
    await _show_features_or_city_step(callback.message, state, data.get("category_id"))


@router.callback_query(AdCreateForm.features)
async def process_features(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Process feature toggles from inline keyboard."""

    if not callback.data or not callback.message:
        return

    data = await state.get_data()

    selected_ids = set(data.get("feature_ids", []))

    if callback.data == BotCallbackPrefix.FEATURES_DONE:
        await state.update_data(feature_ids=list(selected_ids))

        await callback.answer()

        await state.set_state(AdCreateForm.city)

        await callback.message.answer(_("Now select a city. Send a city name."))

        return

    if callback.data.startswith(BotCallbackPrefix.FEATURE):
        feature_id = int(callback.data.replace(BotCallbackPrefix.FEATURE, ""))

        if feature_id in selected_ids:
            selected_ids.discard(feature_id)
        else:
            selected_ids.add(feature_id)

        await state.update_data(feature_ids=list(selected_ids))

        # Update keyboard with new selection state

        features = await get_resolved_features(data.get("category_id"))

        keyboard = build_feature_keyboard(
            features, selected_ids, locale=get_language()
        )

        await callback.message.edit_reply_markup(reply_markup=keyboard)

        await callback.answer()
