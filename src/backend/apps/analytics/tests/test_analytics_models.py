"""
Model-level tests for analytics models (B17-Findings 4.5, 4.10).

Covers:
- ``DailyAdMetrics`` unique constraint on (ad, date)
- ``AnalyticsEvent.source`` default value
- ``DailyAdMetrics`` timestamp fields (``auto_now`` / ``auto_now_add``)
"""

from __future__ import annotations

from datetime import date

import pytest
from django.db import IntegrityError, transaction

from apps.analytics.models import AnalyticsEvent, DailyAdMetrics
from apps.core.enums import AdStatus, AnalyticsEventType
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.unit]


# ---------------------------------------------------------------------------
# Tests: DailyAdMetrics unique constraint
# ---------------------------------------------------------------------------


class TestDailyAdMetricsUniqueConstraint:
    """The (ad, date) pair must be unique — enforced by ``uq_daily_ad_metrics_ad_date``."""

    def test_duplicate_ad_date_raises_integrity_error(
        self, seller, category, city
    ) -> None:
        """Creating two DailyAdMetrics rows with the same (ad, date) raises IntegrityError."""
        ad = create_test_ad(
            seller, category, city, title="Unique Constraint Ad",
            status=AdStatus.PUBLISHED,
        )
        target_date = date(2026, 1, 15)

        DailyAdMetrics.objects.create(
            ad=ad,
            date=target_date,
            views_count=5,
            contacts_count=2,
        )

        with pytest.raises(IntegrityError):
            with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
                DailyAdMetrics.objects.create(
                    ad=ad,
                    date=target_date,
                    views_count=1,
                    contacts_count=1,
                )

    def test_same_date_different_ads_allowed(
        self, seller, category, city
    ) -> None:
        """Rows with the same date but different ads are allowed."""
        ad1 = create_test_ad(
            seller, category, city, title="Constraint Ad 1",
            status=AdStatus.PUBLISHED,
        )
        ad2 = create_test_ad(
            seller, category, city, title="Constraint Ad 2",
            status=AdStatus.PUBLISHED,
        )
        target_date = date(2026, 1, 15)

        DailyAdMetrics.objects.create(
            ad=ad1, date=target_date, views_count=3, contacts_count=1
        )
        DailyAdMetrics.objects.create(
            ad=ad2, date=target_date, views_count=7, contacts_count=2
        )

        assert DailyAdMetrics.objects.filter(date=target_date).count() == 2

    def test_same_ad_different_dates_allowed(
        self, seller, category, city
    ) -> None:
        """Multiple dates for the same ad are allowed (no cross-day conflict)."""
        ad = create_test_ad(
            seller, category, city, title="Multi Date Ad",
            status=AdStatus.PUBLISHED,
        )

        DailyAdMetrics.objects.create(
            ad=ad, date=date(2026, 1, 15), views_count=3, contacts_count=1
        )
        DailyAdMetrics.objects.create(
            ad=ad, date=date(2026, 1, 16), views_count=5, contacts_count=2
        )

        assert DailyAdMetrics.objects.filter(ad=ad).count() == 2


# ---------------------------------------------------------------------------
# Tests: AnalyticsEvent.source default
# ---------------------------------------------------------------------------


class TestAnalyticsEventSourceDefault:
    """The ``source`` field defaults to ``None`` (production), not an enum value."""

    def test_created_without_source_has_none(self, seller, category, city) -> None:
        """An AnalyticsEvent created without ``source`` has ``source=None``."""
        ad = create_test_ad(
            seller, category, city, title="Source Default Ad",
            status=AdStatus.PUBLISHED,
        )

        event = AnalyticsEvent.objects.create(
            ad=ad,
            event_type=AnalyticsEventType.AD_VIEWED,
        )

        assert event.source is None

    def test_field_default_is_none(self) -> None:
        """The ``source`` field's configured default is ``None``."""
        field = AnalyticsEvent._meta.get_field("source")
        assert field.default is None

    def test_field_allows_null(self) -> None:
        """The ``source`` column is nullable in the database schema."""
        field = AnalyticsEvent._meta.get_field("source")
        assert field.null is True


# ---------------------------------------------------------------------------
# Tests: DailyAdMetrics timestamps
# ---------------------------------------------------------------------------


class TestDailyAdMetricsTimestamps:
    """``created_at`` (``auto_now_add``) and ``updated_at`` (``auto_now``) behave
    as expected on ``objects.create()`` and subsequent ``save()``.

    Note: the ``rollup_daily_metrics`` management command uses
    ``bulk_create``, which bypasses both ``auto_now`` and ``auto_now_add``;
    the command sets ``created_at`` and ``updated_at`` explicitly on each
    row. The tests below cover the default ORM path (``save()``), not the
    bulk path — see ``test_rollup_daily_metrics.py::TestRollupDailyMetricsBulkUpsert``
    for the bulk-create coverage.
    """

    def test_created_at_set_on_create(self, seller, category, city) -> None:
        """``created_at`` is automatically populated on insert."""
        ad = create_test_ad(
            seller, category, city, title="Created At Ad",
            status=AdStatus.PUBLISHED,
        )

        metrics = DailyAdMetrics.objects.create(
            ad=ad, date=date(2026, 1, 20), views_count=1, contacts_count=0
        )

        assert metrics.created_at is not None

    def test_updated_at_set_on_create(self, seller, category, city) -> None:
        """``updated_at`` is automatically populated on insert."""
        ad = create_test_ad(
            seller, category, city, title="Updated At Ad",
            status=AdStatus.PUBLISHED,
        )

        metrics = DailyAdMetrics.objects.create(
            ad=ad, date=date(2026, 1, 20), views_count=1, contacts_count=0
        )

        assert metrics.updated_at is not None

    def test_updated_at_refreshed_on_save(self, seller, category, city) -> None:
        """``updated_at`` is refreshed on ``save()``; ``created_at`` is not."""
        ad = create_test_ad(
            seller, category, city, title="Save Refresh Ad",
            status=AdStatus.PUBLISHED,
        )

        metrics = DailyAdMetrics.objects.create(
            ad=ad, date=date(2026, 1, 20), views_count=1, contacts_count=0
        )
        created_at = metrics.created_at

        metrics.views_count = 99
        metrics.save()

        refreshed = DailyAdMetrics.objects.get(pk=metrics.pk)
        assert refreshed.created_at == created_at
        assert refreshed.updated_at >= metrics.updated_at
