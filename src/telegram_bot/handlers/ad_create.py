"""
Ad creation FSM handler for Telegram bot.

Implements step-by-step ad creation with Pydantic validation. Data-access
helpers, media helpers, translation helpers and keyboard builders live in
``telegram_bot.services.ad_data`` (bot -> backend direction); this module
retains only the FSM handlers, router, and state group.
"""

import asyncio
import difflib
import logging
from decimal import Decimal
from typing import Any

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup
from asgiref.sync import sync_to_async
from django.utils.translation import get_language, gettext as _

from apps.ads.services.submission import SubmitAdInput, submit_ad
from apps.categories.models import Category
from apps.core.enums import AdStatus, LanguageLocale
from apps.core.services.site_config import get_site_name_async
from apps.currencies.enums import CurrencyCode
from apps.media.services.filesystem import (
    delete_photo,
    generate_storage_key,
    validate_photo,
)
from telegram_bot.schemas.callbacks import BotCallbackPrefix
from telegram_bot.schemas.message_payloads import (
    DescriptionPayload,
    PhotoCountPayload,
    PricePayload,
    TitlePayload,
)
from telegram_bot.services.ad_data import (
    _get_ad_status,
    build_condition_keyboard,
    build_currency_keyboard,
    build_feature_keyboard,
    build_purpose_keyboard,
    create_draft_ad,
    delete_draft,
    download_photo,
    get_all_cities,
    get_category,
    get_city,
    get_city_by_name,
    get_default_purpose,
    get_feature_names,
    get_lookup_item,
    get_lookup_item_by_slug,
    get_resolved_conditions,
    get_resolved_features,
    get_resolved_purposes,
    save_photo,
    search_categories,
    translate_all_languages,
)
from telegram_bot.services.rate_limit import check_upload_rate_limit
from telegram_bot.states import AdCreateState

logger = logging.getLogger(__name__)

# 2 MB — matches the validate_photo limit in filesystem.py (MED-002).
MAX_PHOTO_BYTES = 2 * 1024 * 1024


router = Router()


class AdCreateForm(StatesGroup):
    """FSM states for ad creation."""

    category = AdCreateState.CATEGORY

    purpose = AdCreateState.PURPOSE

    condition = AdCreateState.CONDITION

    features = AdCreateState.FEATURES

    city = AdCreateState.CITY

    title = AdCreateState.TITLE

    description = AdCreateState.DESCRIPTION

    price = AdCreateState.PRICE

    photos = AdCreateState.PHOTOS

    preview = AdCreateState.PREVIEW


@router.message(Command("post"))
async def cmd_post(message: types.Message, state: FSMContext) -> None:
    """Start the ad creation flow."""

    if not message.from_user:
        return

    data = await state.get_data()

    if "user_id" not in data:
        await message.answer(
            _("Please login first with /start login_<token>")
        )

        return

    # Create draft ad

    ad = await create_draft_ad(user_id=data["user_id"])

    await state.set_state(AdCreateForm.category)

    await state.update_data(ad_id=ad.id)

    await message.answer(
        _(
            "Welcome to %(site)s! Creating new ad. Please select a category.\n"
            "Send a keyword to search, or use /cancel to abort."
        )
        % {"site": await get_site_name_async()}
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext) -> None:
    """Cancel ad creation.

    Only deletes photo files and removes the draft if the ad is still in
    DRAFT status. If the ad has already been submitted (ON_MODERATION or
    later) the FSM ``photos`` list is stale and must not be used to delete
    files belonging to a submitted ad.
    """

    data = await state.get_data()

    if "ad_id" in data:
        ad_status = await _get_ad_status(data["ad_id"])

        if ad_status == AdStatus.DRAFT:
            # Clean up photo files from FSM state before deleting the draft

            photos = data.get("photos", [])

            for photo in photos:
                await asyncio.to_thread(delete_photo, photo["storage_key"])

            await delete_draft(data["ad_id"])

        else:
            logger.info(
                "Cancel skipped photo cleanup: ad %s is %s, not DRAFT",
                data["ad_id"],
                ad_status,
            )

    await state.clear()

    await message.answer(_("Ad creation cancelled."))


