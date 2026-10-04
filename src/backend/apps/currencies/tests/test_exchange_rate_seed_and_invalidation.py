"""
Tests for the exchange-rate seed and the wired cache invalidation (09-API-008).

Three findings expressed as assertions:

1. The seed no longer reverts an operator's corrected rate. ``load_exchange_rates``
   is step 3 of ``migrate_locked._build_steps`` and runs on every boot; a
   ``get_or_create`` switch means an existing row is preserved, and the command's
   output says so.
2. The rate cache is genuinely invalidated through the production write path
   (the ``apps.currencies.signals`` ``post_save`` receiver), not by calling
   ``invalidate_rate_cache`` directly — a direct call proves nothing about the
   wiring.
3. A cache outage during invalidation does NOT roll back the saving transaction
   (the receiver's ``(ConnectionInterrupted, redis.RedisError)`` guard).
"""

from __future__ import annotations

from decimal import Decimal
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
import redis
from django.core.cache import cache
from django.core.management import call_command
from django_redis.exceptions import ConnectionInterrupted

from apps.currencies.enums import CurrencyCode
from apps.currencies.models import ExchangeRate
from apps.currencies.services.price_normalizer import (
    _RATE_CACHE_PREFIX,
    RATE_CACHE_TTL,
    PriceNormalizer,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture(autouse=True)
def _clear_rate_cache():
    """Clear the shared cache so rate lookups hit the DB in each test."""
    cache.clear()
    yield
    cache.clear()


def _rate_cache_key(currency: CurrencyCode) -> str:
    return f"{_RATE_CACHE_PREFIX}:{currency.value}"


class TestLoadExchangeRatesPreservesEditedRate:
    """Finding 1 — the seed never rewrites an existing row."""

    def test_seed_does_not_revert_operator_edit(self, exchange_rates) -> None:
        """An edited rate survives a second ``load_exchange_rates`` run.

        This is the finding, expressed as an assertion: the previous
        ``update_or_create`` reverted the edit with no log line and no record of
        the prior value.
        """
        ExchangeRate.objects.filter(currency=CurrencyCode.BAM.value).update(
            rate_to_eur=Decimal("0.600")
        )

        out = StringIO()
        call_command("load_exchange_rates", stdout=out)

        edited = ExchangeRate.objects.get(currency=CurrencyCode.BAM.value)
        assert edited.rate_to_eur == Decimal("0.600")
        output = out.getvalue()
        assert "preserved existing" in output
        assert "Rate BAM: rate_to_eur=0.60000000 (preserved existing)" in output
        assert "0 created, 3 preserved" in output

    def test_seed_creates_missing_rate_and_reports_seeded(self) -> None:
        """A missing currency is created and reported as seeded."""
        ExchangeRate.objects.all().delete()

        out = StringIO()
        call_command("load_exchange_rates", stdout=out)

        created = ExchangeRate.objects.get(currency=CurrencyCode.RSD.value)
        assert created.rate_to_eur == Decimal("0.0105")
        output = out.getvalue()
        assert "Rate RSD: rate_to_eur=0.0105 (seeded)" in output
        assert "Exchange rates loaded: 3 created, 0 preserved" in output


class TestRateCacheInvalidationWiring:
    """Finding 2 — the cache is invalidated through the production write path."""

    def test_updated_rate_is_visible_to_next_normalizer_read(
        self, exchange_rates
    ) -> None:
        """A rate changed via ``save()`` invalidates the cache for a new read.

        A long-lived ``PriceNormalizer`` is deliberately NOT held across the
        change: its instance-local ``_rate_cache`` would mask a missing
        shared-cache invalidation. A fresh instance must read the new rate from
        the shared cache (written by the first read) after the signal clears it.
        """
        first_read = PriceNormalizer().normalize_to_eur(
            Decimal("100"), CurrencyCode.BAM
        )
        assert first_read == Decimal("51.2000")
        assert cache.get(_rate_cache_key(CurrencyCode.BAM)) is not None

        rate = ExchangeRate.objects.get(currency=CurrencyCode.BAM.value)
        rate.rate_to_eur = Decimal("0.600")
        rate.save(update_fields=["rate_to_eur"])

        # The signal must have removed the warmed key.
        assert cache.get(_rate_cache_key(CurrencyCode.BAM)) is None

        second_read = PriceNormalizer().normalize_to_eur(
            Decimal("100"), CurrencyCode.BAM
        )
        assert second_read == Decimal("60.0000")

    def test_deleted_rate_invalidates_the_cache(self, exchange_rates) -> None:
        """A deleted rate also clears the cached value (``post_delete``)."""
        cache.set(_rate_cache_key(CurrencyCode.RSD), "0.0105", RATE_CACHE_TTL)

        ExchangeRate.objects.filter(currency=CurrencyCode.RSD.value).delete()

        assert cache.get(_rate_cache_key(CurrencyCode.RSD)) is None


class TestRateCacheOutageDoesNotRollBack:
    """Finding 3 — the receiver's guard keeps a cache outage from rolling back."""

    def test_cache_outage_during_invalidation_does_not_roll_back(
        self, exchange_rates
    ) -> None:
        """A Redis outage on ``cache.delete`` does not prevent the save.

        The receiver calls ``PriceNormalizer.invalidate_rate_cache`` inside a
        guarded ``try``; without the ``(ConnectionInterrupted, redis.RedisError)``
        guard the raise would propagate out of the signal and roll back the
        enclosing transaction, so the rate change would be lost.
        """
        bad_cache = MagicMock()
        bad_cache.delete.side_effect = ConnectionInterrupted(None)

        rate = ExchangeRate.objects.get(currency=CurrencyCode.BAM.value)
        rate.rate_to_eur = Decimal("0.700")

        with patch("apps.currencies.services.price_normalizer.cache", bad_cache):
            rate.save(update_fields=["rate_to_eur"])

        persisted = ExchangeRate.objects.get(currency=CurrencyCode.BAM.value)
        assert persisted.rate_to_eur == Decimal("0.700")

    def test_redis_error_during_invalidation_does_not_roll_back(
        self, exchange_rates
    ) -> None:
        """A bare ``redis.RedisError`` is guarded the same way."""
        bad_cache = MagicMock()
        bad_cache.delete.side_effect = redis.RedisError("redis down")

        rate = ExchangeRate.objects.get(currency=CurrencyCode.EUR.value)
        rate.rate_to_eur = Decimal("1.100")

        with patch("apps.currencies.services.price_normalizer.cache", bad_cache):
            rate.save(update_fields=["rate_to_eur"])

        persisted = ExchangeRate.objects.get(currency=CurrencyCode.EUR.value)
        assert persisted.rate_to_eur == Decimal("1.100")
