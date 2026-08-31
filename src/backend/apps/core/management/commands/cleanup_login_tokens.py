"""
Management command to cleanup expired or consumed login tokens.

Deletes login tokens that are expired (expires_at < now()) or consumed over 24 hours ago.
Uses advisory lock 5 for idempotent, safe concurrent execution.
"""

import logging
from datetime import timedelta

from apps.core.enums import AdvisoryLockId
from apps.core.utils.advisory_lock import advisory_lock
from apps.users.models import LoginToken
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Cleanup expired and old consumed login tokens."""

    help = "Delete expired login tokens or consumed tokens older than 24 hours"

    def add_arguments(self, parser) -> None:
        """Add dry-run argument to the command."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            default=False,
            help="Print count of tokens to be deleted without actually deleting",
        )

    def handle(self, *args, **options) -> None:
        """Execute the login token cleanup command with advisory lock."""
        dry_run: bool = options["dry_run"]

        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
            with advisory_lock(AdvisoryLockId.CLEANUP_LOGIN_TOKENS):
                now = timezone.now()
                consumed_cutoff = now - timedelta(hours=24)

                # Query tokens that are either expired or consumed over 24 hours ago
                queryset = LoginToken.objects.filter(
                    expires_at__lt=now,
                ) | LoginToken.objects.filter(
                    consumed_at__isnull=False,
                    consumed_at__lt=consumed_cutoff,
                )

                count = queryset.count()

                if dry_run:
                    logger.info(
                        "DRY RUN: Would delete %d expired or old consumed login tokens",
                        count,
                    )
                    return

                # Delete tokens
                deleted_count, _ = queryset.delete()

                logger.info(
                    "Deleted %d expired or old consumed login tokens",
                    deleted_count,
                )
