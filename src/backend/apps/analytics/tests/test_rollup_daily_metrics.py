"""
Tests for the rollup_daily_metrics management command (TASK_059).

Covers dry-run mode (no DB mutations), actual metrics aggregation with
existing events, advisory lock acquisition, idempotency (running twice
produces the same result), and seed-source event exclusion.
"""

from __future__ import annotations

import datetime as _dt
import threading
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.ads.models import Ad
from apps.analytics.models import AnalyticsEvent, DailyAdMetrics
from apps.core.enums import AdSource, AdStatus, AnalyticsEventType
from conftest import create_test_ad, make_user

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_event(
    ad: Ad,
    event_type: AnalyticsEventType,
    *,
    user=None,
    hours_ago: int = 6,
    source: AdSource | None = None,
    date: _dt.date | None = None,
) -> AnalyticsEvent:
    """Create an AnalyticsEvent for the target date (yesterday by default).

    ``date`` defaults to yesterday so the fixture and the rollup command
    compute the same reference date even when the test crosses midnight.
    """
    target_date = date or (timezone.now().date() - timedelta(days=1))
    naive = _dt.datetime.combine(target_date, _dt.time(hour=12 - hours_ago))
    timestamp = timezone.make_aware(naive)
    return AnalyticsEvent.objects.create(
        ad=ad,
        user=user,
        event_type=event_type.value,
        timestamp=timestamp,
        source=source,
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

    A fixed ``fixed_date`` (yesterday) is computed once and passed to all
    ``_make_event`` calls so the fixture and the rollup command share the
    same reference date even when the test crosses midnight.
    """
    fixed_date = timezone.now().date() - timedelta(days=1)
    seller1 = seller
    seller2 = make_user(telegram_id=990050102)

    ad1 = create_test_ad(
        seller1, category, city, title="Rollup Ad 1", status=AdStatus.PUBLISHED
    )
    ad2 = create_test_ad(
        seller1, category, city, title="Rollup Ad 2", status=AdStatus.PUBLISHED
    )
    ad3 = create_test_ad(
        seller2,
        category,
        city,
        title="Rollup Ad 3 (no events)",
        status=AdStatus.PUBLISHED,
    )

    # Events for ad1: 3 views, 2 contacts
    _make_event(ad1, AnalyticsEventType.AD_VIEWED, hours_ago=10, date=fixed_date)
    _make_event(ad1, AnalyticsEventType.AD_VIEWED, hours_ago=8, date=fixed_date)
    _make_event(ad1, AnalyticsEventType.AD_VIEWED, hours_ago=6, date=fixed_date)
    _make_event(
        ad1, AnalyticsEventType.CONTACT_INITIATED, hours_ago=4, date=fixed_date
    )
    _make_event(
        ad1, AnalyticsEventType.CONTACT_COMPLETED, hours_ago=2, date=fixed_date
    )

    # Events for ad2: 1 view, 1 contact
    _make_event(ad2, AnalyticsEventType.AD_VIEWED, hours_ago=9, date=fixed_date)
    _make_event(
        ad2, AnalyticsEventType.CONTACT_INITIATED, hours_ago=3, date=fixed_date
    )

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
    _make_event(
        ad1, AnalyticsEventType.DASHBOARD_VIEWED, hours_ago=5, date=fixed_date
    )

    return {
        "seller1": seller1,
        "seller2": seller2,
        "ad1": ad1,
        "ad2": ad2,
        "ad3": ad3,
        "fixed_date": fixed_date,
    }


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
        fixed_date = rollup_data["fixed_date"]

        call_command("rollup_daily_metrics", f"--date={fixed_date.isoformat()}")

        # Ad1 should have 3 views and 2 contacts
        metrics_ad1 = DailyAdMetrics.objects.get(ad=ad1, date=fixed_date)
        assert metrics_ad1.views_count == 3
        assert metrics_ad1.contacts_count == 2

        # Ad2 should have 1 view and 1 contact
        metrics_ad2 = DailyAdMetrics.objects.get(ad=ad2, date=fixed_date)
        assert metrics_ad2.views_count == 1
        assert metrics_ad2.contacts_count == 1

    def test_skips_ads_without_events(self, rollup_data) -> None:
        """Ads with no analytics events do not get a DailyAdMetrics record."""
        ad3 = rollup_data["ad3"]
        fixed_date = rollup_data["fixed_date"]

        call_command("rollup_daily_metrics", f"--date={fixed_date.isoformat()}")

        with pytest.raises(DailyAdMetrics.DoesNotExist):
            DailyAdMetrics.objects.get(ad=ad3, date=fixed_date)

    def test_excludes_today_events(self, rollup_data) -> None:
        """Events from today are not included in yesterday's rollup."""
        ad1 = rollup_data["ad1"]
        fixed_date = rollup_data["fixed_date"]

        call_command("rollup_daily_metrics", f"--date={fixed_date.isoformat()}")

        metrics_ad1 = DailyAdMetrics.objects.get(ad=ad1, date=fixed_date)
        assert metrics_ad1.views_count == 3

    def test_excludes_non_target_event_types(self, rollup_data) -> None:
        """Events with non-target types (e.g. DASHBOARD_VIEWED) are excluded."""
        ad1 = rollup_data["ad1"]
        fixed_date = rollup_data["fixed_date"]

        call_command("rollup_daily_metrics", f"--date={fixed_date.isoformat()}")

        metrics_ad1 = DailyAdMetrics.objects.get(ad=ad1, date=fixed_date)
        assert metrics_ad1.views_count == 3

    def test_trust_score_and_avg_response_time_remain_null(self, rollup_data) -> None:
        """Command only sets views_count/contacts_count; other fields stay null."""
        ad1 = rollup_data["ad1"]
        fixed_date = rollup_data["fixed_date"]

        call_command("rollup_daily_metrics", f"--date={fixed_date.isoformat()}")

        metrics = DailyAdMetrics.objects.get(ad=ad1, date=fixed_date)
        assert metrics.trust_score is None
        assert metrics.avg_response_time is None

    def test_creates_records_for_all_eligible_ads(self, rollup_data) -> None:
        """Two ads with events produce two DailyAdMetrics records."""
        ad1 = rollup_data["ad1"]
        ad2 = rollup_data["ad2"]
        fixed_date = rollup_data["fixed_date"]

        call_command("rollup_daily_metrics", f"--date={fixed_date.isoformat()}")

        records = DailyAdMetrics.objects.filter(date=fixed_date)
        assert records.count() == 2

        ad_ids = {r.ad_id for r in records}
        assert ad_ids == {ad1.id, ad2.id}

    def test_date_parameter_targets_specific_date(self, seller, category, city) -> None:
        """The --date parameter targets a specific date instead of yesterday.

        Creates events for three days ago and rolls up with ``--date`` to
        verify the command respects the override rather than defaulting
        to yesterday.
        """
        ad = create_test_ad(
            seller, category, city, title="Date Param Ad", status=AdStatus.PUBLISHED
        )
        target_date = timezone.now().date() - timedelta(days=3)
        _make_event(ad, AnalyticsEventType.AD_VIEWED, date=target_date)

        call_command("rollup_daily_metrics", f"--date={target_date.isoformat()}")

        metrics = DailyAdMetrics.objects.get(ad=ad, date=target_date)
        assert metrics.views_count == 1


# ---------------------------------------------------------------------------
# Tests: advisory lock handling
# ---------------------------------------------------------------------------


class TestRollupDailyMetricsLock:
    """Tests for advisory lock handling in the rollup command."""

    def test_runs_under_advisory_lock(self, rollup_data) -> None:
        """Command runs successfully with advisory lock acquisition."""
        ad1 = rollup_data["ad1"]
        fixed_date = rollup_data["fixed_date"]

        call_command("rollup_daily_metrics", f"--date={fixed_date.isoformat()}")

        metrics = DailyAdMetrics.objects.get(ad=ad1, date=fixed_date)
        assert metrics.views_count == 3

    @pytest.mark.django_db(transaction=True)
    def test_concurrent_lock_attempt(self, rollup_data) -> None:
        """Two concurrent calls serialize on the advisory lock without deadlock.

        PostgreSQL advisory locks (Q8) are transaction-scoped: the second call
        blocks on ``pg_advisory_xact_lock`` until the first commits and releases
        the lock, then proceeds. This verifies true concurrency — both threads
        complete without deadlock.
        """
        ad1 = rollup_data["ad1"]
        fixed_date = rollup_data["fixed_date"]
        errors: list[BaseException] = []
        barrier = threading.Barrier(2, timeout=30)

        def _run() -> None:
            try:
                barrier.wait()
                call_command(
                    "rollup_daily_metrics", f"--date={fixed_date.isoformat()}"
                )
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=_run)
        t2 = threading.Thread(target=_run)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors

        metrics = DailyAdMetrics.objects.get(ad=ad1, date=fixed_date)
        assert metrics.views_count == 3


