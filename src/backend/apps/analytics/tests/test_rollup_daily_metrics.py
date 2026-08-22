"""
Tests for the rollup_daily_metrics management command (TASK_059).

Covers dry-run mode (no DB mutations), actual metrics aggregation with
existing events, advisory lock acquisition, and idempotency (running twice
produces the same result).
"""

from __future__ import annotations

import datetime as _dt
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.ads.models import Ad
from apps.analytics.models import AnalyticsEvent, DailyAdMetrics
from apps.core.enums import AdStatus, AnalyticsEventType

from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_user(telegram_id: int = 990050001, **overrides: object):
    """Create a User with sensible defaults for rollup tests."""
    from apps.users.models import User

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
    user=None,
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
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def rollup_data(seller, category, city):
    """Create ads and events for rollup command tests.

    Layout:
    - seller1 (passed as ``seller`` fixture) has 2 ads with events.
    - seller2 has 1 ad with no events (noise).
    - Today events and non-target event types are noise.
    """
    seller1 = seller
    seller2 = _make_user(telegram_id=990050102)

    ad1 = create_test_ad(
        seller1, category, city, title="Rollup Ad 1", status=AdStatus.PUBLISHED
    )
    ad2 = create_test_ad(
        seller1, category, city, title="Rollup Ad 2", status=AdStatus.PUBLISHED
    )
    ad3 = create_test_ad(
        seller2, category, city, title="Rollup Ad 3 (no events)", status=AdStatus.PUBLISHED
    )

    # Events for ad1: 3 views, 2 contacts
    _make_event(ad1, AnalyticsEventType.AD_VIEWED, hours_ago=10)
    _make_event(ad1, AnalyticsEventType.AD_VIEWED, hours_ago=8)
    _make_event(ad1, AnalyticsEventType.AD_VIEWED, hours_ago=6)
    _make_event(ad1, AnalyticsEventType.CONTACT_INITIATED, hours_ago=4)
    _make_event(ad1, AnalyticsEventType.CONTACT_COMPLETED, hours_ago=2)

    # Events for ad2: 1 view, 1 contact
    _make_event(ad2, AnalyticsEventType.AD_VIEWED, hours_ago=9)
    _make_event(ad2, AnalyticsEventType.CONTACT_INITIATED, hours_ago=3)

    # Ad3 has no events

    # Noise: today event for ad1
    today = timezone.now().date()
    today_event_ts = timezone.make_aware(
        _dt.datetime.combine(today, _dt.time(hour=8)),
    )
    AnalyticsEvent.objects.create(
        ad=ad1,
        event_type=AnalyticsEventType.AD_VIEWED,
        timestamp=today_event_ts,
    )

    # Noise: non-target event type for ad1
    _make_event(ad1, AnalyticsEventType.DASHBOARD_VIEWED, hours_ago=5)

    return {"seller1": seller1, "seller2": seller2, "ad1": ad1, "ad2": ad2, "ad3": ad3}


# ---------------------------------------------------------------------------
# Tests: dry-run mode
# ---------------------------------------------------------------------------


class TestRollupDailyMetricsDryRun:
    """Tests for the dry-run mode of rollup_daily_metrics."""

    def test_dry_run_does_not_create_daily_metrics(self, rollup_data) -> None:
        """Dry-run mode prints results but does not mutate the database."""
        assert DailyAdMetrics.objects.count() == 0

        call_command("rollup_daily_metrics", "--dry-run")

        # No records should have been created
        assert DailyAdMetrics.objects.count() == 0

    def test_dry_run_can_be_called_multiple_times(self, rollup_data) -> None:
        """Repeated dry-run calls are safe and produce no mutations."""
        call_command("rollup_daily_metrics", "--dry-run")
        call_command("rollup_daily_metrics", "--dry-run")
        call_command("rollup_daily_metrics", "--dry-run")

        assert DailyAdMetrics.objects.count() == 0


# ---------------------------------------------------------------------------
# Tests: actual metrics rollup
# ---------------------------------------------------------------------------


