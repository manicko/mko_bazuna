"""
CategoryLookupResolver — inherits purposes and features via MPTT ancestor walk-up.

Resolution algorithm (nearest-explicit-ancestor-wins):
1. Get all ancestor IDs including self via MPTT (1 query)
2. Fetch all active through-row bindings for those ancestors (1 query)
3. Group by category_id; return bindings for the first (nearest) group with rows

Caching uses Django's cache framework with 300s TTL. Invalidation is
signal-based (best-effort, per worker process).
"""

import logging
from typing import TYPE_CHECKING

from django.core.cache import cache

if TYPE_CHECKING:
    from apps.categories.models import Category
    from apps.lookups.models import LookupItem

logger = logging.getLogger(__name__)

RESOLVED_PURPOSES_PREFIX = "lookup:resolved_purposes"
RESOLVED_FEATURES_PREFIX = "lookup:resolved_features"

RESOLVED_CONDITIONS_PREFIX = "lookup:resolved_conditions"
CACHE_TTL = 300  # 5 minutes


class CategoryLookupResolver:
    """Resolves inherited listing purposes and features for a category.

    Walks the canonical MPTT ancestor chain to find the nearest explicit
    definition (nearest-ancestor-wins). Results are cached with 300s TTL.
    """

    @staticmethod
    def get_resolved_purposes(category: Category) -> list[LookupItem]:
        """Get resolved listing purposes for a category (inherited + active only)."""
        return CategoryLookupResolver._resolve(
            category=category,
            through_model_name="CategoryListingPurpose",
            cache_key_prefix=RESOLVED_PURPOSES_PREFIX,
            item_field="listing_purpose",
        )

    @staticmethod
    def get_resolved_features(category: Category) -> list[LookupItem]:
        """Get resolved listing features for a category (inherited + active only)."""
        return CategoryLookupResolver._resolve(
            category=category,
            through_model_name="CategoryListingFeature",
            cache_key_prefix=RESOLVED_FEATURES_PREFIX,
            item_field="feature",
        )

    @staticmethod
    def get_resolved_purpose_codes(category: Category) -> list[str]:
        """Get resolved purpose codes as string slugs."""
        return [
            str(item.slug)
            for item in CategoryLookupResolver.get_resolved_purposes(category)
        ]

    @staticmethod
    def get_resolved_feature_codes(category: Category) -> list[str]:
        """Get resolved feature codes as string slugs."""
        return [
            str(item.slug)
            for item in CategoryLookupResolver.get_resolved_features(category)
        ]

    @staticmethod
    def invalidate_category(category_id: int) -> None:
        """Invalidate cache for a category and all its descendants."""
        from apps.categories.models import Category

        try:
            category = Category.objects.get(id=category_id)
        except Category.DoesNotExist:
            cache.delete(f"{RESOLVED_PURPOSES_PREFIX}:{category_id}")
            cache.delete(f"{RESOLVED_FEATURES_PREFIX}:{category_id}")
            cache.delete(f"{RESOLVED_CONDITIONS_PREFIX}:{category_id}")
            return

        descendants = category.get_descendants(include_self=True)
        for desc in descendants:
            cache.delete(f"{RESOLVED_PURPOSES_PREFIX}:{desc.id}")
            cache.delete(f"{RESOLVED_FEATURES_PREFIX}:{desc.id}")
            cache.delete(f"{RESOLVED_CONDITIONS_PREFIX}:{desc.id}")

    @staticmethod
    def invalidate_lookup_item(lookup_item_id: int) -> None:
        """Invalidate cache for all categories that reference a given LookupItem."""
        # Find categories through through-table bindings
        category_ids = set()
        clp = CategoryLookupResolver._get_through_model("CategoryListingPurpose")
        clf = CategoryLookupResolver._get_through_model("CategoryListingFeature")
        clc = CategoryLookupResolver._get_through_model("CategoryListingCondition")

        if clp:
            cat_ids = list(
                clp.objects.filter(listing_purpose_id=lookup_item_id)
                .values_list("category_id", flat=True)
                .distinct()
            )
            category_ids.update(cat_ids)

        if clf:
            cat_ids = list(
                clf.objects.filter(feature_id=lookup_item_id)
                .values_list("category_id", flat=True)
                .distinct()
            )
            category_ids.update(cat_ids)

        if clc:
            cat_ids = list(
                clc.objects.filter(listing_condition_id=lookup_item_id)
                .values_list("category_id", flat=True)
                .distinct()
            )
            category_ids.update(cat_ids)

        for cat_id in category_ids:
            CategoryLookupResolver.invalidate_category(cat_id)

        # Also invalidate ad-level cache since ads may reference this item
        # delete_pattern is only available on Redis cache backend
        if hasattr(cache, "delete_pattern"):
            cache.delete_pattern(f"{RESOLVED_PURPOSES_PREFIX}:*")
            cache.delete_pattern(f"{RESOLVED_FEATURES_PREFIX}:*")
            cache.delete_pattern(f"{RESOLVED_CONDITIONS_PREFIX}:*")

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
        category: Category,
        through_model_name: str,
        cache_key_prefix: str,
        item_field: str,
    ) -> list[LookupItem]:
        """Core resolution algorithm — nearest-explicit-ancestor-wins.

        1. Check cache
        2. Get ancestors including self (ascending = leaf to root)
        3. Query through-table bindings for all ancestors
        4. Return first ancestor group with rows
        5. Cache result
        """
        cache_key = f"{cache_key_prefix}:{category.id}"
        cached = cache.get(cache_key)
        if cached is not None:
            return list(cached)

        # Get ancestors including self, leaf-to-root order
        ancestors = list(category.get_ancestors(include_self=True, ascending=True))

        # Get through model
        ThroughModel = CategoryLookupResolver._get_through_model(through_model_name)
        if ThroughModel is None:
            logger.warning("Through model %s not found", through_model_name)
            return []

        # Build filter: the FK field name in through model is either listing_purpose or feature
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

        # Cache the result (as list of PKs to avoid serialization issues)
        cache.set(cache_key, result, CACHE_TTL)
        return result

    @staticmethod
    def get_resolved_conditions(category: Category) -> list[LookupItem]:
        """Get resolved listing conditions for a category (inherited + active only)."""
        return CategoryLookupResolver._resolve(
            category=category,
            through_model_name="CategoryListingCondition",
            cache_key_prefix=RESOLVED_CONDITIONS_PREFIX,
            item_field="listing_condition",
        )

    @staticmethod
    def get_resolved_condition_codes(category: Category) -> list[str]:
        """Get resolved condition codes as string slugs."""
        return [
            str(item.slug)
            for item in CategoryLookupResolver.get_resolved_conditions(category)
        ]
