"""
Unit tests for SellerStats analytics service (TASK_041).

Tests cover time range filtering, cache hit/miss behavior, cache key generation,
empty data handling, and stats aggregation.

Requires a working PostgreSQL database per project spec.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.ads.models import Ad
from apps.analytics.models import AnalyticsEvent
from apps.analytics.services import SellerStats
from apps.analytics.services.seller_stats import CACHE_TTL
from apps.core.enums import AdStatus, AnalyticsEventType, TimeRange
from apps.users.models import User
from conftest import create_test_ad, make_user

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(
    ad: Ad,
    event_type: AnalyticsEventType,
    *,
    timestamp: timezone.datetime | None = None,
    user: User | None = None,
) -> AnalyticsEvent:
    """Create an AnalyticsEvent with sensible defaults."""
    return AnalyticsEvent.objects.create(
        event_type=event_type,
        ad=ad,
        user=user,
        timestamp=timestamp or timezone.now(),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def seller_with_ads(seller, category, city):
    """Create a seller with 2 published ads and a full event matrix.

    Data layout (mirrors the old setUpTestData):
    - ``seller`` — primary seller whose stats we query.
    - ad_a — 3 views (2 within 7d, 1 beyond 30d), 1 contact (within 7d)
    - ad_b — 3 views (1 within 7d, 1 within 30d, 1 beyond 30d), 1 contact (within 30d)
    - other_user — another seller (noise).
    - other_ad — ad of other seller with events (noise).
    - A non-ad event for seller (noise).

    Returns a dict with ``seller``, ``ad_a``, ``ad_b``, ``other_user``, ``other_ad``.
    """
    other_user = make_user(telegram_id=990001002)

    ad_a = create_test_ad(
        seller, category, city, title="Ad A", status=AdStatus.PUBLISHED
    )
    ad_b = create_test_ad(
        seller, category, city, title="Ad B", status=AdStatus.PUBLISHED
    )

    other_ad = create_test_ad(
        other_user, category, city, title="Other Ad", status=AdStatus.PUBLISHED
    )

    now = timezone.now()

    # Events for ad_a
    _make_event(ad_a, AnalyticsEventType.AD_VIEWED, timestamp=now - timedelta(days=1))
    _make_event(ad_a, AnalyticsEventType.AD_VIEWED, timestamp=now - timedelta(days=5))
    _make_event(ad_a, AnalyticsEventType.AD_VIEWED, timestamp=now - timedelta(days=60))
    _make_event(
        ad_a, AnalyticsEventType.CONTACT_INITIATED, timestamp=now - timedelta(days=2)
    )

    # Events for ad_b
    _make_event(ad_b, AnalyticsEventType.AD_VIEWED, timestamp=now - timedelta(days=3))
    _make_event(ad_b, AnalyticsEventType.AD_VIEWED, timestamp=now - timedelta(days=20))
    _make_event(ad_b, AnalyticsEventType.AD_VIEWED, timestamp=now - timedelta(days=90))
    _make_event(
        ad_b, AnalyticsEventType.CONTACT_INITIATED, timestamp=now - timedelta(days=15)
    )

    # Noise: other seller's events
    _make_event(
        other_ad, AnalyticsEventType.AD_VIEWED, timestamp=now - timedelta(hours=1)
    )
    _make_event(
        other_ad,
        AnalyticsEventType.CONTACT_INITIATED,
        timestamp=now - timedelta(hours=1),
    )

    # Noise: non-ad event for primary seller
    AnalyticsEvent.objects.create(
        event_type=AnalyticsEventType.DASHBOARD_VIEWED,
        user=seller,
        timestamp=now - timedelta(hours=1),
    )

    return {
        "seller": seller,
        "ad_a": ad_a,
        "ad_b": ad_b,
        "other_user": other_user,
        "other_ad": other_ad,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSellerStats:
    """Comprehensive tests for SellerStats service."""

    def test_get_stats_all_time(self, seller_with_ads) -> None:
        """ALL_TIME returns aggregated totals across all events."""
        seller = seller_with_ads["seller"]
        ad_a = seller_with_ads["ad_a"]
        ad_b = seller_with_ads["ad_b"]

        stats = SellerStats(user_id=seller.id).get_stats(TimeRange.ALL_TIME)

        # ad_a: 3 views, 1 contact; ad_b: 3 views, 1 contact → total 6 views, 2 contacts
        assert stats["total_views"] == 6
        assert stats["total_contacts"] == 2
        assert stats["ads_published"] == 2

        per_ad = {row["ad_id"]: row for row in stats["per_ad_stats"]}
        assert ad_a.id is not None
        assert ad_b.id is not None
        assert ad_a.id in per_ad
        assert ad_b.id in per_ad
        assert per_ad[ad_a.id]["views"] == 3
        assert per_ad[ad_a.id]["contacts"] == 1
        assert per_ad[ad_b.id]["views"] == 3
        assert per_ad[ad_b.id]["contacts"] == 1

    def test_get_stats_with_time_range_7_days(self, seller_with_ads) -> None:
        """SEVEN_DAYS filters events within the last 7 days only."""
        seller = seller_with_ads["seller"]

        stats = SellerStats(user_id=seller.id).get_stats(TimeRange.SEVEN_DAYS)

        # ad_a: 2 views (day 1, day 5), 1 contact (day 2) = 2 views, 1 contact
        # ad_b: 1 view (day 3), 0 contacts = 1 view, 0 contacts
        assert stats["total_views"] == 3
        assert stats["total_contacts"] == 1
        assert stats["ads_published"] == 2

    def test_get_stats_with_time_range_30_days(self, seller_with_ads) -> None:
        """THIRTY_DAYS filters events within the last 30 days only."""
        seller = seller_with_ads["seller"]

        stats = SellerStats(user_id=seller.id).get_stats(TimeRange.THIRTY_DAYS)

        # ad_a: 2 views (day 1, day 5), 1 contact (day 2) = 2 views, 1 contact
        # ad_b: 2 views (day 3, day 20), 1 contact (day 15) = 2 views, 1 contact
        assert stats["total_views"] == 4
        assert stats["total_contacts"] == 2
        assert stats["ads_published"] == 2

    def test_cache_key_format(self) -> None:
        """Cache key follows ``seller_stats:<user_id>:<range_value>``."""
        svc = SellerStats(user_id=42)
        assert svc._cache_key(TimeRange.ALL_TIME) == "seller_stats:42:all_time"
        assert svc._cache_key(TimeRange.THIRTY_DAYS) == "seller_stats:42:30_days"
        assert svc._cache_key(TimeRange.SEVEN_DAYS) == "seller_stats:42:7_days"

    def test_empty_data_handling(self, seller, category, city) -> None:
        """Seller with no analytics events returns zeroed stats."""
        empty_user = make_user(telegram_id=990001003)
        # One ad but zero events
        create_test_ad(
            empty_user, category, city, title="Lonely Ad", status=AdStatus.PUBLISHED
        )

        stats = SellerStats(user_id=empty_user.id).get_stats(TimeRange.ALL_TIME)

        assert stats["total_views"] == 0
        assert stats["total_contacts"] == 0
        assert stats["ads_published"] == 1
        assert len(stats["per_ad_stats"]) == 1
        assert stats["per_ad_stats"][0]["views"] == 0
        assert stats["per_ad_stats"][0]["contacts"] == 0


# ---------------------------------------------------------------------------
# Tests: caching behavior (cache hit / miss, TTL)
# ---------------------------------------------------------------------------


class TestSellerStatsCache:
    """Cache hit/miss behavior for ``SellerStats`` (5-minute TTL)."""

    def test_cache_ttl_is_300(self) -> None:
        """``CACHE_TTL`` constant equals 300 seconds (5 minutes)."""
        assert CACHE_TTL == 300

    def test_cache_miss_invokes_compute(self, seller_with_ads) -> None:
        """First call (cache miss) invokes ``_compute`` exactly once."""
        seller = seller_with_ads["seller"]
        svc = SellerStats(user_id=seller.id)
        with patch.object(SellerStats, "_compute", wraps=svc._compute) as spy:
            result = svc.get_stats(TimeRange.ALL_TIME)
            assert spy.call_count == 1
        assert result["total_views"] == 6

    def test_cache_hit_returns_cached_without_compute(self, seller_with_ads) -> None:
        """Second call returns cached result without invoking ``_compute``."""
        seller = seller_with_ads["seller"]
        svc = SellerStats(user_id=seller.id)
        # Prime the cache (cache miss → _compute invoked)
        first = svc.get_stats(TimeRange.ALL_TIME)
        # Second call must hit the cache
        with patch.object(SellerStats, "_compute") as mock_compute:
            second = svc.get_stats(TimeRange.ALL_TIME)
            assert mock_compute.call_count == 0
        assert second == first

    def test_result_stored_in_cache_after_first_call(self, seller_with_ads) -> None:
        """After the first call, the result is stored under the expected key."""
        from django.core.cache import cache

        seller = seller_with_ads["seller"]
        svc = SellerStats(user_id=seller.id)
        svc.get_stats(TimeRange.ALL_TIME)
        cached = cache.get(f"seller_stats:{seller.id}:all_time")
        assert cached is not None
        assert cached["total_views"] == 6
