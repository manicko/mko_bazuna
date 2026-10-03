"""
Management command to bound the ``MediaDeletionError`` diagnostic table (07-MEDIA-010).

``delete_photo`` records a row whenever a storage-key deletion exhausts all
retries. The table is a diagnostic aid, not a durable ledger, so it is bounded
by a retention window: rows older than ``--older-than`` days (30 by default) are
**deleted**. The purge is **IRREVERSIBLE** — a revert of this command does not
restore purged rows — so ``--dry-run`` is the mandatory first run.

The predicate filters on ``created_at``, which carries ``idx_media_del_err_created``,
so this is an index range scan rather than the sequential scan an unbounded
table would force. ``error_type`` is likewise indexed for the admin reader.

Uses advisory lock 15 (``AdvisoryLockId.PURGE_MEDIA_DELETION_ERRORS``) for
idempotent, safe concurrent execution. Batching is deliberately off: the table
is small by construction and the sweep is a single indexed ``DELETE``.
"""

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.core.enums import AdvisoryLockId
from apps.core.utils.advisory_lock import advisory_lock
from apps.media.models import MediaDeletionError

logger = logging.getLogger(__name__)

#: Default retention window in days. Both columns the predicate touches are
#: already indexed (idx_media_del_err_created / idx_media_del_err_type), so the
#: eligible-set lookup is an index scan, not a sequential scan.
_RETENTION_DAYS = 30


class Command(BaseCommand):
    """Delete MediaDeletionError rows older than the retention window."""

    help = "Delete recorded media deletion failures older than N days (default 30)"

    def add_arguments(self, parser) -> None:
        """Add the retention window (DAYS) and the non-destructive mode."""
        parser.add_argument(
            "--older-than",
            type=int,
            default=_RETENTION_DAYS,
            help="Retention window in days (default: %(default)s)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            default=False,
            help="Report the count that would be deleted without deleting",
        )

    def handle(self, *args, **options) -> None:
        """Purge aged MediaDeletionError rows under the retention lock."""
        older_than: int = options["older_than"]
        dry_run: bool = options["dry_run"]

        if older_than < 1:
            raise CommandError(
                f"--older-than must be at least 1 day; got {older_than}. "
                "A non-positive window would delete every row, including "
                "one written a second ago."
            )

        cutoff = timezone.now() - timedelta(days=older_than)

        # The lock is taken inside the transaction and BEFORE the --dry-run
        # branch, so two schedulers never race even a report. One DELETE, no
        # batching or keyset pagination: the predicate is a single indexed range.
        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
            with advisory_lock(AdvisoryLockId.PURGE_MEDIA_DELETION_ERRORS):
                eligible = MediaDeletionError.objects.filter(created_at__lt=cutoff)

                if dry_run:
                    count = eligible.count()
                    logger.info(
                        "DRY RUN: would delete %d rows older than %d days",
                        count,
                        older_than,
                    )
                    self.stdout.write(
                        self.style.WARNING(
                            f"DRY RUN: {count} deletion-error rows would be deleted."
                        )
                    )
                    return

                deleted_count, _per_model = eligible.delete()
                logger.info(
                    "Purged %d deletion-error rows older than %d days",
                    deleted_count,
                    older_than,
                )

        self.stdout.write(
            self.style.SUCCESS(f"Purged {deleted_count} deletion-error rows.")
        )
