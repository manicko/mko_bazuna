"""
Unit tests for SellerStats analytics service (TASK_041).

Tests cover time range filtering, cache key generation, empty data handling,
and stats aggregation.

Requires a working PostgreSQL database per project spec.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.ads.models import Ad
from apps.analytics.models import AnalyticsEvent
from apps.analytics.services import SellerStats
from apps.core.enums import AdStatus, AnalyticsEventType, TimeRange
from apps.users.models import User

from conftest import create_test_ad

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


def _make_user(telegram_id: int = 990000001, **overrides: object) -> User:
    """Create a User with sensible defaults for analytics tests."""
    defaults: dict = {
        "telegram_id": telegram_id,
        "chat_id": telegram_id,
        "username": None,
        "password": "x",
    }
    defaults.update(overrides)
    return User.objects.create(**defaults)


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
    other_user = _make_user(telegram_id=990001002)

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
    _make_event(other_ad, AnalyticsEventType.AD_VIEWED, timestamp=now - timedelta(hours=1))
    _make_event(
        other_ad, AnalyticsEventType.CONTACT_INITIATED, timestamp=now - timedelta(hours=1)
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
        empty_user = _make_user(telegram_id=990001003)
        # One ad but zero events
        create_test_ad(empty_user, category, city, title="Lonely Ad", status=AdStatus.PUBLISHED)

        stats = SellerStats(user_id=empty_user.id).get_stats(TimeRange.ALL_TIME)

        assert stats["total_views"] == 0
        assert stats["total_contacts"] == 0
        assert stats["ads_published"] == 1
        assert len(stats["per_ad_stats"]) == 1
        assert stats["per_ad_stats"][0]["views"] == 0
        assert stats["per_ad_stats"][0]["contacts"] == 0
