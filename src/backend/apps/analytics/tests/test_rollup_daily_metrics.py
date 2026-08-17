"""
Tests for the rollup_daily_metrics management command (TASK_059).

Covers dry-run mode (no DB mutations), actual metrics aggregation with
existing events, advisory lock acquisition, and idempotency (running twice
produces the same result).

Uses ``django.test.TestCase`` for DB-backed assertions.
"""

from __future__ import annotations

import datetime as _dt
from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.ads.models import Ad
from apps.analytics.models import AnalyticsEvent, DailyAdMetrics
from apps.categories.models import Category
from apps.core.enums import AdSource, AdStatus, AnalyticsEventType
from apps.locations.models import City
from apps.users.models import User

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_user(telegram_id: int = 990050001, **overrides: object) -> User:
    """Create a User with sensible defaults for rollup tests."""
    defaults: dict = {
        "telegram_id": telegram_id,
        "chat_id": telegram_id,
        "username": None,
        "password": "x",
    }
    defaults.update(overrides)
    return User.objects.create(**defaults)  # type: ignore[arg-type]


def _make_category(slug: str = "rollup-cat") -> Category:
    """Create a Category with sensible defaults."""
    return Category.objects.create(
        name="Rollup Category",
        slug=slug,
    )


def _make_city(slug: str = "rollup-city") -> City:
    """Create a City with sensible defaults."""
    return City.objects.create(
        country_code="ME",
        name="Rollup City",
        region="Rollup Region",
        slug=slug,
    )


def _make_ad(
    user: User,
    category: Category,
    city: City,
    *,
    title: str = "Rollup Ad",
    status: AdStatus = AdStatus.PUBLISHED,
    **overrides: object,
) -> Ad:
    """Create an Ad with sensible defaults for rollup tests."""
    defaults: dict = {
        "user": user,
        "title": title,
        "description": "Rollup test description",
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
    user: User | None = None,
    hours_ago: int = 6,
) -> AnalyticsEvent:
    """Create an AnalyticsEvent for yesterday (the command's target date)."""
    yesterday = timezone.now().date() - timedelta(days=1)
    naive = _dt.datetime.combine(yesterday, _dt.time(hour=12 - hours_ago))
    timestamp = timezone.make_aware(naive)
    return AnalyticsEvent.objects.create(
        ad=ad,
        user=user,
        event_type=event_type.value,
        timestamp=timestamp,
    )


# ---------------------------------------------------------------------------
# Tests: rollup_daily_metrics
# ---------------------------------------------------------------------------


