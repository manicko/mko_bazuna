"""
LookupCacheService — caching layer for LookupGroup and LookupItem records.

All lookup records are cached with 1-hour TTL. Cache is invalidated on
post_save / post_delete signals for LookupGroup and LookupItem.
"""

import logging
from typing import Any

from django.core.cache import cache

logger = logging.getLogger(__name__)

ALL_GROUPS_CACHE_KEY = "lookup:all_groups"
ACTIVE_ITEMS_PREFIX = "lookup:active_items"
CACHE_TTL = 3600  # 1 hour


class LookupCacheService:
    """Cache service for lookup groups and items.

    Provides static methods for getting cached lookup data and
    invalidating the cache when records change.
    """

    @staticmethod
    def get_all_groups() -> list[Any]:
        """Get all lookup groups (cached).

        Returns:
            List of LookupGroup instances (with prefetched items).
        """
        from apps.lookups.models import LookupGroup

        cached = cache.get(ALL_GROUPS_CACHE_KEY)
        if cached is not None:
            return list(cached)

        groups = list(
            LookupGroup.objects.all().prefetch_related("items").order_by("sort_order")
        )
        cache.set(ALL_GROUPS_CACHE_KEY, groups, CACHE_TTL)
        return groups

    @staticmethod
    def get_active_items(group_code: str) -> list[Any]:
        """Get active items for a group (cached).

        Args:
            group_code: The code of the lookup group.

        Returns:
            List of active LookupItem instances ordered by sort_order.
        """
        from apps.lookups.models import LookupItem

        cache_key = f"{ACTIVE_ITEMS_PREFIX}:{group_code}"
        cached = cache.get(cache_key)
        if cached is not None:
            return list(cached)

        items = list(
            LookupItem.objects.filter(
                group__code=group_code,
                is_active=True,
            ).order_by("sort_order").select_related("group")
        )
        cache.set(cache_key, items, CACHE_TTL)
        return items

    @staticmethod
    def invalidate_all() -> None:
        """Invalidate all lookup caches."""
        cache.delete(ALL_GROUPS_CACHE_KEY)
        # delete_pattern is only available on Redis cache backend
        if hasattr(cache, "delete_pattern"):
            cache.delete_pattern(f"{ACTIVE_ITEMS_PREFIX}:*")
        logger.debug("Invalidated all lookup caches")

    @staticmethod
    def invalidate_group(group_code: str) -> None:
        """Invalidate cache for a specific group.

        Args:
            group_code: The code of the group to invalidate.
        """
        cache.delete(f"{ACTIVE_ITEMS_PREFIX}:{group_code}")
        cache.delete(ALL_GROUPS_CACHE_KEY)
        logger.debug("Invalidated cache for group: %s", group_code)