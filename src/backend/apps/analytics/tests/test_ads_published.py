"""
Tests for ads_published metric in SellerStats.

Verifies that ads_published counts only PUBLISHED ads, not drafts,
rejected, or other non-published statuses. This tests the fix for F4
(ads_published misleadingly counted all ads regardless of status).
"""

from __future__ import annotations

import pytest
from django.test import override_settings

from apps.analytics.services import SellerStats
from apps.core.enums import AdStatus

from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]

# Use locmem cache so SellerStats cache tests are deterministic and isolated.


@pytest.fixture(autouse=True)
def _locmem_cache():
    """Use in-process locmem cache for deterministic SellerStats behavior."""
    with override_settings(
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            },
        },
    ):
        yield


@pytest.fixture
def seller_ads(seller, category, city):
    """Create 3 published + 2 draft + 1 rejected ads for the seller."""
    for i in range(3):
        create_test_ad(
            seller, category, city, title=f"Published {i}", status=AdStatus.PUBLISHED
        )
    create_test_ad(seller, category, city, title="Draft Ad", status=AdStatus.DRAFT)
    create_test_ad(seller, category, city, title="Another Draft", status=AdStatus.DRAFT)
    create_test_ad(seller, category, city, title="Rejected Ad", status=AdStatus.REJECTED)


class TestAdsPublishedMetric:
    """Tests for the ads_published metric in SellerStats."""

    def test_ads_published_counts_only_published(self, seller_ads, seller: object) -> None:
        """ads_published should count only PUBLISHED ads, not drafts or rejected."""
        stats = SellerStats(user_id=seller.id).get_stats()
        assert stats["ads_published"] == 3

    def test_ads_published_with_zero_published(self, seller, category, city) -> None:
        """Seller with only non-published ads gets 0 ads_published."""
        create_test_ad(
            seller, category, city, title="Only Draft", status=AdStatus.DRAFT
        )
        stats = SellerStats(user_id=seller.id).get_stats()
        assert stats["ads_published"] == 0

    def test_per_ad_stats_includes_all_ads(self, seller_ads, seller: object) -> None:
        """Per-ad stats should include all user ads regardless of status."""
        stats = SellerStats(user_id=seller.id).get_stats()
        # 3 published + 2 drafts + 1 rejected = 6 total ads
        assert len(stats["per_ad_stats"]) == 6
