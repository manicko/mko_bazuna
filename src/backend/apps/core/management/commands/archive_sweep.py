"""
Management command to archive published ads after the retention window.

Transitions ads with PUBLISHED status whose ``published_at`` is older than
``_RETENTION_DAYS`` to ARCHIVED status, committing one batch at a time so row
locks are released as the sweep progresses (finding 03-DB-008). Uses advisory
lock 1, held session-scoped for the whole sweep.
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.ads.models import Ad
from apps.core.enums import AdStatus, AdvisoryLockId
from apps.core.utils.advisory_lock import advisory_lock

logger = logging.getLogger(__name__)

_RETENTION_DAYS = 60
_BATCH_SIZE = 500


@dataclass(frozen=True)
class _Cursor:
    """Position of the last row of the previous batch.

    Both fields are needed: ``published_at`` is not unique, so ``pk`` is the
    tiebreaker and the cursor must be compared as the tuple
    ``(published_at, pk)``.
    """

    published_at: datetime
    pk: int


class Command(BaseCommand):
    """Archive published ads after the retention window."""

    help = "Archive ads with PUBLISHED status older than 2 months"

    def add_arguments(self, parser) -> None:
        """Add dry-run argument to the command."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            default=False,
            help="Print count of ads to be archived without actually archiving",
        )

    def handle(self, *args, **options) -> None:
        """Execute the archive sweep, one committed batch at a time.

        Why there is no enclosing ``transaction.atomic()`` here. The advisory
        lock is **session-scoped** (``pg_advisory_lock``) precisely because the
        batches below each commit. A transaction-scoped lock would be released
        by the first batch ``COMMIT`` and lose mutual exclusion between
        concurrent runs. Because the lock is session-scoped, ``handle`` must
        **not** wrap the loop in ``transaction.atomic()``: doing so would turn
        each per-batch ``atomic()`` into a **savepoint**, so nothing would ever
        commit and the whole sweep would hold every row lock for its full
        duration again — the exact defect 03-DB-008 fixes. Two tests guard this:
        ``test_batches_commit_independently`` (behavioural) and
        ``test_sweep_lock_structure`` (lock scope).
        """
        dry_run: bool = options["dry_run"]

        # Frozen ONCE, above the loop and above the lock.  A per-batch cutoff
        # would let a row cross INTO the eligible set behind the cursor and be
        # skipped for the whole run: only a frozen cutoff makes the eligible set
        # monotonically shrink, so a row can never enter behind the cursor.
        cutoff_date = timezone.now() - timedelta(days=_RETENTION_DAYS)

        with advisory_lock(AdvisoryLockId.ARCHIVE_SWEEP, session=True):
            if dry_run:
                # No row locks: count() is issued on a queryset WITHOUT
                # select_for_update() and mutates nothing.
                count = Ad.objects.filter(
                    status=AdStatus.PUBLISHED, published_at__lt=cutoff_date
                ).count()
                logger.info(
                    "DRY RUN: Would archive %d ads older than %d days",
                    count,
                    _RETENTION_DAYS,
                )
                return

            archived = 0
            batches = 0
            cursor: _Cursor | None = None
            try:
                while True:
                    started = time.monotonic()
                    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
                        ads = list(
                            self._batch(cutoff_date, cursor).select_for_update()
                        )
                        if not ads:
                            break
                        for ad in ads:
                            ad.transition_to(AdStatus.ARCHIVED)
                            archived += 1
                        last = ads[-1]
                        cursor = _Cursor(
                            published_at=last.published_at, pk=last.pk
                        )
                    batches += 1
                    logger.info(
                        "archive_sweep batch %d: archived %d ad(s), "
                        "cursor=(published_at=%s, pk=%s), hold_ms=%d",
                        batches,
                        len(ads),
                        cursor.published_at,
                        cursor.pk,
                        round((time.monotonic() - started) * 1000),
                    )
            except Exception:
                cursor_at = cursor.published_at if cursor is not None else None
                cursor_pk = cursor.pk if cursor is not None else None
                logger.exception(
                    "archive_sweep aborted at batch %d (cursor published_at=%s "
                    "pk=%s); %d ad(s) in the completed batches are ALREADY "
                    "COMMITTED; the next hourly tick re-derives the set from "
                    "scratch and finishes the work",
                    batches + 1,
                    cursor_at,
                    cursor_pk,
                    archived,
                )
                raise

        # AFTER the lock is released — the commit has happened by now.
        logger.info(
            "Archived %d ads across %d batch(es) older than %d days",
            archived,
            batches,
            _RETENTION_DAYS,
        )

    def _batch(self, cutoff_date: datetime, cursor: _Cursor | None) -> QuerySet[Ad]:
        """The keyset window for the next batch.

        ``published_at`` is the batch key because it is the only key PostgreSQL
        can turn into an ``Index Cond`` on ``IX_ads_archive_sweep``. A ``pk``
        keyset leaves the plan to the planner, which can choose
        ``Bitmap Heap Scan + Sort (id)`` with the pk window as a **post-scan
        Filter** — re-reading and re-sorting the whole stale set once per batch.
        The ``pk`` tiebreaker is required because ``published_at`` is not unique.

        The slice is applied here; ``select_for_update()`` is applied by the
        caller **to this already-sliced queryset**, and that queryset is
        evaluated inside the per-batch ``atomic()``.
        """
        window = (
            Q()
            if cursor is None
            else Q(published_at__gt=cursor.published_at)
            | Q(published_at=cursor.published_at, pk__gt=cursor.pk)
        )
        return (
            Ad.objects.filter(
                status=AdStatus.PUBLISHED, published_at__lt=cutoff_date
            )
            .filter(window)
            .order_by("published_at", "pk")[:_BATCH_SIZE]
        )
