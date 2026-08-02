"""
Signal handlers for categories app.

Invalidates CategoryLookupResolver caches on through-table changes,
LookupItem is_active toggles, and Category MPTT moves.
"""

import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender="categories.CategoryListingPurpose")
@receiver(post_delete, sender="categories.CategoryListingPurpose")
@receiver(post_save, sender="categories.CategoryListingFeature")
@receiver(post_delete, sender="categories.CategoryListingFeature")
def invalidate_category_lookup_cache(sender, instance, **kwargs):  # type: ignore[no-untyped-def]
    """Invalidate resolved lookup caches when through-table bindings change."""
    from apps.categories.services.lookup_resolution import CategoryLookupResolver

    resolver = CategoryLookupResolver()
    resolver.invalidate_category(instance.category_id)
    logger.debug(
        "Invalidated lookup cache for category %d due to %s change",
        instance.category_id,
        sender.__name__,
    )


@receiver(post_save, sender="lookups.LookupItem")
def invalidate_on_lookup_item_change(sender, instance, **kwargs):  # type: ignore[no-untyped-def]
    """Invalidate all caches when a LookupItem's is_active field changes."""
    from apps.categories.services.lookup_resolution import CategoryLookupResolver

    update_fields = kwargs.get("update_fields")
    if update_fields is not None and "is_active" not in update_fields:
        return

    resolver = CategoryLookupResolver()
    resolver.invalidate_lookup_item(instance.id)
    logger.debug(
        "Invalidated lookup caches due to LookupItem %d change", instance.id
    )