# --- Category step ---


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


# --- Purpose step ---


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


# --- Condition step ---


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


# --- Features step ---


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


# --- City step ---


@router.message(AdCreateForm.city)
async def process_city(message: types.Message, state: FSMContext) -> None:
    """Process city selection."""

    if not message.text:
        await message.answer(_("Please send a city name."))

        return

    city_name = message.text.strip()

    # Exact match or did-you-mean

    city = await get_city_by_name(city_name)

    if not city:
        all_cities = await get_all_cities()

        close_matches = difflib.get_close_matches(
            city_name, [c.get_name(get_language()) for c in all_cities], n=3, cutoff=0.6
        )

        if close_matches:
            match = await get_city_by_name(close_matches[0])

            if match:
                city = match

    if not city:
        await message.answer(
            _(
                "City not found. Please send an exact city name.\n"
                "Available cities: Podgorica, Nikšić, Bar, etc."
            )
        )

        return

    await state.update_data(city_id=city.id)

    await state.set_state(AdCreateForm.title)

    await message.answer(
        _("City: %(name)s\nNow enter the ad title (5-200 characters).")
        % {"name": city.get_name(get_language())}
    )


# --- Title step ---


@router.message(AdCreateForm.title)
async def process_title(message: types.Message, state: FSMContext) -> None:
    """Process title input with Pydantic validation."""

    if not message.text:
        await message.answer(_("Please send the ad title."))

        return

    try:
        payload = TitlePayload(title=message.text)

    except Exception as e:
        await message.answer(_("Invalid title: {error}").format(error=e))

        return

    await state.update_data(title=payload.title)

    await state.set_state(AdCreateForm.description)

    await message.answer(
        _("Title saved.\nNow enter the ad description (10-2000 characters).")
    )


# --- Description step ---


@router.message(AdCreateForm.description)
async def process_description(message: types.Message, state: FSMContext) -> None:
    """Process description input with Pydantic validation."""

    if not message.text:
        await message.answer(_("Please send the ad description."))

        return

    try:
        payload = DescriptionPayload(description=message.text)

    except Exception as e:
        await message.answer(_("Invalid description: {error}").format(error=e))

        return

    await state.update_data(description=payload.description)

    await state.set_state(AdCreateForm.price)

    await message.answer(
        _("Description saved.\n"
          "Now choose the price currency, or select 'Free' for a zero-price (Charity) ad."),
        reply_markup=build_currency_keyboard(),
    )


# --- Price step ---


@router.callback_query(AdCreateForm.price)
async def process_price_currency(
    callback: types.CallbackQuery, state: FSMContext
) -> None:
    """Process currency selection (or Free) from the price inline keyboard."""

    if not callback.data or not callback.message:
        return

    if callback.data == BotCallbackPrefix.PRICE_FREE:
        await state.update_data(
            price_amount=Decimal("0.00"),
            price_currency=CurrencyCode.EUR,
        )

        await callback.answer()

        await _move_from_price_to_photos(callback.message, state)

        return

    if callback.data.startswith(BotCallbackPrefix.PRICE_CURRENCY):
        currency_value = callback.data.replace(BotCallbackPrefix.PRICE_CURRENCY, "")

        try:
            currency = CurrencyCode(currency_value)

        except ValueError:
            await callback.answer(_("Invalid currency."), show_alert=True)

            return

        await state.update_data(price_currency=currency)

        await callback.answer()

        await callback.message.answer(
            _("Currency: %(currency)s\nNow enter the price amount as a number.")
            % {"currency": currency.value}
        )


