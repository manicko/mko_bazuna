"""
Ad-creation data service for the Telegram bot.

Extracted from ``telegram_bot/handlers/ad_create.py``: the sync-to-async ORM
helpers, the media helpers (``download_photo``, ``save_photo``), the
``translate_all_languages`` helper, and the four inline-keyboard builders.

Import direction: bot -> backend. This module may import from ``apps.*`` but
``apps.*`` must never import ``telegram_bot.*``.

All fixed values are constants — callback tokens via ``BotCallbackPrefix`` and
locale codes via ``LanguageLocale`` — per project rule 10. Keyboard button
labels that are user-facing literals are wrapped in ``gettext`` per rule 16.
"""

import asyncio
import logging
import os

from aiogram import Bot, types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils.translation import gettext as _

from apps.ads.models import Ad
from apps.categories.models import Category, CategoryListingPurpose
from apps.categories.services.lookup_resolution import CategoryLookupResolver
from apps.core.enums import AdStatus
from apps.core.services.translation import translate_text
from apps.locations.models import City
from apps.lookups.models import LookupItem
from apps.media.services.filesystem import (
    STAGING_PREFIX,
    delete_photo,
    generate_storage_key,
    strip_photo_exif,
)
from telegram_bot.schemas.callbacks import BotCallbackPrefix

logger = logging.getLogger(__name__)

__all__ = [
    "create_draft_ad",
    "_get_ad_status",
    "delete_draft",
    "search_categories",
    "get_city_by_name",
    "get_all_cities",
    "download_photo",
    "save_photo",
    "get_category",
    "get_city",
    "translate_all_languages",
    "get_resolved_purposes",
    "get_resolved_features",
    "get_resolved_conditions",
    "get_default_purpose",
    "get_lookup_item_by_slug",
    "get_lookup_item",
    "get_feature_names",
    "build_currency_keyboard",
    "build_purpose_keyboard",
    "build_condition_keyboard",
    "build_feature_keyboard",
]


# ---------------------------------------------------------------------------
# ORM helpers (sync_to_async)
# ---------------------------------------------------------------------------


async def create_draft_ad(user_id: int) -> Ad:
    """Create a draft ad row, ensuring at most one in-progress DRAFT per user.

    If an existing DRAFT is found for the user, it is deleted first (with its
    AdImage rows CASCADE-deleted). The partial unique index
    ``uq_ads_single_draft_per_user`` fires ``IntegrityError`` as a backstop
    for any concurrent race that slips past this check; on such a race we
    retry once after cleaning up.
    """

    @sync_to_async
    def _create() -> Ad:
        # Remove any pre-existing in-progress DRAFT for this user before
        # creating a fresh one (Option D: delete + recreate). AdImage rows
        # CASCADE-delete via the FK. Orphaned media files are reclaimed by
        # sweep_orphaned_media.
        existing = Ad.objects.filter(user_id=user_id, status=AdStatus.DRAFT)
        if existing.exists():
            existing.delete()

        try:
            return Ad.objects.create(user_id=user_id, status=AdStatus.DRAFT)
        except IntegrityError:
            # Race: a concurrent create_draft_ad slipped through the above
            # check before the unique index was enforced. Clean up and retry.
            Ad.objects.filter(user_id=user_id, status=AdStatus.DRAFT).delete()
            return Ad.objects.create(user_id=user_id, status=AdStatus.DRAFT)

    return await _create()


async def _get_ad_status(ad_id: int) -> AdStatus | None:
    """Return the current ``AdStatus`` for *ad_id*, or ``None`` if it doesn't exist.

    Uses ``sync_to_async`` to perform the lightweight DB lookup off
    the bot's event loop, mirroring the TX-then-Filesystem pattern used
    throughout this module.
    """

    @sync_to_async
    def _get() -> AdStatus | None:
        status_str = (
            Ad.objects.filter(id=ad_id).values_list("status", flat=True).first()
        )
        if status_str is None:
            return None
        return AdStatus(status_str)

    return await _get()


async def delete_draft(ad_id: int) -> None:
    """Delete a draft ad and clean up its photo files."""

    @sync_to_async
    def _delete() -> None:
        try:
            ad = Ad.objects.get(id=ad_id, status=AdStatus.DRAFT)
        except Ad.DoesNotExist:
            return

        # Collect storage keys inside the transaction (DB-only read),
        # then delete the Ad row (DB-first). Filesystem deletion happens
        # only after the transaction commits — TX-then-Filesystem pattern
        # mirroring soft_delete_user_ads and sweep_drafts.
        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
            storage_keys = [
                key for img in ad.images.all() for key in img.storage_keys()
            ]
            ad.delete()

        # Delete physical media files after the transaction commits.
        # Filesystem deletions inside transaction.atomic() cannot be
        # rolled back, so a DB rollback would orphan DB rows pointing to
        # already-deleted files.
        for key in storage_keys:
            delete_photo(key)

    await _delete()