# ---------------------------------------------------------------------------
# Tests: empty aggregation early return
# ---------------------------------------------------------------------------


class TestRollupDailyMetricsEmptyAggregation:
    """Tests for early return when no events exist for the target date."""

    def test_no_events_returns_early_without_metrics(self) -> None:
        """When no events exist for yesterday, no DailyAdMetrics are created.

        The command logs and returns before reaching the bulk-upsert path,
        so no records are written.
        """
        assert AnalyticsEvent.objects.count() == 0

        call_command("rollup_daily_metrics")

        assert AnalyticsEvent.objects.count() == 0
        assert DailyAdMetrics.objects.count() == 0


# ---------------------------------------------------------------------------
# Tests: idempotency
# ---------------------------------------------------------------------------


class TestRollupDailyMetricsIdempotency:
    """Tests that running the command twice produces identical results."""

    def test_runs_produce_same_metrics(self, rollup_data) -> None:
        """Running the command twice yields identical DailyAdMetrics records."""
        ad1 = rollup_data["ad1"]
        fixed_date = rollup_data["fixed_date"]

        # First run
        call_command("rollup_daily_metrics", f"--date={fixed_date.isoformat()}")
        metrics_first = DailyAdMetrics.objects.get(ad=ad1, date=fixed_date)

        # Second run
        call_command("rollup_daily_metrics", f"--date={fixed_date.isoformat()}")
        metrics_second = DailyAdMetrics.objects.get(ad=ad1, date=fixed_date)

        assert metrics_first.views_count == metrics_second.views_count
        assert metrics_first.contacts_count == metrics_second.contacts_count

    def test_idempotent_does_not_create_duplicate_records(self, rollup_data) -> None:
        """Running the command twice does not create duplicate DailyAdMetrics."""
        fixed_date = rollup_data["fixed_date"]
        date_arg = f"--date={fixed_date.isoformat()}"

        call_command("rollup_daily_metrics", date_arg)
        call_command("rollup_daily_metrics", date_arg)

        records = DailyAdMetrics.objects.filter(date=fixed_date)
        assert records.count() == 2


