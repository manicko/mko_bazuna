"""
Management command to sweep draft ads after 30-minute retention.

Deletes ads with DRAFT status whose ``updated_at`` is older than 30 minutes —
i.e. with no seller activity. ``updated_at`` is kept fresh by the bot's dialog
heartbeat (``telegram_bot.services.ad_data.orm.touch_draft``); do not filter on
``created_at`` (finding 03-DB-003).
Uses advisory lock 4 for idempotent, safe concurrent execution.
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
    """Sweep draft ads after 30-minute retention window."""

    help = "Delete ads with DRAFT status and no seller activity for 30 minutes"

    def add_arguments(self, parser) -> None:
        """Add dry-run argument to the command."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            default=False,
            help="Print count of draft ads to be deleted without actually deleting",
        )

    def handle(self, *args, **options) -> None:
        """Execute the draft sweep command with advisory lock."""
        dry_run: bool = options["dry_run"]

        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
            with advisory_lock(AdvisoryLockId.SWEEP_DRAFTS):
                # Query draft ads with no seller activity for 30 minutes
                cutoff_date = timezone.now() - timedelta(minutes=30)

                queryset = Ad.objects.filter(
                    status=AdStatus.DRAFT,
                    updated_at__lt=cutoff_date,
                )

                count = queryset.count()

                if dry_run:
                    logger.info(
                        "DRY RUN: Would delete %d draft ads with no seller activity for 30 minutes",
                        count,
                    )
                    return

                # Delete atomically - CASCADE will handle ad_images
                deleted_count, _ = queryset.delete()

        # Physical media deletion is handled by the AdImage pre_delete signal
        # via transaction.on_commit(), which runs after this transaction commits.

        logger.info(
            "Deleted %d draft ads with no seller activity for 30 minutes.",
            deleted_count,
        )
