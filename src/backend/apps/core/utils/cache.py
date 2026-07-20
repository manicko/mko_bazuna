"""
Django cache utilities for Mko Bazuna.

Provides cached singleton access for ModerationCriteria with TTL support.
"""

from typing import Final

from django.core.cache import cache

CRITERIA_CACHE_KEY: Final[str] = "moderation_criteria:v1"
CRITERIA_CACHE_TTL: Final[int] = 300  # 5 minutes


def get_cached_criteria(key: str = CRITERIA_CACHE_KEY) -> dict | None:
    """
    Get cached ModerationCriteria values.

    Args:
        key: Cache key (defaults to moderation_criteria:v1)

    Returns:
        Dict with criteria values or None if not cached
    """
    return cache.get(key)


def set_cached_criteria(
    value: dict,
    key: str = CRITERIA_CACHE_KEY,
    ttl: int = CRITERIA_CACHE_TTL,
) -> None:
    """
    Set cached ModerationCriteria values.

    Args:
        value: Dict of criteria values to cache
        key: Cache key (defaults to moderation_criteria:v1)
        ttl: Time-to-live in seconds (defaults to 300)
    """
    cache.set(key, value, ttl)


def invalidate_criteria_cache(key: str = CRITERIA_CACHE_KEY) -> None:
    """
    Invalidate the cached ModerationCriteria.

    Called when admin updates criteria to ensure fresh values on next access.

    Args:
        key: Cache key to invalidate (defaults to moderation_criteria:v1)
    """
    cache.delete(key)