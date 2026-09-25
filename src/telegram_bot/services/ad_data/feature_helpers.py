"""Purpose/feature/condition lookup helpers for the Telegram bot ad-creation service.

Resolves category listing purposes, features and conditions, plus generic
``LookupItem`` lookups, all wrapped in ``sync_to_async`` (bot -> backend
direction).
"""

import logging

from asgiref.sync import sync_to_async

from apps.categories.models import Category, CategoryListingPurpose
from apps.categories.services.lookup_resolution import CategoryLookupResolver
from apps.core.enums import LanguageLocale
from apps.lookups.models import LookupItem

logger = logging.getLogger(__name__)

__all__ = [
    "get_resolved_purposes",
    "get_resolved_features",
    "get_resolved_conditions",
    "get_default_purpose",
    "get_lookup_item_by_slug",
    "get_lookup_item",
    "get_feature_names",
]


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


async def get_feature_names(
    feature_ids: list[int], locale: str = LanguageLocale.RUSSIAN
) -> list[str]:
    """Get feature names as localized strings."""

    @sync_to_async
    def _get() -> list[str]:
        items = LookupItem.objects.filter(id__in=feature_ids)

        names: list[str] = []

        for item in items:
            names.append(item.get_name(locale))

        return names

    return await _get()
