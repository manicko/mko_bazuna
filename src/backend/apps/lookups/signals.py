"""
Signal handlers for lookups app.

Invalidates lookup caches on LookupGroup/LookupItem save/delete.
"""

import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender="lookups.LookupGroup")
@receiver(post_delete, sender="lookups.LookupGroup")
@receiver(post_save, sender="lookups.LookupItem")
@receiver(post_delete, sender="lookups.LookupItem")
def invalidate_lookup_cache(sender, instance, **kwargs):  # type: ignore[no-untyped-def]
    """Invalidate lookup caches when any lookup record changes."""
    from apps.lookups.services.cache_service import LookupCacheService

    LookupCacheService.invalidate_all()
    logger.debug("Invalidated lookup cache due to %s change", sender.__name__)