"""
Unit tests for SellerStats analytics service (TASK_041).

Tests cover time range filtering, cache key generation, empty data handling,
and stats aggregation. Uses ``django.test.TestCase`` for DB-backed assertions.

Requires a working PostgreSQL database per project spec.
"""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.ads.models import Ad
from apps.analytics.models import AnalyticsEvent
from apps.analytics.services import SellerStats
from apps.categories.models import Category
from apps.core.enums import AdSource, AdStatus, AnalyticsEventType, TimeRange
from apps.locations.models import City
from apps.users.models import User

# ---------------------------------------------------------------------------
# Test helpers
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
    return User.objects.create(**defaults)  # type: ignore[arg-type]


def _make_category(slug: str = "test-cat") -> Category:
    """Create a Category with sensible defaults."""
    return Category.objects.create(
        name="Test Category",
        slug=slug,
    )


def _make_city(slug: str = "test-city") -> City:
    """Create a City with sensible defaults."""
    return City.objects.create(
        country_code="ME",
        name="Test City",
        region="Test Region",
        slug=slug,
    )


def _make_ad(
    user: User,
    category: Category,
    city: City,
    *,
    title: str = "Test Ad",
    status: AdStatus = AdStatus.PUBLISHED,
    **overrides: object,
) -> Ad:
    """Create an Ad with sensible defaults for analytics tests."""
    defaults: dict = {
        "user": user,
        "title": title,
        "description": "Test description",
        "category": category,
        "city": city,
        "category_name": category.name,
        "status": status,
        "source": AdSource.TELEGRAM,
    }
    defaults.update(overrides)
    return Ad.objects.create(**defaults)  # type: ignore[arg-type]


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
# Tests
# ---------------------------------------------------------------------------


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        },
    },
)
class TestSellerStats(TestCase):
    """Comprehensive tests for SellerStats service."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Create shared fixtures for all test methods.

        Data layout:
        - ``cls.user`` — seller whose stats we query.
        - 2 published ads (ad_a, ad_b), each with a mix of view/contact
          events spread across time buckets for time-range filtering.
        - ``cls.other_user`` — another seller (noise, should not appear).
        - ``cls.other_ad`` — ad of the other seller (noise).
        """
        # --- Taxonomy ---
        cls.category = _make_category("seller-stats-cat")
        cls.city = _make_city("seller-stats-city")

        # --- Sellers ---
        cls.user = _make_user(telegram_id=990001001)
        cls.other_user = _make_user(telegram_id=990001002)

        # --- Ads for primary seller ---
        cls.ad_a = _make_ad(
            cls.user,
            cls.category,
            cls.city,
            title="Ad A",
            status=AdStatus.PUBLISHED,
        )
        cls.ad_b = _make_ad(
            cls.user,
            cls.category,
            cls.city,
            title="Ad B",
            status=AdStatus.PUBLISHED,
        )

        # --- Ad for other seller (noise) ---
        cls.other_ad = _make_ad(
            cls.other_user,
            cls.category,
            cls.city,
            title="Other Ad",
            status=AdStatus.PUBLISHED,
        )

        now = timezone.now()

        # --- Events for ad_a ---
        #    views: 2 recent (within 7d), 1 old (beyond 30d)
        _make_event(cls.ad_a, AnalyticsEventType.AD_VIEWED, timestamp=now - timedelta(days=1))
        _make_event(cls.ad_a, AnalyticsEventType.AD_VIEWED, timestamp=now - timedelta(days=5))
        _make_event(cls.ad_a, AnalyticsEventType.AD_VIEWED, timestamp=now - timedelta(days=60))
        #    contacts: 1 recent (within 7d)
        _make_event(
            cls.ad_a,
            AnalyticsEventType.CONTACT_INITIATED,
            timestamp=now - timedelta(days=2),
        )

        # --- Events for ad_b ---
        #    views: 1 recent (within 7d), 1 mid (within 30d), 1 old (beyond 30d)
        _make_event(cls.ad_b, AnalyticsEventType.AD_VIEWED, timestamp=now - timedelta(days=3))
        _make_event(cls.ad_b, AnalyticsEventType.AD_VIEWED, timestamp=now - timedelta(days=20))
        _make_event(cls.ad_b, AnalyticsEventType.AD_VIEWED, timestamp=now - timedelta(days=90))
        #    contacts: 1 mid (within 30d)
        _make_event(
            cls.ad_b,
            AnalyticsEventType.CONTACT_INITIATED,
            timestamp=now - timedelta(days=15),
        )

        # --- Noise: other seller's events (should never be counted) ---
        _make_event(cls.other_ad, AnalyticsEventType.AD_VIEWED, timestamp=now - timedelta(hours=1))
        _make_event(
            cls.other_ad,
            AnalyticsEventType.CONTACT_INITIATED,
            timestamp=now - timedelta(hours=1),
        )

        # --- Non-ad events for primary seller (should never be counted) ---
        AnalyticsEvent.objects.create(
            event_type=AnalyticsEventType.DASHBOARD_VIEWED,
            user=cls.user,
            timestamp=now - timedelta(hours=1),
        )

    # ── helpers ────────────────────────────────────────────────────────

    def _stats(self, time_range: TimeRange = TimeRange.ALL_TIME) -> dict:
        """Convenience: return SellerStats.get_stats() for ``self.user``."""
        return SellerStats(user_id=self.user.id).get_stats(time_range)

    # ── test_get_stats_all_time ────────────────────────────────────────

    def test_get_stats_all_time(self) -> None:
        """ALL_TIME returns aggregated totals across all events."""
        stats = self._stats(TimeRange.ALL_TIME)

        # ad_a: 3 views, 1 contact; ad_b: 3 views, 1 contact → total 6 views, 2 contacts
        self.assertEqual(stats["total_views"], 6)
        self.assertEqual(stats["total_contacts"], 2)
        self.assertEqual(stats["ads_published"], 2)

        per_ad = {row["ad_id"]: row for row in stats["per_ad_stats"]}
        assert self.ad_a.id is not None
        assert self.ad_b.id is not None
        self.assertIn(self.ad_a.id, per_ad)
        self.assertIn(self.ad_b.id, per_ad)
        self.assertEqual(per_ad[self.ad_a.id]["views"], 3)
        self.assertEqual(per_ad[self.ad_a.id]["contacts"], 1)
        self.assertEqual(per_ad[self.ad_b.id]["views"], 3)
        self.assertEqual(per_ad[self.ad_b.id]["contacts"], 1)

    # ── test_get_stats_with_time_range ─────────────────────────────────

    def test_get_stats_with_time_range_7_days(self) -> None:
        """SEVEN_DAYS filters events within the last 7 days only."""
        stats = self._stats(TimeRange.SEVEN_DAYS)

        # ad_a: 2 views (day 1, day 5), 1 contact (day 2) = 2 views, 1 contact
        # ad_b: 1 view (day 3), 0 contacts = 1 view, 0 contacts
        self.assertEqual(stats["total_views"], 3)
        self.assertEqual(stats["total_contacts"], 1)
        self.assertEqual(stats["ads_published"], 2)

    def test_get_stats_with_time_range_30_days(self) -> None:
        """THIRTY_DAYS filters events within the last 30 days only."""
        stats = self._stats(TimeRange.THIRTY_DAYS)

        # ad_a: 2 views (day 1, day 5), 1 contact (day 2) = 2 views, 1 contact
        # ad_b: 2 views (day 3, day 20), 1 contact (day 15) = 2 views, 1 contact
        self.assertEqual(stats["total_views"], 4)
        self.assertEqual(stats["total_contacts"], 2)
        self.assertEqual(stats["ads_published"], 2)

    # ── test_cache_key_format ──────────────────────────────────────────

    def test_cache_key_format(self) -> None:
        """Cache key follows ``seller_stats:<user_id>:<range_value>``."""
        svc = SellerStats(user_id=42)
        self.assertEqual(
            svc._cache_key(TimeRange.ALL_TIME),
            "seller_stats:42:all_time",
        )
        self.assertEqual(
            svc._cache_key(TimeRange.THIRTY_DAYS),
            "seller_stats:42:30_days",
        )
        self.assertEqual(
            svc._cache_key(TimeRange.SEVEN_DAYS),
            "seller_stats:42:7_days",
        )

    # ── test_empty_data_handling ───────────────────────────────────────

    def test_empty_data_handling(self) -> None:
        """Seller with no analytics events returns zeroed stats."""
        empty_user = _make_user(telegram_id=990001003)
        # One ad but zero events
        _make_ad(
            empty_user,
            self.category,
            self.city,
            title="Lonely Ad",
            status=AdStatus.PUBLISHED,
        )

        stats = SellerStats(user_id=empty_user.id).get_stats(TimeRange.ALL_TIME)

        self.assertEqual(stats["total_views"], 0)
        self.assertEqual(stats["total_contacts"], 0)
        self.assertEqual(stats["ads_published"], 1)
        self.assertEqual(len(stats["per_ad_stats"]), 1)
        self.assertEqual(stats["per_ad_stats"][0]["views"], 0)
        self.assertEqual(stats["per_ad_stats"][0]["contacts"], 0)