@router.message(AdCreateForm.price)
async def process_price(message: types.Message, state: FSMContext) -> None:
    """Process the numeric price amount input with Pydantic validation."""

    data = await state.get_data()

    currency: CurrencyCode | None = data.get("price_currency")

    if currency is None:
        await message.answer(
            _("Please choose a currency first or select 'Free' for a zero-price (Charity) ad."),
            reply_markup=build_currency_keyboard(),
        )

        return

    if not message.text:
        await message.answer(
            _("Please send the price amount as a number, or select 'Free' on the keyboard.")
        )

        return

    text = message.text.strip().lower()

    try:
        price_value = Decimal(text)

        payload = PricePayload(price_amount=price_value, price_currency=currency)

        await state.update_data(price_amount=payload.price_amount)

    except (ValueError, ArithmeticError):
        await message.answer(_("Invalid price. Enter a number."))

        return

    await _move_from_price_to_photos(message, state)


async def _move_from_price_to_photos(message: types.Message, state: FSMContext) -> None:
    """Advance from the price step to the photo upload step."""

    await state.set_state(AdCreateForm.photos)

    await message.answer(
        _("Price saved.\n"
          "Send 1-5 photos (JPEG only). Each photo under ~2MB, max 2560x2560 pixels.\n"
          "Send 'done' when finished.")
    )


# --- Photos step ---


@router.message(AdCreateForm.photos)
async def process_photos(message: types.Message, state: FSMContext) -> None:
    """Process photo uploads with validation."""

    data = await state.get_data()

    photos = data.get("photos", [])

    # Handle 'done' command

    if message.text and message.text.strip().lower() == "done":
        count = len(photos)

        try:
            PhotoCountPayload(photo_count=count)

        except Exception:
            if count == 0:
                await message.answer(_("Please send at least 1 photo before finishing."))
            else:
                await message.answer(
                    _("You can upload at most 5 photos (you have {count}).").format(
                        count=count
                    )
                )
            return

        await state.set_state(AdCreateForm.preview)

        await show_preview(message, data)

        return

    # Validate photo exists

    if not message.photo:
        await message.answer(_("Please send a photo (JPEG only) or 'done' to finish."))

        return

    # Get largest photo

    photo = message.photo[-1]

    # Enforce the hard cap before downloading — prevents unbounded uploads
    # and orphaned files beyond the 5-photo limit.
    if len(photos) >= 5:
        await message.answer(
            _("You already have {count} photos. You can upload at most 5 photos.").format(
                count=len(photos)
            )
        )
        return

    # Enforce per-seller upload burst limit (anti-abuse).
    user_id = data.get("user_id")
    if user_id is not None and not await check_upload_rate_limit(user_id):
        await message.answer(_("Uploading too fast, please wait a moment."))
        return

    # Pre-check Telegram-reported file_size before downloading to prevent
    # memory exhaustion from oversized uploads (MED-002). The post-download
    # validate_photo size check is retained as defense-in-depth.

    if photo.file_size is not None and photo.file_size > MAX_PHOTO_BYTES:
        await message.answer(_("Photo too large. Maximum size is approximately 2MB."))
        return

    # Download photo bytes for validation

    photo_bytes = await download_photo(photo.file_id, message.bot)

    if not photo_bytes:
        await message.answer(_("Failed to download photo. Try again."))

        return

    # Validate photo

    is_valid, error = validate_photo(photo_bytes)

    if not is_valid:
        await message.answer(_("Invalid: {error}").format(error=error))

        return

    # Store photo

    storage_key = await save_photo(generate_storage_key(), photo_bytes)

    # Save to state

    photos.append(
        {
            "storage_key": storage_key,
            "telegram_file_id": photo.file_id,
            "position": len(photos),
        }
    )

    await state.update_data(photos=photos)

    await message.answer(
        _("Photo saved ({count}/5).\nSend more or 'done' to finish.").format(
            count=len(photos)
        )
    )


# --- Preview step ---


