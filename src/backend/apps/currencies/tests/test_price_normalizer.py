"""
Tests for the PriceNormalizer service (spec Task 3).
"""

from decimal import Decimal

import pytest

from apps.currencies.enums import CurrencyCode
from apps.currencies.models import ExchangeRate
from apps.currencies.services.exceptions import ExchangeRateNotFoundError
from apps.currencies.services.price_normalizer import (
    PriceNormalizer,
    normalize_price_to_eur,
)
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture(autouse=True)
def _clear_rate_cache():
    """Clear the shared cache so rate lookups hit the DB in each test."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


class TestPriceNormalizer:
    def test_eur_preserves_amount(self, exchange_rates) -> None:
        """EUR is the base currency (rate 1.0), so the amount is preserved."""
        result = PriceNormalizer().normalize_to_eur(Decimal("100"), CurrencyCode.EUR)
        assert result == Decimal("100.0000")

    def test_bam_normalized_by_seeded_rate(self, exchange_rates) -> None:
        """BAM uses the seeded rate (100 BAM = 51.20 EUR)."""
        result = PriceNormalizer().normalize_to_eur(Decimal("100"), CurrencyCode.BAM)
        assert result == Decimal("51.2000")

    def test_rsd_normalized_by_seeded_rate(self, exchange_rates) -> None:
        """RSD uses the seeded rate (1000 RSD = 10.50 EUR)."""
        result = PriceNormalizer().normalize_to_eur(Decimal("1000"), CurrencyCode.RSD)
        assert result == Decimal("10.5000")

    def test_missing_rate_raises_domain_error(self, exchange_rates) -> None:
        """A currency without a current rate raises, never silently normalizes."""
        ExchangeRate.objects.filter(currency=CurrencyCode.EUR.value).update(
            is_current=False
        )
        with pytest.raises(ExchangeRateNotFoundError):
            PriceNormalizer().normalize_to_eur(Decimal("10"), CurrencyCode.EUR)


class TestNormalizePriceToEur:
    def test_sets_eur_value_when_currency_present(
        self, exchange_rates, seller, category, city
    ) -> None:
        """A present currency with a valid rate sets the normalized EUR value."""
        ad = create_test_ad(
            seller, category, city, price=100, price_currency=CurrencyCode.BAM
        )
        normalize_price_to_eur(ad, Decimal("100"), CurrencyCode.BAM)
        assert ad.price_normalized_eur == Decimal("51.2000")

    def test_clears_value_on_normalization_error(
        self, exchange_rates, seller, category, city
    ) -> None:
        """A failed normalization (no current rate) yields None, not a raise.

        ``PriceNormalizer.normalize_to_eur`` raises ``ExchangeRateNotFoundError``
        when no current rate exists; the broad ``except Exception`` in
        ``normalize_price_to_eur`` must swallow it and clear the value.
        """
        ad = create_test_ad(
            seller, category, city, price=100, price_currency=CurrencyCode.EUR
        )
        ExchangeRate.objects.filter(currency=CurrencyCode.EUR.value).update(
            is_current=False
        )
        normalize_price_to_eur(ad, Decimal("100"), CurrencyCode.EUR)
        assert ad.price_normalized_eur is None

    def test_clears_value_when_currency_none(
        self, exchange_rates, seller, category, city
    ) -> None:
        """A missing currency clears the normalized value."""
        ad = create_test_ad(
            seller, category, city, price=100, price_currency=CurrencyCode.EUR
        )
        normalize_price_to_eur(ad, Decimal("100"), None)
        assert ad.price_normalized_eur is None
