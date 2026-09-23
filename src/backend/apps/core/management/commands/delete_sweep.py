"""
Management command to delete archived ads after 60-day retention.

Deletes ads with ARCHIVED status where archived_at is older than 60 days.
Uses advisory lock 2 for idempotent, safe concurrent execution.
Images are CASCADE-deleted via ORM.
"""

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.ads.models import Ad, AdImage
from apps.core.enums import AdStatus, AdvisoryLockId
from apps.core.utils.advisory_lock import advisory_lock

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Delete archived ads after 60-day retention window."""

    help = "Delete ads with ARCHIVED status older than 60 days"

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
        """Execute the delete sweep command with advisory lock."""
        dry_run: bool = options["dry_run"]

        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
            with advisory_lock(AdvisoryLockId.DELETE_SWEEP):
                # Query using the IX_ads_delete_sweep partial index
                # Status is ARCHIVED, archived_at older than 60 days
                cutoff_date = timezone.now() - timedelta(days=60)

                queryset = Ad.objects.filter(
                    status=AdStatus.ARCHIVED,
                    archived_at__lt=cutoff_date,
                )

                count = queryset.count()

                if dry_run:
                    logger.info(
                        "DRY RUN: Would delete %d ads with ARCHIVED status older than 60 days",
                        count,
                    )
                    return

                # Collect storage keys for physical media cleanup before ORM cascade
                ad_ids = list(queryset.values_list("id", flat=True))
                storage_keys = [
                    key
                    for img in AdImage.objects.filter(ad_id__in=ad_ids)
                    for key in img.storage_keys()
                ]

                # Delete atomically - CASCADE will handle ad_images
                deleted_count, _ = queryset.delete()

        # Physical media deletion is handled by the AdImage pre_delete signal
        # via transaction.on_commit(), which runs after this transaction commits.

        logger.info(
            "Deleted %d ads with ARCHIVED status older than 60 days. "
            "Removed %d media files.",
            deleted_count,
            len(storage_keys),
        )