async def show_preview(message: types.Message, data: dict[str, Any]) -> None:
    """Show ad preview before submission."""

    category = await get_category(data.get("category_id"))

    city = await get_city(data.get("city_id"))

    purpose = await get_lookup_item(data.get("listing_purpose_id"))

    purpose_name = (
        purpose.get_name(get_language()) if purpose else _("N/A")
    )

    condition = await get_lookup_item(data.get("condition_id"))

    condition_name = (
        condition.get_name(get_language()) if condition else _("N/A")
    )

    feature_ids = data.get("feature_ids", [])

    feature_names = (
        ", ".join(await get_feature_names(feature_ids, locale=get_language()))
        if feature_ids
        else _("None")
    )

    preview_text = (
        _("Ad Preview:\n\n"
          "Title: %(title)s\n"
          "Description: %(description)s...\n"
          "Price: %(price)s\n"
          "Category: %(category)s\n"
          "Purpose: %(purpose)s\n"
          "Condition: %(condition)s\n"
          "Features: %(features)s\n"
          "City: %(city)s\n")
        % {
            "title": data.get("title", _("N/A")),
            "description": data.get("description", _("N/A"))[:100],
            "price": _format_preview_price(data),
            "category": category.get_name(get_language()) if category else _("N/A"),
            "purpose": purpose_name,
            "condition": condition_name,
            "features": feature_names,
            "city": city.get_name(get_language()) if city else _("N/A"),
        }
    )

    await message.answer(
        preview_text
        + _("Send 'confirm' to submit for moderation or 'cancel' to abort.")
    )


def _format_preview_price(data: dict[str, Any]) -> str:
    """Format the selected price (amount + currency) for the preview."""

    amount = data.get("price_amount")

    if amount is None:
        return _("N/A")

    currency = data.get("price_currency")

    label = str(currency) if currency else ""

    return f"{amount} {label}".strip()


@router.message(AdCreateForm.preview)
async def process_preview(message: types.Message, state: FSMContext) -> None:
    """Process preview confirmation."""

    if not message.text:
        return

    if not message.from_user:
        return

    text = message.text.strip().lower()

    if text == "confirm":
        data = await state.get_data()

        original_title = data.get("title", "")

        original_desc = data.get("description", "")

        # Translate to all languages in parallel

        title_translations = await translate_all_languages(
            original_title, LanguageLocale.values()
        )

        desc_translations = await translate_all_languages(
            original_desc, LanguageLocale.values()
        )

        # Update ad with multi-language content and run moderation

        is_valid, errors = await sync_to_async(submit_ad)(
            SubmitAdInput(
                ad_id=data["ad_id"],
                title_ru=title_translations.get("ru", original_title),
                desc_ru=desc_translations.get("ru", original_desc),
                title_bs=title_translations.get("bs", original_title),
                desc_bs=desc_translations.get("bs", original_desc),
                title_en=title_translations.get("en", original_title),
                desc_en=desc_translations.get("en", original_desc),
                original_language=LanguageLocale.from_code(
                    message.from_user.language_code,
                    fallback=LanguageLocale.BOSNIAN,
                ).value,
                category_id=data.get("category_id"),
                city_id=data.get("city_id"),
                price_amount=data.get("price_amount") or Decimal("0"),
                price_currency=data.get("price_currency"),
                photos=data.get("photos", []),
                user_id=data.get("user_id"),
                listing_purpose_id=data.get("listing_purpose_id"),
                feature_ids=data.get("feature_ids"),
                listing_condition_id=data.get("condition_id"),
            )
        )

        if is_valid:
            await message.answer(
                _("Ad submitted for moderation! You'll be notified when it's published.")
            )

            await state.clear()

        else:
            await message.answer(
                _("Ad failed moderation. Please check your content and try again.")
            )

            await state.clear()

            return

    elif text == "cancel":
        await cmd_cancel(message, state)

    else:
        await message.answer(_("Send 'confirm' to submit or 'cancel' to abort."))
