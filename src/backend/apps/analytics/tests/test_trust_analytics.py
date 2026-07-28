"""
Unit tests for TrustAnalytics service (TASK_057).

Tests cover trust score calculation, trust level mapping, trust event recording,
and daily metrics query. Uses ``django.test.TestCase`` for DB-backed assertions.
"""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.ads.models import Ad
from apps.analytics.models import AnalyticsEvent, DailyAdMetrics
from apps.analytics.services.trust_analytics import (
    calculate_seller_trust_score,
    get_seller_daily_metrics,
    get_trust_level,
    record_trust_event,
)
from apps.categories.models import Category
from apps.core.enums import AdSource, AdStatus, AnalyticsEventType, TrustLevel
from apps.locations.models import City
from apps.trust.models import SellerVerification
from apps.users.models import User

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_user(telegram_id: int = 990010001, **overrides: object) -> User:
    """Create a User with sensible defaults for trust analytics tests."""
    defaults: dict = {
        "telegram_id": telegram_id,
        "chat_id": telegram_id,
        "username": None,
        "password": "x",
    }
    defaults.update(overrides)
    return User.objects.create(**defaults)  # type: ignore[arg-type]


def _make_category(slug: str = "trust-cat") -> Category:
    """Create a Category with sensible defaults."""
    return Category.objects.create(
        name="Trust Category",
        slug=slug,
    )


def _make_city(slug: str = "trust-city") -> City:
    """Create a City with sensible defaults."""
    return City.objects.create(
        country_code="ME",
        name="Trust City",
        region="Trust Region",
        slug=slug,
    )


