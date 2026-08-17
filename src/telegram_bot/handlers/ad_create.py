"""
Ad creation FSM handler for Telegram bot.

Implements step-by-step ad creation with Pydantic validation.
"""

import difflib
import logging
import os

from aiogram import Bot, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from django.conf import settings

from apps.ads.models import Ad, AdImage
from apps.categories.models import Category
from apps.core.enums import AdStatus, LanguageLocale, ThumbnailSizeStrEnum
from apps.core.services.translation import translate_text
from apps.locations.models import City
from telegram_bot.schemas.message_payloads import (
    DescriptionPayload,
    PhotoCountPayload,
    PricePayload,
    TitlePayload,
)
from telegram_bot.services.media import generate_storage_key, validate_photo, strip_photo_exif, delete_photo
from telegram_bot.states import AdCreateState
import asyncio

from apps.media.services.thumbnails import ThumbnailService

logger = logging.getLogger(__name__)

router = Router()


class AdCreateForm(StatesGroup):
    """FSM states for ad creation."""

    category = AdCreateState.CATEGORY
    purpose = AdCreateState.PURPOSE
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
        await message.answer("Please login first with /start login_<token>")
        return

    # Create draft ad
    ad = await create_draft_ad(user_id=data["user_id"])

    await state.set_state(AdCreateForm.category)
    await state.update_data(ad_id=ad.id)

    await message.answer(
        "Creating new ad. Please select a category.\n"
        "Send a keyword to search, or use /cancel to abort."
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext) -> None:
    """Cancel ad creation."""
    data = await state.get_data()

    if "ad_id" in data:
        # Clean up photo files from FSM state before deleting the draft
        photos = data.get("photos", [])
        for photo in photos:
            await asyncio.to_thread(delete_photo, photo["storage_key"])

        await delete_draft(data["ad_id"])

    await state.clear()
    await message.answer("Ad creation cancelled.")


# --- Category step ---
@router.message(AdCreateForm.category)
async def process_category(message: types.Message, state: FSMContext) -> None:
    """Process category selection."""
    if not message.text:
        await message.answer("Please send a category keyword or name.")
        return

    keyword = message.text.strip().lower()

    # Search categories by keyword
    categories = await search_categories(keyword)

    if not categories:
        await message.answer(
            "No categories found. Please try another keyword. "
            "Top-level categories: Товары, Услуги, Недвижимость"
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
        f"{i+1}. {cat.name}" for i, cat in enumerate(suggestions)
    )

    await message.answer(
        f"Please choose a category:\n{suggestion_text}\n"
        "Reply with the number or full category name."
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
                "No listing purposes configured for this category. "
                "Please contact support."
            )
        return

    if len(purposes) == 1:
        # Single purpose: auto-select, skip to features
        await state.update_data(listing_purpose_id=purposes[0].id)
        await proceed_to_features_or_city(message, state, category.id)
        return

    # Multiple purposes: show choice
    default_purpose = await get_default_purpose(category.id, purposes)
    keyboard = build_purpose_keyboard(purposes, default_purpose.slug if default_purpose else None)
    await state.set_state(AdCreateForm.purpose)
    await message.answer(
        f"Category: {category.name}\n"
        "Select the purpose of your listing:",
        reply_markup=keyboard,
    )


async def proceed_to_features_or_city(
    message: types.Message, state: FSMContext, category_id: int
) -> None:
    """Resolve features and either show them or skip to city selection."""
    features = await get_resolved_features(category_id)

    if features:
        await state.set_state(AdCreateForm.features)
        await state.update_data(feature_ids=[])
        keyboard = build_feature_keyboard(features, set())
        await message.answer(
            "Select features for your listing (optional):\n"
            "Tap to toggle, then tap Done.",
            reply_markup=keyboard,
        )
    else:
        # No features: skip to city
        await state.set_state(AdCreateForm.city)
        await message.answer(
            "Now select a city. Send a city name."
        )


