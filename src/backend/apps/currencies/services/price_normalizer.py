"""
PriceNormalizer service — single entry point for computing EUR-normalized prices.

Normalizes a ``price_amount`` in a given ``CurrencyCode`` to its EUR
equivalent using the *current* ``ExchangeRate`` (the rate stored for
``is_current=True``). Rate lookups are cached with a 5-minute TTL, mirroring
the ``ModerationCriteria`` cache pattern in ``apps/core/utils/cache.py``.

Both the web and bot processes share one database, so the short cache is
acceptable. The cache is invalidated when a rate is updated (admin/recompute
path). An explicit domain error is raised when no current rate exists for a
currency — prices are never silently normalized with a missing rate.
"""

import logging
from decimal import ROUND_HALF_UP, Decimal

from django.core.cache import cache

from apps.currencies.enums import CurrencyCode
from apps.currencies.services.exceptions import ExchangeRateNotFoundError

logger = logging.getLogger(__name__)

# Cache key prefix and TTL for current exchange rates (5 minutes).
_RATE_CACHE_PREFIX = "exchange_rate:v1"
RATE_CACHE_TTL = 300  # seconds


class PriceNormalizer:
    """Compute EUR-normalized price from an amount and its currency.

    Example:
        >>> normalizer = PriceNormalizer()
        >>> normalizer.normalize_to_eur(Decimal("100"), CurrencyCode.BAM)
        Decimal('51.2000')
    """

    def __init__(self) -> None:
        self._rate_cache: dict[CurrencyCode, Decimal] = {}

    def normalize_to_eur(self, amount: Decimal, currency: CurrencyCode) -> Decimal:
        """Return ``amount`` converted to EUR using the current rate.

        Args:
            amount: The seller's original price amount.
            currency: The currency of ``amount``.

        Returns:
            The EUR-normalized amount rounded to 4 decimal places with
            ``ROUND_HALF_UP``. No rounding is applied to the stored value
            beyond this 4-decimal precision.

        Raises:
            ExchangeRateNotFoundError: If no ``is_current`` rate exists for
                ``currency`` (or the currency is unsupported).
        """
        rate = self._get_current_rate(currency)
        normalized = (Decimal(amount) * rate).quantize(
            Decimal("0.0001"),
            rounding=ROUND_HALF_UP,
        )
        return normalized

    def _get_current_rate(self, currency: CurrencyCode) -> Decimal:
        """Return the current rate for ``currency``, cached (5-min TTL).

        Uses a process-local dict in addition to the shared cache so repeated
        calls within a request avoid a DB hit. On a cache miss the rate is
        loaded from ``ExchangeRate`` and re-cached.

        Args:
            currency: The currency whose current rate is needed.

        Returns:
            The current ``rate_to_eur`` as a Decimal.

        Raises:
            ExchangeRateNotFoundError: If no current rate exists.
        """
        from apps.currencies.models import ExchangeRate

        if currency in self._rate_cache:
            return self._rate_cache[currency]

        cache_key = f"{_RATE_CACHE_PREFIX}:{currency.value}"
        cached = cache.get(cache_key)
        if cached is not None:
            self._rate_cache[currency] = Decimal(str(cached))
            return self._rate_cache[currency]

        rate_obj = ExchangeRate.objects.filter(
            currency=currency.value,
            is_current=True,
        ).first()
        if rate_obj is None:
            raise ExchangeRateNotFoundError(currency)

        rate = Decimal(str(rate_obj.rate_to_eur))
        self._rate_cache[currency] = rate
        cache.set(cache_key, str(rate), RATE_CACHE_TTL)
        return rate

    @staticmethod
    def invalidate_rate_cache(currency: CurrencyCode) -> None:
        """Invalidate the shared cached rate for ``currency`` after a change.

        Called by the admin/recompute path so the next normalization reads the
        updated current rate.

        Args:
            currency: The currency whose cached rate to invalidate.
        """
        cache.delete(f"{_RATE_CACHE_PREFIX}:{currency.value}")
        logger.info("Invalidated exchange rate cache for %s", currency.value)