# ---------------------------------------------------------------------------
# Tests: chunked bulk upsert against the unique constraint (13-PERF-003)
# ---------------------------------------------------------------------------


class TestRollupDailyMetricsBulkUpsert:
    """The write path is a chunked ``bulk_create(update_conflicts=True)``.

    A re-run must update the existing row in place — no duplicate and no
    silently dropped update — and a pre-existing stale value must be overwritten
    by the fresh aggregate rather than left behind.
    """

    def test_second_run_updates_existing_row_in_place(self, rollup_data) -> None:
        """A stale pre-existing row is overwritten in place, not duplicated."""
        ad1 = rollup_data["ad1"]
        fixed_date = rollup_data["fixed_date"]

        # Pre-seed a stale row for ad1 with wrong counts.
        DailyAdMetrics.objects.create(
            ad=ad1,
            date=fixed_date,
            views_count=99,
            contacts_count=99,
        )

        call_command("rollup_daily_metrics", f"--date={fixed_date.isoformat()}")

        rows = DailyAdMetrics.objects.filter(ad=ad1, date=fixed_date)
        assert rows.count() == 1, "upsert must update in place, not duplicate"
        metrics = rows.get()
        assert metrics.views_count == 3
        assert metrics.contacts_count == 2

    def test_rerun_overwrites_changed_aggregate(self, rollup_data) -> None:
        """A subsequent run reflects the new aggregate over the same ad+date."""
        ad1 = rollup_data["ad1"]
        fixed_date = rollup_data["fixed_date"]

        call_command("rollup_daily_metrics", f"--date={fixed_date.isoformat()}")
        first = DailyAdMetrics.objects.get(ad=ad1, date=fixed_date)
        assert first.views_count == 3

        # A new view event for the same ad and target date.
        _make_event(
            ad1, AnalyticsEventType.AD_VIEWED, hours_ago=7, date=fixed_date
        )

        call_command("rollup_daily_metrics", f"--date={fixed_date.isoformat()}")

        rows = DailyAdMetrics.objects.filter(ad=ad1, date=fixed_date)
        assert rows.count() == 1
        assert rows.get().views_count == 4

    def test_created_row_carries_timestamps(self, rollup_data) -> None:
        """``bulk_create`` bypasses ``auto_now``; the command sets both stamps."""
        ad1 = rollup_data["ad1"]
        fixed_date = rollup_data["fixed_date"]

        call_command("rollup_daily_metrics", f"--date={fixed_date.isoformat()}")

        metrics = DailyAdMetrics.objects.get(ad=ad1, date=fixed_date)
        assert metrics.created_at is not None
        assert metrics.updated_at is not None