async def search_categories(keyword: str) -> list[Category]:
    """Search categories by keyword."""

    @sync_to_async
    def _search() -> list[Category]:
        return list(
            Category.objects.filter(name__icontains=keyword, is_active=True)[:5]
        )

    return await _search()


async def get_city_by_name(name: str) -> City | None:
    """Get city by exact name."""

    @sync_to_async
    def _get() -> City | None:
        try:
            return City.objects.get(name__iexact=name)
        except City.DoesNotExist:
            return None

    return await _get()


async def get_all_cities() -> list[City]:
    """Get all cities."""

    @sync_to_async
    def _get() -> list[City]:
        return list(City.objects.all())

    return await _get()


async def download_photo(file_id: str, bot: Bot) -> bytes | None:
    """Download photo bytes from Telegram."""

    try:
        file = await bot.download(file_id)

        return file.read() if file else None

    except Exception as e:
        logger.error("Failed to download photo %s: %s", file_id, e)

        return None


async def save_photo(storage_key: str, photo_bytes: bytes) -> str:
    """Save photo to filesystem via thread executor to avoid blocking the event loop.

    Strips EXIF/metadata and re-encodes the image before persisting to disk.

    Files are written to the ``staging/`` subdirectory of ``MEDIA_ROOT`` so
    that in-flight uploads are protected from the orphan sweep.  The returned
    key carries the ``staging/`` prefix and is promoted to permanent storage
    by ``submit_ad`` before AdImage rows are created.

    Uses ``os.open`` with ``O_CREAT|O_EXCL`` to guarantee atomic writes; on
    ``FileExistsError`` regenerates the storage key and retries.

    Returns:
        The final storage key used (may differ from the input on collision).
        The key carries the ``staging/`` prefix — ``submit_ad`` promotes it to
        permanent storage before creating AdImage rows.
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
        staging_key = f"{STAGING_PREFIX}{key}"
        media_path = os.path.join(settings.MEDIA_ROOT, staging_key)

        try:
            await asyncio.to_thread(_write, media_path, photo_bytes)

            return staging_key

        except FileExistsError:
            logger.warning("Storage key collision: %s, regenerating", key)

            key = generate_storage_key()


async def get_category(category_id: int) -> Category | None:
    """Get category by ID."""

    @sync_to_async
    def _get() -> Category | None:
        try:
            return Category.objects.get(id=category_id)
        except Category.DoesNotExist:
            return None

    return await _get()


async def get_city(city_id: int) -> City | None:
    """Get city by ID."""

    @sync_to_async
    def _get() -> City | None:
        try:
            return City.objects.get(id=city_id)
        except City.DoesNotExist:
            return None

    return await _get()


async def translate_all_languages(
    text: str, target_locales: list[str]
) -> dict[str, str]:
    """Translate text to all target languages in parallel.

    Uses an ``asyncio.Semaphore`` (created inside the coroutine to stay
    compatible with ``asyncio_mode=strict``) to bound concurrent ``to_thread``
    dispatches, and ``return_exceptions=True`` on ``asyncio.gather`` so one
    locale's failure does not cancel the batch.  Falls back to the original
    text on any failure.

    Call sites pass ``LanguageLocale.values()`` (e.g. ``["ru", "bs", "en"]``)
    so the locale list is never a bare literal (QLT-002).

    Args:
        text: Source text to translate.
        target_locales: List of target locale codes (e.g. ['ru', 'bs', 'en']).

    Returns:
        Dict mapping locale codes to translated text. Falls back to original
        text on failure (via the shared service's graceful fallback).
    """

    _sem = asyncio.Semaphore(len(target_locales))

    async def _translate_one(loc: str) -> str:
        async with _sem:
            return await asyncio.to_thread(translate_text, text, "auto", loc)

    results = await asyncio.gather(
        *(_translate_one(loc) for loc in target_locales),
        return_exceptions=True,
    )

    translated: dict[str, str] = {}
    for loc, result in zip(target_locales, results, strict=True):
        if isinstance(result, Exception):
            logger.warning(
                "Translation for %s raised: %s — falling back to original",
                loc,
                result,
            )
            translated[loc] = text
        else:
            translated[loc] = result
    return translated


# --- Purpose / Feature helper functions ---


async def get_resolved_purposes(category_id: int) -> list[LookupItem]:
    """Get resolved listing purposes for a category."""

    resolver = CategoryLookupResolver()

    @sync_to_async
    def _get() -> list[LookupItem]:
        try:
            cat = Category.objects.get(id=category_id)
        except Category.DoesNotExist:
            return []

        return list(resolver.get_resolved_purposes(cat))

    return await _get()


async def get_resolved_features(category_id: int) -> list[LookupItem]:
    """Get resolved listing features for a category."""

    resolver = CategoryLookupResolver()

    @sync_to_async
    def _get() -> list[LookupItem]:
        try:
            cat = Category.objects.get(id=category_id)
        except Category.DoesNotExist:
            return []

        return list(resolver.get_resolved_features(cat))

    return await _get()


async def get_resolved_conditions(category_id: int) -> list[LookupItem]:
    """Get resolved listing conditions for a category."""

    resolver = CategoryLookupResolver()

    @sync_to_async
    def _get() -> list[LookupItem]:
        try:
            cat = Category.objects.get(id=category_id)
        except Category.DoesNotExist:
            return []
        return list(resolver.get_resolved_conditions(cat))

    return await _get()


async def get_default_purpose(
    category_id: int, purposes: list[LookupItem]
) -> LookupItem | None:
    """Get the default purpose for a category, if configured."""

    @sync_to_async
    def _get() -> LookupItem | None:
        try:
            clp = CategoryListingPurpose.objects.get(
                category_id=category_id,
                is_default=True,
            )
            return clp.listing_purpose
        except CategoryListingPurpose.DoesNotExist:
            return None

    return await _get()


async def get_lookup_item_by_slug(slug: str) -> LookupItem | None:
    """Get a LookupItem by slug."""

    @sync_to_async
    def _get() -> LookupItem | None:
        try:
            return LookupItem.objects.get(slug=slug)
        except LookupItem.DoesNotExist:
            return None

    return await _get()


async def get_lookup_item(item_id: int | None) -> LookupItem | None:
    """Get a LookupItem by ID."""

    if item_id is None:
        return None

    @sync_to_async
    def _get() -> LookupItem | None:
        try:
            return LookupItem.objects.get(id=item_id)
        except LookupItem.DoesNotExist:
            return None

    return await _get()


async def get_feature_names(feature_ids: list[int], locale: str = "ru") -> list[str]:
    """Get feature names as localized strings."""

    @sync_to_async
    def _get() -> list[str]:
        items = LookupItem.objects.filter(id__in=feature_ids)

        names: list[str] = []

        for item in items:
            names.append(item.get_name(locale))

        return names

    return await _get()


# ---------------------------------------------------------------------------
# Inline keyboard builders
# ---------------------------------------------------------------------------


def build_currency_keyboard() -> types.InlineKeyboardMarkup:
    """Build the inline keyboard for currency selection (EUR first, PO-01)."""

    builder = InlineKeyboardBuilder()

    builder.button(
        text="🇪🇺 EUR", callback_data=f"{BotCallbackPrefix.PRICE_CURRENCY}EUR"
    )

    builder.button(
        text="🇷🇸 RSD", callback_data=f"{BotCallbackPrefix.PRICE_CURRENCY}RSD"
    )

    builder.button(
        text="🇧🇦 BAM", callback_data=f"{BotCallbackPrefix.PRICE_CURRENCY}BAM"
    )

    builder.button(text=_("🆓 Free"), callback_data=BotCallbackPrefix.PRICE_FREE)

    builder.adjust(2)

    return builder.as_markup()


def build_purpose_keyboard(
    purposes: list[LookupItem],
    default_slug: str | None = None,
    locale: str = "ru",
) -> types.InlineKeyboardMarkup:
    """Build inline keyboard for purpose selection."""

    builder = InlineKeyboardBuilder()

    for purpose in purposes:
        text = purpose.get_name(locale)

        if purpose.slug == default_slug:
            text = f"✅ {text}"

        builder.button(
            text=text, callback_data=f"{BotCallbackPrefix.PURPOSE}{purpose.slug}"
        )

    builder.adjust(2)

    return builder.as_markup()


def build_condition_keyboard(
    conditions: list[LookupItem],
    locale: str = "ru",
) -> types.InlineKeyboardMarkup:
    """Build inline keyboard for condition single-selection."""
    builder = InlineKeyboardBuilder()
    for condition in conditions:
        text = condition.get_name(locale)
        builder.button(
            text=text, callback_data=f"{BotCallbackPrefix.CONDITION}{condition.slug}"
        )
    builder.adjust(2)
    return builder.as_markup()


def build_feature_keyboard(
    features: list[LookupItem],
    selected_ids: set[int],
    locale: str = "ru",
) -> types.InlineKeyboardMarkup:
    """Build inline keyboard for feature multi-selection."""

    builder = InlineKeyboardBuilder()

    for feature in features:
        if feature.slug in ("new", "used"):
            continue
        text = feature.get_name(locale)

        if feature.id in selected_ids:
            text = f"✅ {text}"

        builder.button(
            text=text, callback_data=f"{BotCallbackPrefix.FEATURE}{feature.id}"
        )

    builder.button(text=_("✔️ Done"), callback_data=BotCallbackPrefix.FEATURES_DONE)

    builder.adjust(2)

    return builder.as_markup()
