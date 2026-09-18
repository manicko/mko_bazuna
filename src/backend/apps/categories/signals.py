"""
Signal handlers for categories app.

Invalidates CategoryLookupResolver caches on through-table changes,
any LookupItem change (name, slug, is_active, etc.), and Category MPTT moves.
Also bumps the category tree version so header submenu fragments are
invalidated on structural Category / CategoryPath changes.
"""

import logging

import redis
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django_redis.exceptions import ConnectionInterrupted

logger = logging.getLogger(__name__)


@receiver(post_save, sender="categories.Category")
@receiver(post_delete, sender="categories.Category")
@receiver(post_save, sender="categories.CategoryPath")
@receiver(post_delete, sender="categories.CategoryPath")
def bump_tree_version_on_structure_change(sender, instance, **kwargs):  # type: ignore[no-untyped-def]
    """Invalidate header submenu fragments when the category tree changes."""
    from apps.categories.cache import bump_tree_version

    bump_tree_version()
    logger.debug("Bumped category tree version due to %s change", sender.__name__)


@receiver(post_save, sender="categories.CategoryListingPurpose")
@receiver(post_delete, sender="categories.CategoryListingPurpose")
@receiver(post_save, sender="categories.CategoryListingFeature")
@receiver(post_delete, sender="categories.CategoryListingFeature")
@receiver(post_save, sender="categories.CategoryListingCondition")
@receiver(post_delete, sender="categories.CategoryListingCondition")
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
    """Invalidate resolved lookup caches on any LookupItem change.

    Fires on ALL LookupItem post_save events (name_i18n, slug, is_active, etc.),
    not just ``is_active`` toggles, so that RESOLVED_* caches (purposes,
    features, conditions) reflect the latest LookupItem data. Cache
    invalidation is best-effort: a cache backend failure must never prevent the
    originating DB save from committing. A stale cache will simply be refreshed
    on the next read.
    """
    from apps.categories.services.lookup_resolution import CategoryLookupResolver

    resolver = CategoryLookupResolver()
    try:
        resolver.invalidate_lookup_item(instance.id)
    except ConnectionInterrupted, redis.RedisError:
        logger.warning(
            "Cache backend unavailable — resolved lookup caches not "
            "invalidated after LookupItem %d change; cache will refresh "
            "on next read",
            instance.id,
        )
    else:
        logger.debug(
            "Invalidated lookup caches due to LookupItem %d change", instance.id
        )