def _make_ad(
    user: User,
    category: Category,
    city: City,
    *,
    title: str = "Trust Ad",
    status: AdStatus = AdStatus.PUBLISHED,
    **overrides: object,
) -> Ad:
    """Create an Ad with sensible defaults for trust analytics tests."""
    defaults: dict = {
        "user": user,
        "title": title,
        "description": "Trust analytics test description",
        "category": category,
        "city": city,
        "category_name": category.name,
        "status": status,
        "source": AdSource.TELEGRAM,
    }
    defaults.update(overrides)
    return Ad.objects.create(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tests: calculate_seller_trust_score
# ---------------------------------------------------------------------------


class TestCalculateSellerTrustScore(TestCase):
    """Tests for the trust score calculation algorithm."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.category = _make_category()
        cls.city = _make_city()

    def test_base_score_no_ads_no_verification(self) -> None:
        """A seller with no ads and no verification gets the base score of 50."""
        user = _make_user(telegram_id=990010101)
        score = calculate_seller_trust_score(user.id)
        self.assertAlmostEqual(score, 50.0)

    def test_published_ads_increase_score(self) -> None:
        """Each published ad adds +10, up to a maximum of +50 (5 ads)."""
        user = _make_user(telegram_id=990010102)

        # 2 published ads → +20
        for i in range(2):
            _make_ad(user, self.category, self.city, title=f"Pub Ad {i}")
        score = calculate_seller_trust_score(user.id)
        self.assertAlmostEqual(score, 70.0)

    def test_published_ads_capped_at_five(self) -> None:
        """More than 5 published ads still caps the bonus at +50."""
        user = _make_user(telegram_id=990010103)

        # 10 published ads → bonus capped at +50
        for i in range(10):
            _make_ad(user, self.category, self.city, title=f"Pub Ad {i}")
        score = calculate_seller_trust_score(user.id)
        self.assertAlmostEqual(score, 100.0)

    def test_admin_verification_adds_bonus(self) -> None:
        """Admin-verified seller gets +20."""
        user = _make_user(telegram_id=990010104)
        SellerVerification.objects.create(user=user, verified_by_admin=True)

        score = calculate_seller_trust_score(user.id)
        self.assertAlmostEqual(score, 70.0)

    def test_admin_verification_no_bonus_when_not_verified(self) -> None:
        """SellerVerification exists but verified_by_admin is False → no bonus."""
        user = _make_user(telegram_id=990010105)
        SellerVerification.objects.create(user=user, verified_by_admin=False)

        score = calculate_seller_trust_score(user.id)
        self.assertAlmostEqual(score, 50.0)

    def test_rejected_ads_reduce_score(self) -> None:
        """Each rejected ad subtracts 10, floored at 0."""
        user = _make_user(telegram_id=990010106)

        # 6 rejected ads → -60, floor at 0 (base 50 - 60 = -10 → 0)
        for i in range(6):
            _make_ad(
                user, self.category, self.city,
                title=f"Rej Ad {i}",
                status=AdStatus.REJECTED,
            )
        score = calculate_seller_trust_score(user.id)
        self.assertAlmostEqual(score, 0.0)

    def test_combined_published_rejected_and_verified(self) -> None:
        """Mix of published (+30), verified (+20), and rejected (-20)."""
        user = _make_user(telegram_id=990010107)

        # 3 published ads → +30
        for i in range(3):
            _make_ad(user, self.category, self.city, title=f"Pub {i}")

        # 2 rejected ads → -20
        for i in range(2):
            _make_ad(
                user, self.category, self.city,
                title=f"Rej {i}",
                status=AdStatus.REJECTED,
            )

        # Admin verified → +20
        SellerVerification.objects.create(user=user, verified_by_admin=True)

        # Score: 50 + 30 + 20 - 20 = 80
        score = calculate_seller_trust_score(user.id)
        self.assertAlmostEqual(score, 80.0)

    def test_score_clamped_at_100(self) -> None:
        """Score cannot exceed 100 even with high bonuses."""
        user = _make_user(telegram_id=990010108)

        # 5 published → +50
        for i in range(5):
            _make_ad(user, self.category, self.city, title=f"Pub {i}")

        # Verified → +20
        SellerVerification.objects.create(user=user, verified_by_admin=True)

        # Net: 50 + 50 + 20 = 120 → clamped to 100
        score = calculate_seller_trust_score(user.id)
        self.assertAlmostEqual(score, 100.0)

    def test_score_not_below_zero(self) -> None:
        """Score cannot go below 0 even with many rejections."""
        user = _make_user(telegram_id=990010109)

        # Many rejected ads
        for i in range(20):
            _make_ad(
                user, self.category, self.city,
                title=f"Rej {i}",
                status=AdStatus.REJECTED,
            )

        score = calculate_seller_trust_score(user.id)
        self.assertAlmostEqual(score, 0.0)

    def test_other_users_ads_do_not_affect_score(self) -> None:
        """Only the given user's ads are counted."""
        user = _make_user(telegram_id=990010110)
        other = _make_user(telegram_id=990010111)

        # Other user has many published ads
        for i in range(5):
            _make_ad(other, self.category, self.city, title=f"Other {i}")

        # Primary user has nothing → base 50
        score = calculate_seller_trust_score(user.id)
        self.assertAlmostEqual(score, 50.0)

    def test_seller_verification_does_not_exist_returns_base(self) -> None:
        """Missing SellerVerification row is handled gracefully."""
        user = _make_user(telegram_id=990010112)
        # No SellerVerification created
        score = calculate_seller_trust_score(user.id)
        self.assertAlmostEqual(score, 50.0)


# ---------------------------------------------------------------------------
# Tests: get_trust_level
# ---------------------------------------------------------------------------


class TestGetTrustLevel(TestCase):
    """Tests for mapping numeric trust scores to TrustLevel enum."""

    def test_unverified_at_zero(self) -> None:
        """Score 0 maps to UNVERIFIED."""
        assert get_trust_level(0) == TrustLevel.UNVERIFIED

    def test_unverified_up_to_30(self) -> None:
        """Score 30 maps to UNVERIFIED (upper boundary)."""
        assert get_trust_level(30) == TrustLevel.UNVERIFIED

    def test_verified_starts_at_31(self) -> None:
        """Score 31 maps to VERIFIED (lower boundary)."""
        assert get_trust_level(31) == TrustLevel.VERIFIED

    def test_verified_up_to_60(self) -> None:
        """Score 60 maps to VERIFIED (upper boundary)."""
        assert get_trust_level(60) == TrustLevel.VERIFIED

    def test_trusted_starts_at_61(self) -> None:
        """Score 61 maps to TRUSTED (lower boundary)."""
        assert get_trust_level(61) == TrustLevel.TRUSTED

    def test_trusted_up_to_85(self) -> None:
        """Score 85 maps to TRUSTED (upper boundary)."""
        assert get_trust_level(85) == TrustLevel.TRUSTED

    def test_pro_starts_at_86(self) -> None:
        """Score 86 maps to PRO (lower boundary)."""
        assert get_trust_level(86) == TrustLevel.PRO

    def test_pro_at_100(self) -> None:
        """Score 100 maps to PRO."""
        assert get_trust_level(100) == TrustLevel.PRO

    def test_mid_range_verified(self) -> None:
        """Score 45 maps to VERIFIED (mid-range)."""
        assert get_trust_level(45) == TrustLevel.VERIFIED

    def test_mid_range_trusted(self) -> None:
        """Score 73 maps to TRUSTED (mid-range)."""
        assert get_trust_level(73) == TrustLevel.TRUSTED


# ---------------------------------------------------------------------------
# Tests: record_trust_event
# ---------------------------------------------------------------------------


class TestRecordTrustEvent(TestCase):
    """Tests for recording trust-related analytics events."""

    def test_creates_analytics_event(self) -> None:
        """record_trust_event creates an AnalyticsEvent with correct data."""
        user = _make_user(telegram_id=990010201)
        record_trust_event(user.id, AnalyticsEventType.SELLER_VERIFIED)

        events = AnalyticsEvent.objects.filter(user_id=user.id)
        self.assertEqual(events.count(), 1)
        event = events.first()
        assert event is not None
        self.assertEqual(event.event_type, AnalyticsEventType.SELLER_VERIFIED.value)

    def test_creates_event_without_ad(self) -> None:
        """Trust events are created without an associated ad."""
        user = _make_user(telegram_id=990010202)
        record_trust_event(user.id, AnalyticsEventType.TRUST_LEVEL_UPDATED)

        event = AnalyticsEvent.objects.get(user_id=user.id)
        self.assertIsNone(event.ad)

    def test_creates_multiple_events_independently(self) -> None:
        """Multiple calls create separate events."""
        user = _make_user(telegram_id=990010203)
        record_trust_event(user.id, AnalyticsEventType.SELLER_VERIFIED)
        record_trust_event(user.id, AnalyticsEventType.TRUST_LEVEL_UPDATED)

        events = AnalyticsEvent.objects.filter(user_id=user.id).order_by("timestamp")
        self.assertEqual(events.count(), 2)
        assert events[0] is not None
        assert events[1] is not None
        self.assertEqual(
            events[0].event_type,
            AnalyticsEventType.SELLER_VERIFIED.value,
        )
        self.assertEqual(
            events[1].event_type,
            AnalyticsEventType.TRUST_LEVEL_UPDATED.value,
        )


# ---------------------------------------------------------------------------
# Tests: get_seller_daily_metrics
# ---------------------------------------------------------------------------


class TestGetSellerDailyMetrics(TestCase):
    """Tests for querying daily aggregated ad metrics."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.category = _make_category("metrics-cat")
        cls.city = _make_city("metrics-city")

        cls.user = _make_user(telegram_id=990010301)
        cls.other = _make_user(telegram_id=990010302)

        cls.ad = _make_ad(
            cls.user,
            cls.category,
            cls.city,
            title="Metrics Ad",
            status=AdStatus.PUBLISHED,
        )
        cls.other_ad = _make_ad(
            cls.other,
            cls.category,
            cls.city,
            title="Other Metrics Ad",
            status=AdStatus.PUBLISHED,
        )

        today = timezone.now().date()

        # Daily metrics for the primary seller's ad on 3 different dates
        cls.metrics_day1 = DailyAdMetrics.objects.create(
            ad=cls.ad,
            date=today - timedelta(days=2),
            views_count=10,
            contacts_count=2,
            trust_score=0.8,
        )
        cls.metrics_day2 = DailyAdMetrics.objects.create(
            ad=cls.ad,
            date=today - timedelta(days=1),
            views_count=20,
            contacts_count=3,
            trust_score=0.9,
        )
        cls.metrics_day3 = DailyAdMetrics.objects.create(
            ad=cls.ad,
            date=today,
            views_count=30,
            contacts_count=5,
            trust_score=0.95,
        )

        # Noise: another seller's metrics (should not appear)
        DailyAdMetrics.objects.create(
            ad=cls.other_ad,
            date=today,
            views_count=999,
            contacts_count=999,
        )

    def test_returns_metrics_for_seller(self) -> None:
        """Returns only DailyAdMetrics for the specified seller's ads."""
        metrics = get_seller_daily_metrics(self.user.id)
        self.assertEqual(len(metrics), 3)

        ad_ids = {m.ad_id for m in metrics}
        assert self.ad.id is not None
        self.assertEqual(ad_ids, {self.ad.id})

    def test_excludes_other_sellers(self) -> None:
        """Other sellers' metrics are not included."""
        metrics = get_seller_daily_metrics(self.user.id)
        assert self.other_ad.id is not None
        other_ad_ids = {m.ad_id for m in metrics if m.ad_id == self.other_ad.id}
        self.assertEqual(len(other_ad_ids), 0)

    def test_ordered_by_date_desc_then_ad_id(self) -> None:
        """Results are ordered by date descending, then ad_id."""
        metrics = get_seller_daily_metrics(self.user.id)
        dates = [m.date for m in metrics]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_days_parameter_filters_by_cutoff(self) -> None:
        """The days parameter limits the lookback window."""
        metrics_1_day = get_seller_daily_metrics(self.user.id, days=1)
        self.assertEqual(len(metrics_1_day), 1)
        assert self.metrics_day3 is not None
        self.assertEqual(metrics_1_day[0].date, self.metrics_day3.date)

        metrics_2_days = get_seller_daily_metrics(self.user.id, days=2)
        self.assertEqual(len(metrics_2_days), 2)

    def test_empty_when_no_metrics(self) -> None:
        """A seller with no metrics returns an empty list."""
        empty_user = _make_user(telegram_id=990010303)
        metrics = get_seller_daily_metrics(empty_user.id)
        self.assertEqual(metrics, [])

    def test_returns_all_metric_fields(self) -> None:
        """Returned metrics contain all expected fields."""
        metrics = get_seller_daily_metrics(self.user.id, days=1)
        self.assertEqual(len(metrics), 1)
        m = metrics[0]
        assert self.ad.id is not None
        self.assertEqual(m.ad_id, self.ad.id)
        self.assertEqual(m.views_count, 30)
        self.assertEqual(m.contacts_count, 5)
        self.assertAlmostEqual(m.trust_score, 0.95)  # type: ignore[arg-type]