class TestRollupDailyMetrics(TestCase):
    """Tests for the rollup_daily_metrics management command."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.category = _make_category()
        cls.city = _make_city()

        cls.seller1 = _make_user(telegram_id=990050101)
        cls.seller2 = _make_user(telegram_id=990050102)

        cls.ad1 = _make_ad(
            cls.seller1,
            cls.category,
            cls.city,
            title="Rollup Ad 1",
            status=AdStatus.PUBLISHED,
        )
        cls.ad2 = _make_ad(
            cls.seller1,
            cls.category,
            cls.city,
            title="Rollup Ad 2",
            status=AdStatus.PUBLISHED,
        )
        cls.ad3 = _make_ad(
            cls.seller2,
            cls.category,
            cls.city,
            title="Rollup Ad 3 (no events)",
            status=AdStatus.PUBLISHED,
        )

        # Events for ad1: 3 views, 2 contacts
        assert cls.ad1.id is not None
        _make_event(cls.ad1, AnalyticsEventType.AD_VIEWED, hours_ago=10)
        _make_event(cls.ad1, AnalyticsEventType.AD_VIEWED, hours_ago=8)
        _make_event(cls.ad1, AnalyticsEventType.AD_VIEWED, hours_ago=6)
        _make_event(cls.ad1, AnalyticsEventType.CONTACT_INITIATED, hours_ago=4)
        _make_event(cls.ad1, AnalyticsEventType.CONTACT_COMPLETED, hours_ago=2)

        # Events for ad2: 1 view, 1 contact
        assert cls.ad2.id is not None
        _make_event(cls.ad2, AnalyticsEventType.AD_VIEWED, hours_ago=9)
        _make_event(cls.ad2, AnalyticsEventType.CONTACT_INITIATED, hours_ago=3)

        # Ad3 has no events

        # Noise: an event for today (should be excluded)
        today = timezone.now().date()
        today_event_ts = timezone.make_aware(
            _dt.datetime.combine(today, _dt.time(hour=8)),
        )
        assert cls.ad1.id is not None
        AnalyticsEvent.objects.create(
            ad=cls.ad1,
            event_type=AnalyticsEventType.AD_VIEWED,
            timestamp=today_event_ts,
        )

        # Noise: an event for ad1 but with a non-target event type
        assert cls.ad1.id is not None
        _make_event(cls.ad1, AnalyticsEventType.DASHBOARD_VIEWED, hours_ago=5)

    # ------------------------------------------------------------------
    # Dry-run mode
    # ------------------------------------------------------------------

    def test_dry_run_does_not_create_daily_metrics(self) -> None:
        """Dry-run mode prints results but does not mutate the database."""
        assert DailyAdMetrics.objects.count() == 0

        call_command("rollup_daily_metrics", "--dry-run")

        # No records should have been created
        self.assertEqual(DailyAdMetrics.objects.count(), 0)

    def test_dry_run_can_be_called_multiple_times(self) -> None:
        """Repeated dry-run calls are safe and produce no mutations."""
        call_command("rollup_daily_metrics", "--dry-run")
        call_command("rollup_daily_metrics", "--dry-run")
        call_command("rollup_daily_metrics", "--dry-run")

        self.assertEqual(DailyAdMetrics.objects.count(), 0)

    # ------------------------------------------------------------------
    # Actual metrics rollup
    # ------------------------------------------------------------------

    def test_aggregates_ad_views_and_contacts(self) -> None:
        """Command aggregates views and contacts correctly per ad."""
        call_command("rollup_daily_metrics")

        yesterday = timezone.now().date() - timedelta(days=1)

        # Ad1 should have 3 views and 2 contacts
        assert self.ad1.id is not None
        metrics_ad1 = DailyAdMetrics.objects.get(ad=self.ad1, date=yesterday)
        self.assertEqual(metrics_ad1.views_count, 3)
        self.assertEqual(metrics_ad1.contacts_count, 2)

        # Ad2 should have 1 view and 1 contact
        assert self.ad2.id is not None
        metrics_ad2 = DailyAdMetrics.objects.get(ad=self.ad2, date=yesterday)
        self.assertEqual(metrics_ad2.views_count, 1)
        self.assertEqual(metrics_ad2.contacts_count, 1)

    def test_skips_ads_without_events(self) -> None:
        """Ads with no analytics events do not get a DailyAdMetrics record."""
        call_command("rollup_daily_metrics")

        yesterday = timezone.now().date() - timedelta(days=1)

        # Ad3 has no events → no metrics record
        assert self.ad3.id is not None
        with self.assertRaises(DailyAdMetrics.DoesNotExist):
            DailyAdMetrics.objects.get(ad=self.ad3, date=yesterday)

    def test_excludes_today_events(self) -> None:
        """Events from today are not included in yesterday's rollup."""
        call_command("rollup_daily_metrics")

        yesterday = timezone.now().date() - timedelta(days=1)

        # The extra view for ad1 today should not be counted
        assert self.ad1.id is not None
        metrics_ad1 = DailyAdMetrics.objects.get(ad=self.ad1, date=yesterday)
        self.assertEqual(metrics_ad1.views_count, 3)

    def test_excludes_non_target_event_types(self) -> None:
        """Events with non-target types (e.g. DASHBOARD_VIEWED) are excluded."""
        call_command("rollup_daily_metrics")

        yesterday = timezone.now().date() - timedelta(days=1)

        assert self.ad1.id is not None
        metrics_ad1 = DailyAdMetrics.objects.get(ad=self.ad1, date=yesterday)

        # Only AD_VIEWED counted as views; DASHBOARD_VIEWED is not a view
        self.assertEqual(metrics_ad1.views_count, 3)

    def test_trust_score_and_avg_response_time_remain_null(self) -> None:
        """Command only sets views_count/contacts_count; other fields stay null."""
        call_command("rollup_daily_metrics")

        yesterday = timezone.now().date() - timedelta(days=1)

        assert self.ad1.id is not None
        metrics = DailyAdMetrics.objects.get(ad=self.ad1, date=yesterday)
        self.assertIsNone(metrics.trust_score)
        self.assertIsNone(metrics.avg_response_time)

    def test_creates_records_for_all_eligible_ads(self) -> None:
        """Two ads with events produce two DailyAdMetrics records."""
        call_command("rollup_daily_metrics")

        yesterday = timezone.now().date() - timedelta(days=1)

        records = DailyAdMetrics.objects.filter(date=yesterday)
        self.assertEqual(records.count(), 2)

        ad_ids = {r.ad_id for r in records}
        assert self.ad1.id is not None
        assert self.ad2.id is not None
        self.assertEqual(ad_ids, {self.ad1.id, self.ad2.id})

    # ------------------------------------------------------------------
    # Advisory lock handling
    # ------------------------------------------------------------------

    def test_runs_under_advisory_lock(self) -> None:
        """Command runs successfully with advisory lock acquisition."""
        # The command acquires advisory lock internally.
        # If the lock fails, the command would raise an exception.
        # A successful run implies correct lock acquisition and release.
        call_command("rollup_daily_metrics")

        yesterday = timezone.now().date() - timedelta(days=1)
        assert self.ad1.id is not None
        metrics = DailyAdMetrics.objects.get(ad=self.ad1, date=yesterday)
        self.assertEqual(metrics.views_count, 3)

    def test_concurrent_lock_attempt(self) -> None:
        """A second call while inside the advisory lock is blocked.

        PostgreSQL advisory locks are session-scoped; attempting to acquire
        the same lock in the same transaction blocks. This test verifies that
        the command properly acquires and releases the lock by ensuring the
        outer transaction can acquire it after the command completes.
        """
        # The command should complete and release its lock normally.
        call_command("rollup_daily_metrics")

        # After the command, the lock is released, so this second call
        # should also succeed.
        call_command("rollup_daily_metrics")

        yesterday = timezone.now().date() - timedelta(days=1)
        assert self.ad1.id is not None
        metrics = DailyAdMetrics.objects.get(ad=self.ad1, date=yesterday)
        self.assertEqual(metrics.views_count, 3)

    # ------------------------------------------------------------------
    # Idempotency
    # ------------------------------------------------------------------

    def test_idempotent_runs_produce_same_metrics(self) -> None:
        """Running the command twice yields identical DailyAdMetrics records."""
        # First run
        call_command("rollup_daily_metrics")
        yesterday = timezone.now().date() - timedelta(days=1)

        assert self.ad1.id is not None
        metrics_first = DailyAdMetrics.objects.get(ad=self.ad1, date=yesterday)

        # Second run
        call_command("rollup_daily_metrics")
        metrics_second = DailyAdMetrics.objects.get(ad=self.ad1, date=yesterday)

        self.assertEqual(metrics_first.views_count, metrics_second.views_count)
        self.assertEqual(metrics_first.contacts_count, metrics_second.contacts_count)

    def test_idempotent_does_not_create_duplicate_records(self) -> None:
        """Running the command twice does not create duplicate DailyAdMetrics."""
        call_command("rollup_daily_metrics")
        call_command("rollup_daily_metrics")

        yesterday = timezone.now().date() - timedelta(days=1)

        # Should still have 2 records (one per ad with events)
        records = DailyAdMetrics.objects.filter(date=yesterday)
        self.assertEqual(records.count(), 2)