# ---------------------------------------------------------------------------
# Tests: seed-source exclusion
# ---------------------------------------------------------------------------


class TestRollupDailyMetricsSeedExclusion:
    """Seed-source events are excluded from rollup by ``SeedService._clean``.

    The rollup command itself does NOT filter by ``source``; seed events are
    removed beforehand via ``AnalyticsEvent.objects.filter(source=AdSource.SEED)``.
    These tests verify that flow: seed events coexist with production events,
    ``_clean`` purges seed events, and the rollup counts production events only.
    """

    @pytest.fixture
    def seed_exclusion_data(self, seller, category, city):
        """Create an ad with both seed-source and production events for yesterday.

        - 2 production AD_VIEWED, 1 production CONTACT_INITIATED,
          1 production CONTACT_COMPLETED
        - 2 seed AD_VIEWED, 1 seed CONTACT_INITIATED, 1 seed CONTACT_COMPLETED

        A fixed ``fixed_date`` (yesterday) is computed once and passed to all
        ``_make_event`` calls so the fixture and the rollup command share the
        same reference date even when the test crosses midnight.
        """
        fixed_date = timezone.now().date() - timedelta(days=1)
        ad = create_test_ad(
            seller, category, city, title="Seed Exclusion Ad", status=AdStatus.PUBLISHED
        )

        # Production events (source=None = production)
        _make_event(ad, AnalyticsEventType.AD_VIEWED, hours_ago=10, date=fixed_date)
        _make_event(ad, AnalyticsEventType.AD_VIEWED, hours_ago=8, date=fixed_date)
        _make_event(
            ad, AnalyticsEventType.CONTACT_INITIATED, hours_ago=6, date=fixed_date
        )
        _make_event(
            ad, AnalyticsEventType.CONTACT_COMPLETED, hours_ago=4, date=fixed_date
        )

        # Seed-source events (source=AdSource.SEED) — should be excluded after _clean
        _make_event(
            ad, AnalyticsEventType.AD_VIEWED, hours_ago=5, source=AdSource.SEED, date=fixed_date
        )
        _make_event(
            ad, AnalyticsEventType.AD_VIEWED, hours_ago=3, source=AdSource.SEED, date=fixed_date
        )
        _make_event(
            ad,
            AnalyticsEventType.CONTACT_INITIATED,
            hours_ago=4,
            source=AdSource.SEED,
            date=fixed_date,
        )
        _make_event(
            ad,
            AnalyticsEventType.CONTACT_COMPLETED,
            hours_ago=2,
            source=AdSource.SEED,
            date=fixed_date,
        )

        return {"ad": ad, "fixed_date": fixed_date}

    def test_seed_events_excluded_after_clean(self, seed_exclusion_data) -> None:
        """After ``_clean`` removes seed events, rollup counts production only."""
        ad = seed_exclusion_data["ad"]
        fixed_date = seed_exclusion_data["fixed_date"]

        # Simulate SeedService._clean() purging seed-source events
        AnalyticsEvent.objects.filter(source=AdSource.SEED).delete()

        call_command("rollup_daily_metrics", f"--date={fixed_date.isoformat()}")

        metrics = DailyAdMetrics.objects.get(ad=ad, date=fixed_date)
        assert metrics.views_count == 2
        assert metrics.contacts_count == 2

    def test_seed_events_counted_without_clean(self, seed_exclusion_data) -> None:
        """Without ``_clean``, seed events inflate rollup counts (proves cleanup needed).

        The rollup command does not filter by ``source``, so seed events ARE
        counted when present — confirming that ``_clean`` is the exclusion
        mechanism.
        """
        ad = seed_exclusion_data["ad"]
        fixed_date = seed_exclusion_data["fixed_date"]

        call_command("rollup_daily_metrics", f"--date={fixed_date.isoformat()}")

        metrics = DailyAdMetrics.objects.get(ad=ad, date=fixed_date)
        assert metrics.views_count == 4
        assert metrics.contacts_count == 4
