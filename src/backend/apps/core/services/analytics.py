"""
Analytics event recording service for Mko Bazuna.

Provides a single best-effort entry point for persisting ``AnalyticsEvent`` rows
from views. Analytics is an **observer, not a participant**: it never decides the
caller's transaction outcome. Recording failures must never break the request
lifecycle, so all persistence errors are caught, logged, and swallowed — and when
a caller-owned transaction is active, any failure is first contained inside a
savepoint that this module owns, leaving the caller's transaction healthy and
usable.
"""

import logging

from django.db import transaction

from apps.analytics.models import AnalyticsEvent
from apps.core.enums import AdSource, AnalyticsEventType

logger = logging.getLogger(__name__)

# Generated FK constraint names on ``analytics_events``, read from the LIVE schema
# (``pg_constraint``), never copied from a report. Both are
# DEFERRABLE INITIALLY DEFERRED, so a bare INSERT inside a caller-owned
# transaction defers the check to the outermost COMMIT. Guarded by
# ``test_analytics_service.py::TestRecordEventFix::test_set_constraints_targets_exist``,
# which fails CI if a migration renames them.
_ANALYTICS_FK_CONSTRAINTS = (
    "analytics_events_user_id_b21e3686_fk_users_id",
    "analytics_events_ad_id_bc186949_fk_ads_id",
)

# Single statement: PostgreSQL 18 accepts a comma-separated constraint list, so
# naming the two constraints costs exactly the same as ``ALL`` while confining
# the retroactive re-validation to this table.
_SET_CONSTRAINTS_SQL = f"SET CONSTRAINTS {', '.join(_ANALYTICS_FK_CONSTRAINTS)} IMMEDIATE"


def record_event(
    event_type: AnalyticsEventType,
    user_id: int | None = None,
    *,
    ad_id: int | None = None,
    source: AdSource | None = None,
) -> AnalyticsEvent | None:
    """Persist an analytics event, never perturbing the caller's transaction.

    Both FKs on ``AnalyticsEvent`` are ``DEFERRABLE INITIALLY DEFERRED``. Inside
    a caller's transaction a bare INSERT therefore succeeds and defers the FK
    check to the **outermost** COMMIT — an exception raised outside this
    function, which the ``except`` below cannot catch, and which discards the
    caller's entire business write. When a caller-owned transaction is active
    this function therefore (a) opens a savepoint it owns and (b) forces the two
    ``analytics_events`` FK checks to run **immediately** inside it. A violation
    then raises here, is rolled back to our savepoint, and is logged — leaving
    the caller's transaction healthy and usable.

    **Removing the ``SET CONSTRAINTS`` statement silently reintroduces the
    COMMIT-time data loss.** The savepoint alone is NOT sufficient: a deferred
    violation is not raised at ``RELEASE SAVEPOINT``, only at the outermost
    COMMIT.

    Scoping notes: the constraint list is **named, not ``ALL``** —
    ``SET CONSTRAINTS ALL IMMEDIATE`` retroactively re-validates *every* pending
    deferred constraint in the caller's transaction, including ones on other
    tables, and can fail a publish for an unrelated dangling FK. The mode change
    is restored by ``ROLLBACK TO SAVEPOINT`` but **not** by ``RELEASE
    SAVEPOINT``, so after a successful call these two FKs stay ``IMMEDIATE`` for
    the rest of the caller's transaction; that is harmless (only this function
    writes the table) and resets at commit.

    In autocommit no savepoint is created: the deferred check already fires
    inside this single statement, so the failure surfaces here and is caught by
    the handler. This keeps the ad-detail render budget (see
    ``test_ad_detail_queries._QUERY_BOUND``) at one statement in production; the
    transactional branch costs three (``SAVEPOINT`` + ``SET CONSTRAINTS`` +
    ``RELEASE SAVEPOINT``) and is reachable only from a caller-owned transaction.

    Args:
        event_type: The analytics event type to record.
        user_id: Optional user ID (nullable FK: buyer may be anonymous,
            seller via ``ad.user_id``).
        ad_id: Optional ad ID (keyword-only, nullable FK for non-ad events).
        source: Optional event origin (keyword-only; ``None`` = production,
            ``"seed"`` = seed-generated).

    Returns:
        The persisted ``AnalyticsEvent`` instance, or ``None`` if recording
        failed.
    """
    connection = transaction.get_connection()

    try:
        if not connection.in_atomic_block:
            # Autocommit: the deferred FK check runs inside this single implicit
            # transaction, so a violation raises here and the handler below
            # catches it. One statement — the ad-detail budget is unaffected.
            return AnalyticsEvent.objects.create(
                event_type=event_type,
                user_id=user_id,
                ad_id=ad_id,
                source=source,
            )

        # Caller owns the transaction. The savepoint is opened BEFORE the failing
        # work so Atomic.__exit__ rolls back to it before the exception reaches
        # the handler; the handler then runs on a healthy transaction.
        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
            with connection.cursor() as cursor:
                cursor.execute(_SET_CONSTRAINTS_SQL)
            return AnalyticsEvent.objects.create(
                event_type=event_type,
                user_id=user_id,
                ad_id=ad_id,
                source=source,
            )
    except Exception:  # noqa: BLE001 — analytics must never break the request
        logger.exception(
            "Failed to record analytics event %s (user_id=%s, ad_id=%s, source=%s)",
            event_type,
            user_id,
            ad_id,
            source,
        )
        return None