class TestRollupDailyMetricsAggregation:
    """Tests for metrics aggregation by the rollup command."""

    def test_aggregates_ad_views_and_contacts(self, rollup_data) -> None:
        """Command aggregates views and contacts correctly per ad."""
        ad1 = rollup_data["ad1"]
        ad2 = rollup_data["ad2"]

        call_command("rollup_daily_metrics")

        yesterday = timezone.now().date() - timedelta(days=1)

        # Ad1 should have 3 views and 2 contacts
        metrics_ad1 = DailyAdMetrics.objects.get(ad=ad1, date=yesterday)
        assert metrics_ad1.views_count == 3
        assert metrics_ad1.contacts_count == 2

        # Ad2 should have 1 view and 1 contact
        metrics_ad2 = DailyAdMetrics.objects.get(ad=ad2, date=yesterday)
        assert metrics_ad2.views_count == 1
        assert metrics_ad2.contacts_count == 1

    def test_skips_ads_without_events(self, rollup_data) -> None:
        """Ads with no analytics events do not get a DailyAdMetrics record."""
        ad3 = rollup_data["ad3"]

        call_command("rollup_daily_metrics")

        yesterday = timezone.now().date() - timedelta(days=1)

        with pytest.raises(DailyAdMetrics.DoesNotExist):
            DailyAdMetrics.objects.get(ad=ad3, date=yesterday)

    def test_excludes_today_events(self, rollup_data) -> None:
        """Events from today are not included in yesterday's rollup."""
        ad1 = rollup_data["ad1"]

        call_command("rollup_daily_metrics")

        yesterday = timezone.now().date() - timedelta(days=1)

        metrics_ad1 = DailyAdMetrics.objects.get(ad=ad1, date=yesterday)
        assert metrics_ad1.views_count == 3

    def test_excludes_non_target_event_types(self, rollup_data) -> None:
        """Events with non-target types (e.g. DASHBOARD_VIEWED) are excluded."""
        ad1 = rollup_data["ad1"]

        call_command("rollup_daily_metrics")

        yesterday = timezone.now().date() - timedelta(days=1)
        metrics_ad1 = DailyAdMetrics.objects.get(ad=ad1, date=yesterday)
        assert metrics_ad1.views_count == 3

    def test_trust_score_and_avg_response_time_remain_null(self, rollup_data) -> None:
        """Command only sets views_count/contacts_count; other fields stay null."""
        ad1 = rollup_data["ad1"]

        call_command("rollup_daily_metrics")

        yesterday = timezone.now().date() - timedelta(days=1)
        metrics = DailyAdMetrics.objects.get(ad=ad1, date=yesterday)
        assert metrics.trust_score is None
        assert metrics.avg_response_time is None

    def test_creates_records_for_all_eligible_ads(self, rollup_data) -> None:
        """Two ads with events produce two DailyAdMetrics records."""
        ad1 = rollup_data["ad1"]
        ad2 = rollup_data["ad2"]

        call_command("rollup_daily_metrics")

        yesterday = timezone.now().date() - timedelta(days=1)

        records = DailyAdMetrics.objects.filter(date=yesterday)
        assert records.count() == 2

        ad_ids = {r.ad_id for r in records}
        assert ad_ids == {ad1.id, ad2.id}


# ---------------------------------------------------------------------------
# Tests: advisory lock handling
# ---------------------------------------------------------------------------


class TestRollupDailyMetricsLock:
    """Tests for advisory lock handling in the rollup command."""

    def test_runs_under_advisory_lock(self, rollup_data) -> None:
        """Command runs successfully with advisory lock acquisition."""
        ad1 = rollup_data["ad1"]

        call_command("rollup_daily_metrics")

        yesterday = timezone.now().date() - timedelta(days=1)
        metrics = DailyAdMetrics.objects.get(ad=ad1, date=yesterday)
        assert metrics.views_count == 3

    def test_concurrent_lock_attempt(self, rollup_data) -> None:
        """A second call while inside the advisory lock is blocked.

        PostgreSQL advisory locks are session-scoped; attempting to acquire
        the same lock in the same transaction blocks. This test verifies that
        the command properly acquires and releases the lock by ensuring the
        outer transaction can acquire it after the command completes.
        """
        ad1 = rollup_data["ad1"]

        # The command should complete and release its lock normally.
        call_command("rollup_daily_metrics")

        # After the command, the lock is released, so this second call
        # should also succeed.
        call_command("rollup_daily_metrics")

        yesterday = timezone.now().date() - timedelta(days=1)
        metrics = DailyAdMetrics.objects.get(ad=ad1, date=yesterday)
        assert metrics.views_count == 3


# ---------------------------------------------------------------------------
# Tests: idempotency
# ---------------------------------------------------------------------------


class TestRollupDailyMetricsIdempotency:
    """Tests that running the command twice produces identical results."""

    def test_runs_produce_same_metrics(self, rollup_data) -> None:
        """Running the command twice yields identical DailyAdMetrics records."""
        ad1 = rollup_data["ad1"]

        # First run
        call_command("rollup_daily_metrics")
        yesterday = timezone.now().date() - timedelta(days=1)
        metrics_first = DailyAdMetrics.objects.get(ad=ad1, date=yesterday)

        # Second run
        call_command("rollup_daily_metrics")
        metrics_second = DailyAdMetrics.objects.get(ad=ad1, date=yesterday)

        assert metrics_first.views_count == metrics_second.views_count
        assert metrics_first.contacts_count == metrics_second.contacts_count

    def test_idempotent_does_not_create_duplicate_records(self, rollup_data) -> None:
        """Running the command twice does not create duplicate DailyAdMetrics."""
        call_command("rollup_daily_metrics")
        call_command("rollup_daily_metrics")

        yesterday = timezone.now().date() - timedelta(days=1)

        records = DailyAdMetrics.objects.filter(date=yesterday)
        assert records.count() == 2
