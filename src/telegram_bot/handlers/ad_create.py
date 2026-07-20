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
from django.conf import settings
from django.utils import timezone

from apps.ads.models import Ad, AdImage
from apps.analytics.models import AnalyticsEvent
from apps.categories.models import Category
from apps.core.enums import AdStatus, AnalyticsEventType
from apps.locations.models import City
from apps.moderation.models import ModerationCriteria
from telegram_bot.schemas.message_payloads import (
    DescriptionPayload,
    PhotoCountPayload,
    PricePayload,
    TitlePayload,
)
from telegram_bot.services.media import generate_storage_key, validate_photo
from telegram_bot.states import AdCreateState

logger = logging.getLogger(__name__)

router = Router()


class AdCreateForm(StatesGroup):
    """FSM states for ad creation."""

    category = AdCreateState.CATEGORY
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
        await state.set_state(AdCreateForm.city)
        await message.answer(
            f"Category: {categories[0].name}\n"
            "Now select a city. Send a city name."
        )
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
            "Available cities: Sarajevo, Mostar, Banja Luka, etc."
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
    storage_key = generate_storage_key()
    await save_photo(storage_key, photo_bytes)

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

    preview_text = (
        f"Ad Preview:\n\n"
        f"Title: {data.get('title', 'N/A')}\n"
        f"Description: {data.get('description', 'N/A')[:100]}...\n"
        f"Price: {data.get('price', 'N/A')} BAM\n"
        f"Category: {category.name if category else 'N/A'}\n"
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

    text = message.text.strip().lower()

    if text == "confirm":
        data = await state.get_data()

        # Translate to Russian
        title_ru, desc_ru = await translate_to_russian(
            data.get("title", ""), data.get("description", "")
        )

        # Update ad with Russian content and run moderation
        is_valid, errors = await update_ad_and_moderate(
            ad_id=data["ad_id"],
            title_ru=title_ru,
            desc_ru=desc_ru,
            category_id=data.get("category_id"),
            city_id=data.get("city_id"),
            price=data.get("price"),
            photos=data.get("photos", []),
            user_id=data.get("user_id"),
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
    """Delete a draft ad."""
    from asgiref.sync import sync_to_async

    @sync_to_async
    def _delete() -> None:
        Ad.objects.filter(id=ad_id, status=AdStatus.DRAFT).delete()

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


async def save_photo(storage_key: str, photo_bytes: bytes) -> None:
    """Save photo to filesystem."""
    media_path = os.path.join(settings.MEDIA_ROOT, storage_key)
    os.makedirs(os.path.dirname(media_path), exist_ok=True)

    with open(media_path, "wb") as f:
        f.write(photo_bytes)


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


async def translate_to_russian(title: str, description: str) -> tuple[str, str]:
    """Translate content to Russian using deep-translator."""
    from deep_translator import GoogleTranslator

    try:
        title_ru = GoogleTranslator(source="auto", target="ru").translate(title)
    except Exception:
        title_ru = title

    try:
        desc_ru = GoogleTranslator(source="auto", target="ru").translate(description)
    except Exception:
        desc_ru = description

    return title_ru, desc_ru


async def update_ad_and_moderate(
    ad_id: int,
    title_ru: str,
    desc_ru: str,
    category_id: int | None,
    city_id: int | None,
    price: int | None,
    photos: list,
    user_id: int | None,
) -> tuple[bool, list[str]]:
    """Update ad with Russian content, create images, and run auto-moderation."""
    from asgiref.sync import sync_to_async

    @sync_to_async
    def _update_and_moderate() -> tuple[bool, list[str]]:
        try:
            ad = Ad.objects.get(id=ad_id)
        except Ad.DoesNotExist:
            return False, ["Ad not found"]

        criteria = ModerationCriteria.get_singleton()
        errors: list[str] = []

        # Update ad fields
        ad.title = title_ru
        ad.description = desc_ru
        ad.category_id = category_id
        ad.city_id = city_id
        ad.price = price

        # Validate before saving
        # Title length
        if len(ad.title) < criteria.title_min_length:
            errors.append("Title too short")

        # Description length
        if len(ad.description) < criteria.description_min_length:
            errors.append("Description too short")

        # Price required
        if criteria.price_required and ad.price is None:
            errors.append("Price is required")

        # Photo count (using photos list from state)
        photo_count = len(photos)
        if photo_count < criteria.min_images or photo_count > criteria.max_images:
            errors.append(f"Must have {criteria.min_images}-{criteria.max_images} photos")

        # Active ad count check
        if user_id:
            active_count = Ad.objects.filter(
                user_id=user_id, status=AdStatus.PUBLISHED
            ).count()
            if active_count >= criteria.max_ads_per_user:
                errors.append("Too many active ads")

        if errors:
            ad.status = AdStatus.ON_MODERATION_FAILED
            ad.moderation_failed_at = timezone.now()
            ad.save()
            return False, errors

        # Photos are valid - create AdImage records
        for photo in photos:
            AdImage.objects.create(
                ad_id=ad_id,
                image=photo["storage_key"],
                telegram_file_id=photo["telegram_file_id"],
                position=photo["position"],
            )

        # Approve
        ad.status = AdStatus.PUBLISHED
        ad.published_at = timezone.now()
        if ad.original_published_at is None:
            ad.original_published_at = timezone.now()
        ad.save()

        # Create analytics event
        AnalyticsEvent.objects.create(
            event_type=AnalyticsEventType.AD_PUBLISHED.value, user=user_id
        )

        return True, []

    return await _update_and_moderate()