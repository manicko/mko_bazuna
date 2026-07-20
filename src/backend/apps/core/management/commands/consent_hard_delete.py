"""
Management command to hard-delete users who revoked consent after 30-day grace period.

Permanently erases user data and deletes ads+images.
Sets NULL on AnalyticsEvent.user and ModeratorActionLog.user to preserve histories.
Uses advisory lock 3 for idempotent, safe concurrent execution.
"""

import logging
from datetime import timedelta

from apps.analytics.models import AnalyticsEvent
from apps.core.enums import AdvisoryLockId
from apps.core.utils.advisory_lock import advisory_lock
from apps.moderation.models import ModeratorActionLog
from apps.users.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Hard-delete users who revoked consent after 30-day grace period."""

    help = "Hard-delete users with consent revoked more than 30 days ago"

    def add_arguments(self, parser) -> None:
        """Add dry-run argument to the command."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            default=False,
            help="Print count of users to be hard-deleted without actually deleting",
        )

    def handle(self, *args, **options) -> None:
        """Execute the consent hard-delete command with advisory lock."""
        dry_run: bool = options["dry_run"]

        with advisory_lock(AdvisoryLockId.CONSENT_HARD_DELETE):
            # Query using the IX_users_erasure_sweep index
            # consent_revoked_at is not null and older than 30 days
            cutoff_date = timezone.now() - timedelta(days=30)

            queryset = User.objects.filter(
                consent_revoked_at__isnull=False,
                consent_revoked_at__lt=cutoff_date,
            )

            count = queryset.count()

            if dry_run:
                logger.info(
                    "DRY RUN: Would hard-delete %d users with consent revoked over 30 days ago",
                    count,
                )
                return

            # Collect user IDs for logging before processing
            user_ids = list(queryset.values_list("id", flat=True))

            with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
                # Null out analytics_events.user_id (preserves aggregate history)
                AnalyticsEvent.objects.filter(user_id__in=user_ids).update(user_id=None)

                # Null out moderation_action_logs.user_id (preserves history)
                ModeratorActionLog.objects.filter(user_id__in=user_ids).update(user_id=None)

                # Delete users - CASCADE will handle their ads (and ad_images via ORM)
                deleted_count, _ = queryset.delete()

            logger.info(
                "Hard-deleted %d users with consent revoked over 30 days ago",
                deleted_count,
            )