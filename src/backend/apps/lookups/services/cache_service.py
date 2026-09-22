"""
LookupCacheService — caching layer for LookupGroup and LookupItem records.

All lookup records are cached with stale-while-revalidate (SWR) and a
version-bump invalidation strategy. Cache is invalidated on post_save /
post_delete signals for LookupGroup and LookupItem via
``bump_lookup_version``, which atomically increments a content-freshness
counter embedded in every cache key. Old entries become unreachable and
expire via TTL — no global prefix wipe (thundering-herd risk).

SWR provides a single-flight lock (stampede guard) and a stale-serve
window so concurrent misses after invalidation produce one recompute
winner while other workers serve stale data.

Reference: ``apps/core/utils/swr_cache.py`` / ``apps/search/services/cache.py``.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import TYPE_CHECKING

from django.core.cache import cache

from apps.core.utils.swr_cache import get_with_stale_revalidate

if TYPE_CHECKING:
    from apps.lookups.models import LookupGroup, LookupItem

logger = logging.getLogger(__name__)


class LookupCacheKey(StrEnum):
    """Versioned namespace prefix for lookup cache keys.

    Bump the version segment (e.g. to ``lookup:v2``) when the cache entry
    format changes to avoid stale-entry deserialization errors.
    """

    V1 = "lookup:v1"


# Content-freshness version token.  Bumped whenever lookup data changes
# so that cached entries become unreachable (the version is embedded in
# every cache key).  Mirrors ``search:content_version`` in
# ``apps/search/services/cache.py``.
LOOKUP_CONTENT_VERSION_KEY = "lookup:content_version"

# SWR TTL configuration (seconds).
# Stale-while-revalidate: 1 hour fresh + 10 min stale window + 30 s lock.
# The lock TTL (30 s) is deliberately shorter than the stale window (600 s)
# so a crashed worker releases the lock before stale data expires.
LOOKUP_CACHE_TTL: int = 3600
LOOKUP_CACHE_STALE_TTL: int = 600
LOOKUP_CACHE_LOCK_TTL: int = 30


def get_lookup_version() -> int:
    """Return the current lookup content version (0 when never bumped).

    Mirrors ``get_search_version`` in ``apps/search/services/cache.py``.
    """
    return int(cache.get(LOOKUP_CONTENT_VERSION_KEY, 0) or 0)


def bump_lookup_version() -> None:
    """Increment the lookup content version to invalidate cached entries.

    Uses ``cache.incr`` (atomic on Redis, thread-safe on LocMemCache);
    falls back to ``cache.set`` when the key does not exist yet.

    Mirrors ``bump_tree_version`` in ``apps/categories/cache.py``.
    """
    try:
        cache.incr(LOOKUP_CONTENT_VERSION_KEY)
    except ValueError:
        cache.set(LOOKUP_CONTENT_VERSION_KEY, 1)
        logger.debug("Initialized lookup content version to 1")


def all_groups_key() -> str:
    """Build the versioned cache key for all lookup groups."""
    return f"{LookupCacheKey.V1}:{get_lookup_version()}:all_groups"


def active_items_key(group_code: str) -> str:
    """Build the versioned cache key for active items of a group.

    Args:
        group_code: The code of the lookup group.
    """
    return f"{LookupCacheKey.V1}:{get_lookup_version()}:items:{group_code}"


class LookupCacheService:
    """Cache service for lookup groups and items.

    Provides static methods for getting cached lookup data and
    invalidating the cache when records change.  Reads use
    ``get_with_stale_revalidate`` for single-flight + stale-serve;
    invalidation uses version-bump (``bump_lookup_version``).
    """

    @staticmethod
    def get_all_groups() -> list[LookupGroup]:
        """Get all lookup groups (cached with SWR).

        Returns:
            List of LookupGroup instances (with prefetched items).
        """
        from apps.lookups.models import LookupGroup

        cache_key = all_groups_key()
        result = get_with_stale_revalidate(
            cache_key,
            lambda: list(
                LookupGroup.objects.all()
                .prefetch_related("items")
                .order_by("sort_order")
            ),
            ttl=LOOKUP_CACHE_TTL,
            stale_ttl=LOOKUP_CACHE_STALE_TTL,
            lock_ttl=LOOKUP_CACHE_LOCK_TTL,
            default=[],
        )
        return list(result)

    @staticmethod
    def get_active_items(group_code: str) -> list[LookupItem]:
        """Get active items for a group (cached with SWR).

        Args:
            group_code: The code of the lookup group.

        Returns:
            List of active LookupItem instances ordered by sort_order.
        """
        from apps.lookups.models import LookupItem

        cache_key = active_items_key(group_code)
        result = get_with_stale_revalidate(
            cache_key,
            lambda: list(
                LookupItem.objects.filter(
                    group__code=group_code,
                    is_active=True,
                )
                .order_by("sort_order")
                .select_related("group")
            ),
            ttl=LOOKUP_CACHE_TTL,
            stale_ttl=LOOKUP_CACHE_STALE_TTL,
            lock_ttl=LOOKUP_CACHE_LOCK_TTL,
            default=[],
        )
        return list(result)

    @staticmethod
    def invalidate_all() -> None:
        """Invalidate all lookup caches by bumping the content version.

        Old entries become unreachable (new reads embed the bumped version in
        the key) and expire via TTL in the background.  No global prefix wipe
        is needed.
        """
        bump_lookup_version()
        logger.debug("Invalidated all lookup caches (version bump)")

    @staticmethod
    def invalidate_group(group_code: str) -> None:
        """Invalidate cache for a specific group by bumping the content version.

        A single global version bump is used (rather than a targeted key
        delete) because lookup invalidation is infrequent (admin operation)
        and version-bump prevents thundering-herd across all lookup entries.

        Args:
            group_code: The code of the group to invalidate.
        """
        bump_lookup_version()
        logger.debug(
            "Invalidated lookup cache for group: %s (version bump)", group_code
        )
