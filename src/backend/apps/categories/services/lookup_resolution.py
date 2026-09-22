"""
CategoryLookupResolver — inherits purposes and features via MPTT ancestor walk-up.

Resolution algorithm (nearest-explicit-ancestor-wins):
1. Get all ancestor IDs including self via MPTT (1 query)
2. Fetch all active through-row bindings for those ancestors (1 query)
3. Group by category_id; return bindings for the first (nearest) group with rows

Caching uses stale-while-revalidate (SWR) with a version-bump invalidation
strategy. Cache keys embed a content version (`lookup:resolve_version`) so
that invalidation makes old entries unreachable without a global prefix wipe
(thundering-herd). SWR provides a single-flight lock + stale-serve window.

Invalidation is signal-based (best-effort, per worker process) — callers
should not rely on immediate cache consistency across processes after a
data change.
"""

import logging
from enum import StrEnum
from typing import TYPE_CHECKING

from django.core.cache import cache

from apps.core.utils.swr_cache import get_with_stale_revalidate

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class LookupResolveCacheKey(StrEnum):
    """Versioned namespace prefix for resolved-lookup cache keys.

    Bump the version segment (e.g. to ``lookup:v2``) when the cache entry
    format changes to avoid stale-entry deserialization errors.
    """

    V1 = "lookup:v1:resolve"


# Content-freshness version token.  Bumped whenever lookup data or category
# bindings change so that cached resolved lookups become unreachable (the
# version is embedded in every cache key).  Mirrors ``search:content_version``.
LOOKUP_RESOLVE_VERSION_KEY = "lookup:resolve_version"

# SWR TTL configuration (seconds).
# Stale-while-revalidate: 5 min fresh + 1 min stale + 30 s lock.
# Mirrors the proven search-cache parameters (ttl=300, stale_ttl=60, lock=30).
LOOKUP_RESOLVE_CACHE_TTL: int = 300
LOOKUP_RESOLVE_CACHE_STALE_TTL: int = 60
LOOKUP_RESOLVE_CACHE_LOCK_TTL: int = 30

# Segments identifying each resolved-lookup type within the versioned key
# namespace.  These replace the former prefix constants that included the
# full key prefix (e.g. ``lookup:resolved_purposes`` → just ``purposes``).
RESOLVED_PURPOSES_SEGMENT = "purposes"
RESOLVED_FEATURES_SEGMENT = "features"
RESOLVED_CONDITIONS_SEGMENT = "conditions"

# Deprecated aliases — kept for backward compatibility with any external
# callers still importing the old prefix constants.  They return only the
# segment string, not a full cache key.
RESOLVED_PURPOSES_PREFIX = RESOLVED_PURPOSES_SEGMENT
RESOLVED_FEATURES_PREFIX = RESOLVED_FEATURES_SEGMENT
RESOLVED_CONDITIONS_PREFIX = RESOLVED_CONDITIONS_SEGMENT


def get_lookup_resolve_version() -> int:
    """Return the current resolved-lookup content version (0 when never bumped)."""
    return int(cache.get(LOOKUP_RESOLVE_VERSION_KEY, 0) or 0)


def bump_lookup_resolve_version() -> None:
    """Increment the resolved-lookup content version to invalidate cached entries.

    Uses ``cache.incr`` (atomic on Redis, thread-safe on LocMemCache);
    falls back to ``cache.set`` when the key does not exist yet.
    """
    try:
        cache.incr(LOOKUP_RESOLVE_VERSION_KEY)
    except ValueError:
        cache.set(LOOKUP_RESOLVE_VERSION_KEY, 1)
        logger.debug("Initialized lookup resolve version to 1")


def resolved_lookup_key(segment: str, category_id: int) -> str:
    """Build a versioned cache key for a resolved lookup type.

    Args:
        segment: The lookup type segment (e.g. ``"purposes"``).
        category_id: The category ID whose resolved lookups are cached.
    """
    return (
        f"{LookupResolveCacheKey.V1}:{get_lookup_resolve_version()}"
        f":{segment}:{category_id}"
    )


