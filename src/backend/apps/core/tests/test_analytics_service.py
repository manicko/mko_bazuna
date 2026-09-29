"""
Tests for the ``record_event`` analytics service.

Covers the happy path (event persisted with all fields), the minimal-argument
call (only ``event_type``), the anonymous ``user_id`` case, the failure path
(persistence error is caught, logged at ERROR with traceback, and ``None`` is
returned), and the DB-002 contract: inside a caller-owned transaction a real
server-side FK violation must be contained in ``record_event``'s own savepoint
so the caller's business write still commits.
"""

from __future__ import annotations

import logging

import pytest
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext

from apps.analytics.models import AnalyticsEvent
from apps.core.enums import AdSource, AdStatus, AnalyticsEventType
from apps.core.services.analytics import (
    _ANALYTICS_FK_CONSTRAINTS,
    record_event,
)
from conftest import create_test_ad

User = get_user_model()

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


class TestRecordEventFix:
    """DB-002: ``record_event`` must never abort the caller's transaction.

    Both FKs on ``analytics_events`` are ``DEFERRABLE INITIALLY DEFERRED``, so a
    bare INSERT inside a caller-owned transaction defers the FK check to the
    outermost COMMIT — an exception raised *outside* ``record_event``'s frame,
    where its ``except`` clause cannot catch it, and which discards the caller's
    entire business write. These tests provoke a **real server-side** error and
    assert the caller's write survives.
    """

    _MISSING_USER_ID = 888888888

    @pytest.mark.django_db(transaction=True)
    def test_record_event_rescues_caller_transaction_on_real_fk_violation(
        self,
    ) -> None:
        """A real FK violation inside a caller transaction is contained by
        ``record_event``'s savepoint; the caller's business write still commits."""
        seller = User.objects.create(chat_id=990090101)
        marker = "DB002_SURVIVED"
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE users SET first_name = %s WHERE id = %s",
                [marker, seller.id],
            )

        raised: Exception | None = None
        result: AnalyticsEvent | None = None
        try:
            # A REAL COMMIT boundary (django_db(transaction=True)) — without the
            # fix, the deferred FK violation fires here and the business write is
            # rolled back with it.
            with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE users SET first_name = %s WHERE id = %s",
                        [marker, seller.id],
                    )
                result = record_event(
                    AnalyticsEventType.AD_VIEWED,
                    user_id=self._MISSING_USER_ID,
                )
        except Exception as exc:  # noqa: BLE001
            raised = exc

        assert raised is None, f"caller transaction was aborted: {raised!r}"
        assert result is None
        seller.refresh_from_db()
        assert seller.first_name == marker
        assert (
            AnalyticsEvent.objects.filter(user_id=self._MISSING_USER_ID).count() == 0
        )

    def test_set_constraints_targets_exist(self) -> None:
        """The generated FK constraint names ``record_event`` names in
        ``SET CONSTRAINTS`` must exist on the live schema and be deferrable.

        A migration renaming either column regenerates the hash suffix; this
        fails CI instead of silently turning the check into a no-op.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT conname
                FROM pg_constraint
                WHERE conrelid = 'analytics_events'::regclass
                  AND contype = 'f'
                  AND condeferrable
                  AND condeferred
                """
            )
            live_names = {row[0] for row in cursor.fetchall()}

        assert set(_ANALYTICS_FK_CONSTRAINTS) <= live_names


@pytest.mark.django_db(transaction=True)
class TestRecordEventAutocommitCost:
    """The autocommit branch of ``record_event`` keeps issuing one statement.

    ``transaction=True`` takes the test out of Django's wrapping atomic, so
    ``in_atomic_block`` is ``False`` — exactly the production ``ad_detail``
    state. The assertion filters the captured SQL for transaction-control
    statements instead of counting queries, because a bare query count would pin
    an unrelated line of the view.
    """

    def test_autocommit_branch_issues_no_savepoint_bookkeeping(self) -> None:
        assert not connection.in_atomic_block

        with CaptureQueriesContext(connection) as ctx:
            result = record_event(AnalyticsEventType.SEARCH_PERFORMED)

        assert result is not None
        assert AnalyticsEvent.objects.filter(id=result.id).exists()

        control = [
            q["sql"]
            for q in ctx.captured_queries
            if any(
                token in q["sql"].upper()
                for token in ("SAVEPOINT", "SET CONSTRAINTS", "RELEASE")
            )
        ]
        assert control == []