# --- Purpose step ---
@router.callback_query(AdCreateForm.purpose, lambda c: c.data and c.data.startswith("purpose:"))
async def process_purpose(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Process purpose selection from inline keyboard."""
    if not callback.data or not callback.message:
        return

    slug = callback.data.replace("purpose:", "")
    purpose_item = await get_lookup_item_by_slug(slug)
    if not purpose_item:
        await callback.answer("Purpose not found.")
        return

    await state.update_data(listing_purpose_id=purpose_item.id)
    data = await state.get_data()
    await callback.answer()

    await proceed_to_features_or_city(
        callback.message, state, data.get("category_id")
    )


# --- Features step ---
@router.callback_query(AdCreateForm.features)
async def process_features(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Process feature toggles from inline keyboard."""
    if not callback.data or not callback.message:
        return

    data = await state.get_data()
    selected_ids = set(data.get("feature_ids", []))

    if callback.data == "features_done":
        await state.update_data(feature_ids=list(selected_ids))
        await callback.answer()
        await state.set_state(AdCreateForm.city)
        await callback.message.answer(
            "Now select a city. Send a city name."
        )
        return

    if callback.data.startswith("feature:"):
        feature_id = int(callback.data.replace("feature:", ""))
        if feature_id in selected_ids:
            selected_ids.discard(feature_id)
        else:
            selected_ids.add(feature_id)

        await state.update_data(feature_ids=list(selected_ids))

        # Update keyboard with new selection state
        features = await get_resolved_features(data.get("category_id"))
        keyboard = build_feature_keyboard(features, selected_ids)
        await callback.message.edit_reply_markup(reply_markup=keyboard)
        await callback.answer()


# --- City step ---
@router.message(AdCreateForm.city)
async def process_city(message: types.Message, state: FSMContext) -> None:
    """Process city selection."""
    if not message.text:
        await message.answer("Please send a city name.")
        return

    city_name = message.text.strip()

    # Exact match or did-you-mean
    city = await get_city_by_name(city_name)

    if not city:
        all_cities = await get_all_cities()
        close_matches = difflib.get_close_matches(
            city_name, [c.name for c in all_cities], n=3, cutoff=0.6
        )

        if close_matches:
            match = await get_city_by_name(close_matches[0])
            if match:
                city = match

    if not city:
        await message.answer(
            "City not found. Please send an exact city name.\n"
            "Available cities: Podgorica, Nikšić, Bar, etc."
        )
        return

    await state.update_data(city_id=city.id)
    await state.set_state(AdCreateForm.title)
    await message.answer(
        f"City: {city.name}\nNow enter the ad title (5-200 characters)."
    )


# --- Title step ---
@router.message(AdCreateForm.title)
async def process_title(message: types.Message, state: FSMContext) -> None:
    """Process title input with Pydantic validation."""
    if not message.text:
        await message.answer("Please send the ad title.")
        return

    try:
        payload = TitlePayload(title=message.text)
    except Exception as e:
        await message.answer(f"Invalid title: {e}")
        return

    await state.update_data(title=payload.title)
    await state.set_state(AdCreateForm.description)
    await message.answer(
        "Title saved.\nNow enter the ad description (10-2000 characters)."
    )


# --- Description step ---
@router.message(AdCreateForm.description)
async def process_description(message: types.Message, state: FSMContext) -> None:
    """Process description input with Pydantic validation."""
    if not message.text:
        await message.answer("Please send the ad description.")
        return

    try:
        payload = DescriptionPayload(description=message.text)
    except Exception as e:
        await message.answer(f"Invalid description: {e}")
        return

    await state.update_data(description=payload.description)
    await state.set_state(AdCreateForm.price)
    await message.answer(
        "Description saved.\n"
        "Enter price in BAM (whole numbers) or send 'skip' if price not required."
    )


# --- Price step ---
@router.message(AdCreateForm.price)
async def process_price(message: types.Message, state: FSMContext) -> None:
    """Process price input with Pydantic validation."""
    if not message.text:
        await message.answer("Please send price or 'skip'.")
        return

    text = message.text.strip().lower()

    if text == "skip":
        await state.update_data(price=None)
    else:
        try:
            price_value = int(text)
            payload = PricePayload(price=price_value)
            await state.update_data(price=payload.price)
        except (ValueError, Exception):
            await message.answer("Invalid price. Enter a number or 'skip'.")
            return

    await state.set_state(AdCreateForm.photos)
    await message.answer(
        "Price saved.\n"
        "Send 1-5 photos (JPEG only). Each photo under ~2MB, max 2560x2560 pixels.\n"
        "Send 'done' when finished."
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
            await message.answer(f"Please send at least 1 photo (you have {count}).")
            return

        await state.set_state(AdCreateForm.preview)
        await show_preview(message, data)
        return

    # Validate photo exists
    if not message.photo:
        await message.answer(
            "Please send a photo (JPEG only) or 'done' to finish."
        )
        return

    # Get largest photo
    photo = message.photo[-1]

    # Download photo bytes for validation
    photo_bytes = await download_photo(photo.file_id, message.bot)

    if not photo_bytes:
        await message.answer("Failed to download photo. Try again.")
        return

    # Validate photo
    is_valid, error = validate_photo(photo_bytes)

    if not is_valid:
        await message.answer(f"Invalid: {error}")
        return

    # Store photo
    storage_key = await save_photo(generate_storage_key(), photo_bytes)

    # Save to state
    photos.append(
        {"storage_key": storage_key, "telegram_file_id": photo.file_id, "position": len(photos)}
    )
    await state.update_data(photos=photos)

    await message.answer(
        f"Photo saved ({len(photos)}/5).\nSend more or 'done' to finish."
    )


# --- Preview step ---
async def show_preview(message: types.Message, data: dict) -> None:
    """Show ad preview before submission."""
    category = await get_category(data.get("category_id"))
    city = await get_city(data.get("city_id"))
    purpose = await get_lookup_item(data.get("listing_purpose_id"))
    purpose_name = purpose.name_i18n.get("ru", purpose.slug) if purpose and purpose.name_i18n else (purpose.slug if purpose else "N/A")
    feature_ids = data.get("feature_ids", [])
    feature_names = ", ".join(
        await get_feature_names(feature_ids)
    ) if feature_ids else "None"

    preview_text = (
        f"Ad Preview:\n\n"
        f"Title: {data.get('title', 'N/A')}\n"
        f"Description: {data.get('description', 'N/A')[:100]}...\n"
        f"Price: {data.get('price', 'N/A')} BAM\n"
        f"Category: {category.name if category else 'N/A'}\n"
        f"Purpose: {purpose_name}\n"
        f"Features: {feature_names}\n"
        f"City: {city.name if city else 'N/A'}\n"
    )

    await message.answer(
        preview_text + "Send 'confirm' to submit for moderation or 'cancel' to abort."
    )


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
            original_title, ["ru", "bs", "en"]
        )
        desc_translations = await translate_all_languages(
            original_desc, ["ru", "bs", "en"]
        )

        # Update ad with multi-language content and run moderation
        is_valid, errors = await update_ad_and_moderate(
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
            price=data.get("price"),
            photos=data.get("photos", []),
            user_id=data.get("user_id"),
            listing_purpose_id=data.get("listing_purpose_id"),
            feature_ids=data.get("feature_ids"),
        )

        if is_valid:
            await message.answer(
                "Ad submitted for moderation! You'll be notified when it's published."
            )
        else:
            await message.answer(
                "Ad failed moderation. Please check your content and try again."
            )
            await state.clear()
            return

    elif text == "cancel":
        await cmd_cancel(message, state)
    else:
        await message.answer("Send 'confirm' to submit or 'cancel' to abort.")


# Helper functions using sync_to_async
async def create_draft_ad(user_id: int) -> Ad:
    """Create a draft ad row."""
    from asgiref.sync import sync_to_async

    @sync_to_async
    def _create() -> Ad:
        return Ad.objects.create(user_id=user_id, status=AdStatus.DRAFT)

    return await _create()


async def delete_draft(ad_id: int) -> None:
    """Delete a draft ad and clean up its photo files."""
    from asgiref.sync import sync_to_async

    @sync_to_async
    def _delete() -> None:
        try:
            ad = Ad.objects.get(id=ad_id, status=AdStatus.DRAFT)
        except Ad.DoesNotExist:
            return

        # Delete physical photo files for any AdImage records
        for img in ad.images.all():
            delete_photo(img.image)

        ad.delete()

    await _delete()


async def search_categories(keyword: str):
    """Search categories by keyword."""
    from asgiref.sync import sync_to_async

    @sync_to_async
    def _search():
        return list(
            Category.objects.filter(name__icontains=keyword, is_active=True)[:5]
        )

    return await _search()


async def get_city_by_name(name: str):
    """Get city by exact name."""
    from asgiref.sync import sync_to_async

    @sync_to_async
    def _get():
        try:
            return City.objects.get(name__iexact=name)
        except City.DoesNotExist:
            return None

    return await _get()


async def get_all_cities():
    """Get all cities."""
    from asgiref.sync import sync_to_async

    @sync_to_async
    def _get():
        return list(City.objects.all())

    return await _get()


async def download_photo(file_id: str, bot: Bot) -> bytes | None:
    """Download photo bytes from Telegram."""
    try:
        file = await bot.download(file_id)
        return file.read() if file else None
    except Exception as e:
        logger.error(f"Failed to download photo {file_id}: {e}")
        return None


async def save_photo(storage_key: str, photo_bytes: bytes) -> str:
    """Save photo to filesystem via thread executor to avoid blocking the event loop.

    Strips EXIF/metadata and re-encodes the image before persisting to disk.
    Uses ``os.open`` with ``O_CREAT|O_EXCL`` to guarantee atomic writes; on
    ``FileExistsError`` regenerates the storage key and retries.

    Returns:
        The final storage key used (may differ from the input on collision).
    """

    def _write(path: str, data: bytes) -> None:
        cleaned = strip_photo_exif(data)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(fd, cleaned)
        finally:
            os.close(fd)

    key = storage_key
    while True:
        media_path = os.path.join(settings.MEDIA_ROOT, key)
        try:
            await asyncio.to_thread(_write, media_path, photo_bytes)
            return key
        except FileExistsError:
            logger.warning(f"Storage key collision: {key}, regenerating")
            key = generate_storage_key()


async def get_category(category_id: int):
    """Get category by ID."""
    from asgiref.sync import sync_to_async

    @sync_to_async
    def _get():
        try:
            return Category.objects.get(id=category_id)
        except Category.DoesNotExist:
            return None

    return await _get()


async def get_city(city_id: int):
    """Get city by ID."""
    from asgiref.sync import sync_to_async

    @sync_to_async
    def _get():
        try:
            return City.objects.get(id=city_id)
        except City.DoesNotExist:
            return None

    return await _get()


async def update_ad_and_moderate(
    ad_id: int,
    title_ru: str,
    desc_ru: str,
    category_id: int | None,
    city_id: int | None,
    price: int | None,
    photos: list,
    user_id: int | None,
    title_bs: str = "",
    desc_bs: str = "",
    title_en: str = "",
    desc_en: str = "",
    original_language: str | None = None,
    listing_purpose_id: int | None = None,
    feature_ids: list[int] | None = None,
) -> tuple[bool, list[str]]:
    """Update ad with multi-language content, create images, and delegate to shared auto_moderate.

    Backward-compatible: new language fields default to empty strings.
    Russian (title_ru/desc_ru) remains the base content stored in title/description columns.
    """
    from asgiref.sync import sync_to_async
    from apps.moderation.services.auto_moderation import auto_moderate

    @sync_to_async
    def _update_and_moderate() -> tuple[bool, list[str]]:
        from django.db import transaction

        try:
            ad = Ad.objects.get(id=ad_id)
        except Ad.DoesNotExist:
            return False, ["Ad not found"]

        # Update ad fields — Russian remains the base content
        ad.title = title_ru
        ad.description = desc_ru
        ad.category_id = category_id
        ad.city_id = city_id
        ad.price = price

        # Store multi-language translations
        if title_bs:
            ad.title_bs = title_bs
        if desc_bs:
            ad.description_bs = desc_bs
        if title_en:
            ad.title_en = title_en
        if desc_en:
            ad.description_en = desc_en
        if original_language:
            ad.original_language = original_language

        # Save listing purpose
        if listing_purpose_id:
            ad.listing_purpose_id = listing_purpose_id

        # Generate thumbnails BEFORE the DB transaction (filesystem I/O outside tx)
        # so a DB rollback does not leave filesystem and DB desynced.
        for photo in photos:
            try:
                original_path = os.path.join(
                    settings.MEDIA_ROOT, photo["storage_key"]
                )
                with open(original_path, "rb") as f:
                    photo_bytes = f.read()

                thumbnail_service = ThumbnailService(settings.MEDIA_ROOT)
                thumbnail_keys = thumbnail_service.generate_thumbnails(
                    photo_bytes, photo["storage_key"]
                )

                photo["thumbnail_small"] = thumbnail_keys.get(
                    ThumbnailSizeStrEnum.SMALL
                )
                photo["thumbnail_medium"] = thumbnail_keys.get(
                    ThumbnailSizeStrEnum.MEDIUM
                )
                photo["thumbnail_large"] = thumbnail_keys.get(
                    ThumbnailSizeStrEnum.LARGE
                )
            except Exception:
                logger.exception(
                    "Failed to generate thumbnails for %s",
                    photo["storage_key"],
                )
                photo["thumbnail_small"] = None
                photo["thumbnail_medium"] = None
                photo["thumbnail_large"] = None

        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
            ad.save()

            # Save features (M2M via through model)
            if feature_ids is not None:
                ad.features.set(feature_ids)

            # Create AdImage records with pre-generated thumbnails
            for photo in photos:
                AdImage.objects.create(
                    ad_id=ad_id,
                    image=photo["storage_key"],
                    telegram_file_id=photo["telegram_file_id"],
                    position=photo["position"],
                    thumbnail_small=photo.get("thumbnail_small"),
                    thumbnail_medium=photo.get("thumbnail_medium"),
                    thumbnail_large=photo.get("thumbnail_large"),
                )

            # Transition DRAFT -> ON_MODERATION (state machine requires this step)
            ad.transition_to(AdStatus.ON_MODERATION)

        # Delegate to shared auto-moderation service
        # Handles: banned_words, duplicate_title, all validations,
        # ModeratorActionLog, AnalyticsEvent (with enum member), status transitions
        passed = auto_moderate(ad)

        if passed:
            return True, []
        else:
            return False, ["Ad failed moderation checks"]

    return await _update_and_moderate()

async def translate_all_languages(text: str, target_locales: list[str]) -> dict[str, str]:
    """Translate text to all target languages in parallel.

    Delegates to the shared translation service (apps.core.services.translation)
    which provides 500ms timeout, circuit breaker, and LRU cache.

    Args:
        text: Source text to translate.
        target_locales: List of target locale codes (e.g. ['ru', 'bs', 'en']).

    Returns:
        Dict mapping locale codes to translated text. Falls back to original
        text on failure (via the shared service's graceful fallback).
    """
    results = await asyncio.gather(
        *[asyncio.to_thread(translate_text, text, "auto", loc)
          for loc in target_locales]
    )
    return dict(zip(target_locales, results, strict=True))


# --- Purpose / Feature helper functions ---

async def get_resolved_purposes(category_id: int) -> list:
    """Get resolved listing purposes for a category."""
    from asgiref.sync import sync_to_async
    from apps.categories.services.lookup_resolution import CategoryLookupResolver

    @sync_to_async
    def _get():
        from apps.categories.models import Category
        try:
            cat = Category.objects.get(id=category_id)
        except Category.DoesNotExist:
            return []
        resolver = CategoryLookupResolver()
        return list(resolver.get_resolved_purposes(cat))

    return await _get()


async def get_resolved_features(category_id: int) -> list:
    """Get resolved listing features for a category."""
    from asgiref.sync import sync_to_async
    from apps.categories.services.lookup_resolution import CategoryLookupResolver

    @sync_to_async
    def _get():
        from apps.categories.models import Category
        try:
            cat = Category.objects.get(id=category_id)
        except Category.DoesNotExist:
            return []
        resolver = CategoryLookupResolver()
        return list(resolver.get_resolved_features(cat))

    return await _get()


async def get_default_purpose(category_id: int, purposes: list) -> object | None:
    """Get the default purpose for a category, if configured."""
    from asgiref.sync import sync_to_async
    from apps.categories.models import CategoryListingPurpose

    @sync_to_async
    def _get():
        try:
            clp = CategoryListingPurpose.objects.get(
                category_id=category_id,
                is_default=True,
            )
            return clp.listing_purpose
        except CategoryListingPurpose.DoesNotExist:
            return None

    return await _get()


async def get_lookup_item_by_slug(slug: str):
    """Get a LookupItem by slug."""
    from asgiref.sync import sync_to_async
    from apps.lookups.models import LookupItem

    @sync_to_async
    def _get():
        try:
            return LookupItem.objects.get(slug=slug)
        except LookupItem.DoesNotExist:
            return None

    return await _get()


async def get_lookup_item(item_id: int | None):
    """Get a LookupItem by ID."""
    if item_id is None:
        return None
    from asgiref.sync import sync_to_async
    from apps.lookups.models import LookupItem

    @sync_to_async
    def _get():
        try:
            return LookupItem.objects.get(id=item_id)
        except LookupItem.DoesNotExist:
            return None

    return await _get()


async def get_feature_names(feature_ids: list[int]) -> list[str]:
    """Get feature names as localized strings."""
    from asgiref.sync import sync_to_async
    from apps.lookups.models import LookupItem

    @sync_to_async
    def _get():
        items = LookupItem.objects.filter(id__in=feature_ids)
        names = []
        for item in items:
            if item.name_i18n and isinstance(item.name_i18n, dict):
                names.append(item.name_i18n.get("ru", item.slug))
            else:
                names.append(item.slug)
        return names

    return await _get()


def build_purpose_keyboard(purposes: list, default_slug: str | None = None) -> types.InlineKeyboardMarkup:
    """Build inline keyboard for purpose selection."""
    builder = InlineKeyboardBuilder()
    for purpose in purposes:
        text = purpose.name_i18n.get("ru", purpose.slug) if purpose.name_i18n else purpose.slug
        if purpose.slug == default_slug:
            text = f"✅ {text}"
        builder.button(text=text, callback_data=f"purpose:{purpose.slug}")
    builder.adjust(2)
    return builder.as_markup()


def build_feature_keyboard(features: list, selected_ids: set) -> types.InlineKeyboardMarkup:
    """Build inline keyboard for feature multi-selection."""
    builder = InlineKeyboardBuilder()
    for feature in features:
        text = feature.name_i18n.get("ru", feature.slug) if feature.name_i18n else feature.slug
        if feature.id in selected_ids:
            text = f"✅ {text}"
        builder.button(text=text, callback_data=f"feature:{feature.id}")
    builder.button(text="✔️ Done", callback_data="features_done")
    builder.adjust(2)
    return builder.as_markup()