class CategoryLookupResolver:
    """Resolves inherited listing purposes and features for a category.

    Walks the canonical MPTT ancestor chain to find the nearest explicit
    definition (nearest-ancestor-wins). Results are cached with SWR and
    a version-bump invalidation strategy.
    """

    @staticmethod
    def get_resolved_purposes(category) -> list:  # type: ignore[type-arg]
        """Get resolved listing purposes for a category (inherited + active only)."""
        return CategoryLookupResolver._resolve(
            category=category,
            through_model_name="CategoryListingPurpose",
            key_segment=RESOLVED_PURPOSES_SEGMENT,
            item_field="listing_purpose",
        )

    @staticmethod
    def get_resolved_features(category) -> list:  # type: ignore[type-arg]
        """Get resolved listing features for a category (inherited + active only)."""
        return CategoryLookupResolver._resolve(
            category=category,
            through_model_name="CategoryListingFeature",
            key_segment=RESOLVED_FEATURES_SEGMENT,
            item_field="feature",
        )

    @staticmethod
    def get_resolved_purpose_codes(category) -> list[str]:
        """Get resolved purpose codes as string slugs."""
        return [
            str(item.slug)
            for item in CategoryLookupResolver.get_resolved_purposes(category)
        ]

    @staticmethod
    def get_resolved_feature_codes(category) -> list[str]:
        """Get resolved feature codes as string slugs."""
        return [
            str(item.slug)
            for item in CategoryLookupResolver.get_resolved_features(category)
        ]

    @staticmethod
    def invalidate_category(category_id: int) -> None:
        """Invalidate resolved-lookup caches for a category and all descendants.

        Uses version-bump (global) so old entries become unreachable without
        a prefix wipe.  The `category_id` parameter is accepted for API
        compatibility with the signal handler but does not narrow the scope
        — all resolved lookups share one version counter.
        """
        bump_lookup_resolve_version()
        logger.debug(
            "Invalidated resolved lookup caches for category %d (version bump)",
            category_id,
        )

    @staticmethod
    def invalidate_lookup_item(lookup_item_id: int) -> None:
        """Invalidate resolved-lookup caches for all categories referencing a LookupItem.

        Uses version-bump (global) — old entries become unreachable and expire
        via TTL.  The `lookup_item_id` parameter is accepted for API
        compatibility with the signal handler but does not narrow the scope.
        """
        bump_lookup_resolve_version()
        logger.debug(
            "Invalidated resolved lookup caches due to LookupItem %d change",
            lookup_item_id,
        )

    @staticmethod
    def _get_through_model(model_name: str):
        """Get a through model by name, handling import."""
        from django.apps import apps

        try:
            return apps.get_model("categories", model_name)
        except LookupError:
            return None

    @staticmethod
    def _resolve(
        category,
        through_model_name: str,
        key_segment: str,
        item_field: str,
    ) -> list:  # type: ignore[type-arg]
        """Core resolution algorithm — nearest-explicit-ancestor-wins.

        1. Check cache (SWR fresh/stale/cold-miss)
        2. Get ancestors including self (ascending = leaf to root)
        3. Query through-table bindings for all ancestors
        4. Return first ancestor group with rows
        5. SWR stores result with age-tracking for stale-serve
        """
        cache_key = resolved_lookup_key(key_segment, category.id)

        def _fetch():
            # Get ancestors including self, leaf-to-root order
            ancestors = list(
                category.get_ancestors(include_self=True, ascending=True)
            )

            # Get through model
            ThroughModel = CategoryLookupResolver._get_through_model(
                through_model_name
            )
            if ThroughModel is None:
                logger.warning("Through model %s not found", through_model_name)
                return []

            # Build filter: the FK field name in through model is either
            # listing_purpose or feature
            fk_filter = {f"{item_field}__is_active": True}

            # Query all bindings for ancestors
            bindings = ThroughModel.objects.filter(
                category__in=ancestors,
                **fk_filter,
            ).select_related(item_field)

            # Group by category_id
            grouped: dict[int, list] = {}
            for binding in bindings:
                grouped.setdefault(binding.category_id, []).append(
                    getattr(binding, item_field)
                )

            # Return first ancestor (nearest to leaf) with bindings
            result: list = []
            for ancestor in ancestors:
                if ancestor.id in grouped:
                    result = grouped[ancestor.id]
                    break

            return result

        result = get_with_stale_revalidate(
            cache_key,
            _fetch,
            ttl=LOOKUP_RESOLVE_CACHE_TTL,
            stale_ttl=LOOKUP_RESOLVE_CACHE_STALE_TTL,
            lock_ttl=LOOKUP_RESOLVE_CACHE_LOCK_TTL,
            default=[],
        )
        return list(result)

    @staticmethod
    def get_resolved_conditions(category) -> list:  # type: ignore[type-arg]
        """Get resolved listing conditions for a category (inherited + active only)."""
        return CategoryLookupResolver._resolve(
            category=category,
            through_model_name="CategoryListingCondition",
            key_segment=RESOLVED_CONDITIONS_SEGMENT,
            item_field="listing_condition",
        )

    @staticmethod
    def get_resolved_condition_codes(category) -> list[str]:
        """Get resolved condition codes as string slugs."""
        return [
            str(item.slug)
            for item in CategoryLookupResolver.get_resolved_conditions(category)
        ]
