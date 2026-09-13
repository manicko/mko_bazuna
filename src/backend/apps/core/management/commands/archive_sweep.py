"""
Management command to archive published ads after 2-month retention.

Transitions ads with PUBLISHED status where published_at is older than 2 months to ARCHIVED status.
Uses advisory lock 1 for idempotent, safe concurrent execution.
"""

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.ads.models import Ad
from apps.core.enums import AdStatus, AdvisoryLockId
from apps.core.utils.advisory_lock import advisory_lock

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Archive published ads after 2-month retention window."""

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
        """Execute the archive sweep command with advisory lock."""
        dry_run: bool = options["dry_run"]

        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
            with advisory_lock(AdvisoryLockId.ARCHIVE_SWEEP):
                # Query using the IX_ads_archive_sweep partial index
                # Status is PUBLISHED, published_at older than 2 months
                cutoff_date = timezone.now() - timedelta(days=60)

                queryset = Ad.objects.filter(
                    status=AdStatus.PUBLISHED,
                    published_at__lt=cutoff_date,
                )

                count = queryset.count()

                if dry_run:
                    logger.info(
                        "DRY RUN: Would archive %d ads with PUBLISHED status older than 2 months",
                        count,
                    )
                    return

                # Deliberate bulk update path (bypasses transition_to() + save()):
                # 1. queryset pre-filtered to PUBLISHED, matching ALLOWED_TRANSITIONS PUBLISHED -> ARCHIVED
                # 2. archived_at set below, satisfying ck_ads_archived_at_if_archived
                # 3. updated_at refreshed here because bulk update() does not call save() and so skips auto_now
                updated_count = queryset.update(
                    status=AdStatus.ARCHIVED,
                    archived_at=timezone.now(),
                    updated_at=timezone.now(),
                )

                logger.info(
                    "Archived %d ads with PUBLISHED status older than 2 months",
                    updated_count,
                )
