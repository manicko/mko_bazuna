"""
Signal handlers for lookups app.

Invalidates lookup caches on LookupGroup/LookupItem save/delete.
"""

import logging

import redis
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django_redis.exceptions import ConnectionInterrupted

logger = logging.getLogger(__name__)


@receiver(post_save, sender="lookups.LookupGroup")
@receiver(post_delete, sender="lookups.LookupGroup")
@receiver(post_save, sender="lookups.LookupItem")
@receiver(post_delete, sender="lookups.LookupItem")
def invalidate_lookup_cache(sender, instance, **kwargs):  # type: ignore[no-untyped-def]
    """Invalidate lookup caches when any lookup record changes.

    Cache invalidation is best-effort: a cache backend failure (e.g. Redis
    unreachable during a one-shot data-load service) must never prevent the
    originating DB save/delete from succeeding. A stale cache will simply be
    refreshed on the next read.
    """
    from apps.lookups.services.cache_service import LookupCacheService

    try:
        LookupCacheService.invalidate_all()
    except ConnectionInterrupted, redis.RedisError:
        logger.warning(
            "Cache backend unavailable — lookup cache not invalidated after "
            "%s change; cache will refresh on next read",
            sender.__name__,
        )
    else:
        logger.debug("Invalidated lookup cache due to %s change", sender.__name__)
