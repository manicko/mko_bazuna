"""
Tests for the ``record_event`` analytics service.

Covers the happy path (event persisted with all fields), the minimal-argument
call (only ``event_type``), the anonymous ``user_id`` case, and the failure
path (persistence error is caught, logged at ERROR with traceback, and
``None`` is returned).
"""

from __future__ import annotations

import logging

import pytest
from django.db import transaction

from apps.analytics.models import AnalyticsEvent
from apps.core.enums import AdSource, AdStatus, AnalyticsEventType
from apps.core.services.analytics import record_event
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestRecordEvent:
    """Tests for ``record_event`` success and failure paths."""

    def test_record_event_creates_row_with_all_fields(
        self, seller, category, city
    ) -> None:
        """All four arguments map to the corresponding model fields."""
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)

        result = record_event(
            AnalyticsEventType.AD_VIEWED,
            user_id=seller.id,
            ad_id=ad.id,
            source=AdSource.TELEGRAM,
        )

        assert result is not None
        assert isinstance(result, AnalyticsEvent)
        event = AnalyticsEvent.objects.get(id=result.id)
        assert event.event_type == AnalyticsEventType.AD_VIEWED
        assert event.user_id == seller.id
        assert event.ad_id == ad.id
        assert event.source == AdSource.TELEGRAM

    def test_record_event_minimal_call(self) -> None:
        """Only ``event_type`` is required; nullable fields default to None."""
        result = record_event(AnalyticsEventType.SEARCH_PERFORMED)

        assert result is not None
        event = AnalyticsEvent.objects.get(id=result.id)
        assert event.event_type == AnalyticsEventType.SEARCH_PERFORMED
        assert event.user_id is None
        assert event.ad_id is None
        assert event.source is None

    def test_record_event_anonymous_user(self, seller, category, city) -> None:
        """Anonymous search event records with user_id = None and a valid ad_id."""
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)

        result = record_event(
            AnalyticsEventType.SEARCH_PERFORMED,
            user_id=None,
            ad_id=ad.id,
        )

        assert result is not None
        event = AnalyticsEvent.objects.get(id=result.id)
        assert event.user_id is None
        assert event.ad_id == ad.id

    def test_record_event_failure_returns_none_and_logs(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A persistence error is caught, logged at ERROR with traceback, and
        ``None`` is returned (analytics must never break the request)."""

        def _raise(*args: object, **kwargs: object) -> AnalyticsEvent:
            raise RuntimeError("DB on fire")

        monkeypatch.setattr(AnalyticsEvent.objects, "create", _raise)

        with caplog.at_level(logging.ERROR, logger="apps.core.services.analytics"):
            result = record_event(
                AnalyticsEventType.AD_VIEWED,
                user_id=1,
                ad_id=2,
                source=AdSource.TELEGRAM,
            )

        assert result is None
        assert "Failed to record analytics event" in caplog.text
        assert "RuntimeError" in caplog.text
        # No event should have been persisted.
        assert AnalyticsEvent.objects.count() == 0

    def test_record_event_inside_rollback_not_persisted(self) -> None:
        """``record_event`` is transaction-transparent: an event created inside an
        ``atomic()`` block that is rolled back must NOT be committed."""

        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
            record_event(AnalyticsEventType.SEARCH_PERFORMED)
            transaction.set_rollback(True)

        assert AnalyticsEvent.objects.count() == 0

    def test_record_event_inside_commit_persisted(self) -> None:
        """``record_event`` created inside an ``atomic()`` block with no rollback
        must be committed within the atomic scope."""

        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
            record_event(AnalyticsEventType.SEARCH_PERFORMED)

        assert AnalyticsEvent.objects.count() == 1
