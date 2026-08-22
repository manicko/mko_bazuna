"""
Tests for the PriceNormalizer service (spec Task 3).
"""

from decimal import Decimal

import pytest

from apps.currencies.enums import CurrencyCode
from apps.currencies.models import ExchangeRate
from apps.currencies.services.exceptions import ExchangeRateNotFoundError
from apps.currencies.services.price_normalizer import PriceNormalizer

pytestmark = [pytest.mark.django_db]


@pytest.fixture(autouse=True)
def _clear_rate_cache():
    """Clear the shared cache so rate lookups hit the DB in each test."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


class TestPriceNormalizer:
    def test_eur_preserves_amount(self) -> None:
        """EUR is the base currency (rate 1.0), so the amount is preserved."""
        result = PriceNormalizer().normalize_to_eur(Decimal("100"), CurrencyCode.EUR)
        assert result == Decimal("100.0000")

    def test_bam_normalized_by_seeded_rate(self) -> None:
        """BAM uses the seeded rate (100 BAM = 51.20 EUR)."""
        result = PriceNormalizer().normalize_to_eur(Decimal("100"), CurrencyCode.BAM)
        assert result == Decimal("51.2000")

    def test_rsd_normalized_by_seeded_rate(self) -> None:
        """RSD uses the seeded rate (1000 RSD = 10.50 EUR)."""
        result = PriceNormalizer().normalize_to_eur(Decimal("1000"), CurrencyCode.RSD)
        assert result == Decimal("10.5000")

    def test_missing_rate_raises_domain_error(self) -> None:
        """A currency without a current rate raises, never silently normalizes."""
        ExchangeRate.objects.filter(currency=CurrencyCode.EUR.value).update(
            is_current=False
        )
        with pytest.raises(ExchangeRateNotFoundError):
            PriceNormalizer().normalize_to_eur(Decimal("10"), CurrencyCode.EUR)
