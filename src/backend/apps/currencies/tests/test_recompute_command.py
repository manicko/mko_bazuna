"""
Tests for the ``recompute_normalized_prices`` management command (spec Task 11).
"""

from decimal import Decimal

import pytest
from django.core.management import call_command

from conftest import create_test_ad
from apps.core.enums import AdStatus
from apps.currencies.enums import CurrencyCode

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture(autouse=True)
def _clear_rate_cache():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


class TestRecomputeNormalizedPrices:
    def test_recompute_corrects_stale_normalized_value(
        self, exchange_rates, seller, category, city
    ) -> None:
        """A stale EUR-normalized value is recomputed from the current rate.

        The ad is BAM with amount 100 (100 * 0.512 = 51.20 EUR); the stored
        normalized value (999) is stale and must be corrected.
        """
        ad = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.PUBLISHED,
            price=100,
            price_currency=CurrencyCode.BAM,
            price_normalized_eur=999,
        )

        call_command("recompute_normalized_prices")

        ad.refresh_from_db()
        assert ad.price_normalized_eur == Decimal("51.2000")

    def test_dry_run_does_not_write(self, exchange_rates, seller, category, city) -> None:
        """``--dry-run`` reports without persisting any change."""
        ad = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.PUBLISHED,
            price=100,
            price_currency=CurrencyCode.BAM,
            price_normalized_eur=999,
        )

        call_command("recompute_normalized_prices", dry_run=True)

        ad.refresh_from_db()
        assert ad.price_normalized_eur == Decimal("999")

    def test_draft_ads_are_skipped(self, exchange_rates, seller, category, city) -> None:
        """Draft ads (pre-submission) are excluded from recompute."""
        ad = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.DRAFT,
            price=100,
            price_currency=CurrencyCode.BAM,
            price_normalized_eur=999,
        )

        call_command("recompute_normalized_prices")

        ad.refresh_from_db()
        assert ad.price_normalized_eur == Decimal("999")
