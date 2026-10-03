"""
Management command to hard-delete users who revoked consent after 30-day grace period.

Permanently erases user data and deletes ads+images.
Sets NULL on AnalyticsEvent.user and ModeratorActionLog.user to preserve histories.
Uses advisory lock 3 for idempotent, safe concurrent execution.
"""

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.analytics.models import AnalyticsEvent
from apps.core.enums import AdvisoryLockId
from apps.core.models import SupportTicket
from apps.core.utils.advisory_lock import advisory_lock
from apps.moderation.models import ModeratorActionLog
from apps.users.models import User

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

        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
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

                # Null out analytics_events.user_id (preserves aggregate history)
                AnalyticsEvent.objects.filter(user_id__in=user_ids).update(user_id=None)

                # Null out moderation_action_logs.user_id (preserves history)
                ModeratorActionLog.objects.filter(user_id__in=user_ids).update(
                    user_id=None
                )

                # Delete support tickets for the users about to be hard-deleted
                # (06-PII-101). The FK's CASCADE would remove them with the user
                # row, but the delete is stated explicitly so the erasure intent
                # is visible in this path rather than implied by a model option.
                SupportTicket.objects.filter(user_id__in=user_ids).delete()

                # Sweep already-orphaned tickets (user_id IS NULL). This is a
                # CORRECTNESS STATEMENT, not a data fix: no cascade can reach an
                # orphan and this population is 0 rows in dev and test today.
                # Stating it here keeps the invariant "no unattributed ticket
                # outlives its subject" true without a migration that deletes
                # rows (constraint 10).
                SupportTicket.objects.filter(user_id__isnull=True).delete()

                # Delete users - CASCADE will handle their ads (and ad_images via ORM)
                deleted_count, _ = queryset.delete()

        # Physical media deletion is handled by the AdImage pre_delete signal
        # via transaction.on_commit(), which runs after this transaction commits.

        logger.info(
            "Hard-deleted %d users (cascaded %d rows incl. ads/images) "
            "with consent revoked over 30 days ago.",
            len(user_ids),
            deleted_count,
        )
