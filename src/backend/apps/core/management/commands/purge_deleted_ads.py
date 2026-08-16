"""
Management command to purge soft-deleted ads after 4-month retention.

Deletes ads with DELETED status where deleted_at is older than 120 days.
Uses advisory lock 11 (PURGE_DELETED_ADS) for idempotent, safe concurrent execution.
Photo files are deleted after the transaction commits.
"""

import logging
from datetime import timedelta

from apps.ads.models import Ad
from apps.core.enums import AdStatus, AdvisoryLockId
from apps.core.utils.advisory_lock import advisory_lock
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction

from apps.ads.models import AdImage
from telegram_bot.services.media import delete_photo

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Purge soft-deleted ads after 4-month retention window."""

    help = "Purge ads with DELETED status older than 120 days"

    def add_arguments(self, parser) -> None:
        """Add dry-run argument to the command."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            default=False,
            help="Print count of ads to be deleted without actually deleting",
        )

    def handle(self, *args, **options) -> None:
        """Execute the purge command with advisory lock."""
        dry_run: bool = options["dry_run"]

        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
            with advisory_lock(AdvisoryLockId.PURGE_DELETED_ADS):
                # Query using the IX_ads_purge_deleted partial index
                # Status is DELETED, deleted_at older than 120 days (4 months)
                cutoff_date = timezone.now() - timedelta(days=120)

                queryset = Ad.objects.filter(
                    status=AdStatus.DELETED,
                    deleted_at__lt=cutoff_date,
                )

                count = queryset.count()

                if dry_run:
                    logger.info(
                        "DRY RUN: Would delete %d ads with DELETED status older than 120 days",
                        count,
                    )
                    return

                # Collect storage keys for physical media cleanup before ORM cascade
                ad_ids = list(queryset.values_list("id", flat=True))
                storage_keys = list(
                    AdImage.objects.filter(ad_id__in=ad_ids).values_list(
                        "image", flat=True
                    )
                )

                # Delete atomically - CASCADE will handle ad_images
                deleted_count, _ = queryset.delete()

        # Delete physical media after the transaction commits. Filesystem
        # deletions inside transaction.atomic() cannot be rolled back, so a DB
        # rollback would orphan DB rows pointing to already-deleted files.
        for storage_key in storage_keys:
            delete_photo(storage_key)

        logger.info(
            "Deleted %d ads with DELETED status older than 120 days. "
            "Removed %d media files.",
            deleted_count,
            len(storage_keys),
        )
