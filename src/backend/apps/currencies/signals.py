"""
Signal handlers for the currencies app.

Invalidates the cached current exchange rate whenever an ``ExchangeRate`` row is
created, updated or deleted, so the next ``PriceNormalizer`` read sees the new
value instead of a stale cached one.

The invalidation is best-effort: ``cache.delete`` raises
``ConnectionInterrupted`` under a Redis outage, and a receiver that let it escape
would roll back the saving transaction. The ``(ConnectionInterrupted,
redis.RedisError)`` guard below copies
``apps.categories.signals.invalidate_on_lookup_item_change`` verbatim; a stale
cache entry simply refreshes on the next read.
"""

import logging

import redis
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django_redis.exceptions import ConnectionInterrupted

from apps.currencies.enums import CurrencyCode

logger = logging.getLogger(__name__)


@receiver(post_save, sender="currencies.ExchangeRate")
@receiver(post_delete, sender="currencies.ExchangeRate")
def invalidate_rate_cache_on_change(sender, instance, **kwargs):  # type: ignore[no-untyped-def]
    """Invalidate the cached rate for ``instance.currency`` after a change."""
    from apps.currencies.services.price_normalizer import PriceNormalizer

    try:
        currency = CurrencyCode(instance.currency)
    except ValueError:
        # An unsupported currency has no cache entry to invalidate.
        logger.debug(
            "No cached rate to invalidate for unsupported currency %r",
            instance.currency,
        )
        return

    try:
        PriceNormalizer.invalidate_rate_cache(currency)
    except ConnectionInterrupted, redis.RedisError:
        logger.warning(
            "Cache backend unavailable — exchange-rate cache not invalidated "
            "after %s row change; cache will refresh on next read",
            instance.currency,
        )
    else:
        logger.debug(
            "Invalidated exchange-rate cache due to %s row change",
            instance.currency,
        )
