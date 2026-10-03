"""Tests for the ``purge_media_deletion_errors`` retention command (07-MEDIA-010).

``MediaDeletionError.created_at`` is ``auto_now_add=True``, so passing it to
``objects.create()`` is silently ignored. ``_aged_row`` therefore forces the
timestamp with an ``UPDATE`` afterwards; without that every row reads as "now",
nothing is ever past the TTL, and every delete assertion passes vacuously.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.media.models import MediaDeletionError
from apps.media.services.filesystem import DELETE_PHOTO_MAX_ATTEMPTS

pytestmark = [pytest.mark.django_db]


def _aged_row(*, age_days: int, **overrides) -> MediaDeletionError:
    """Create a row whose ``created_at`` is *age_days* in the past.

    ``created_at`` is ``auto_now_add=True``, so passing it to ``create()`` is
    SILENTLY IGNORED — the argument must be forced with an ``UPDATE``
    afterwards, or every row reads as "now" and the delete assertions pass
    vacuously.
    """
    fields = {
        "storage_key": f"{uuid4()}.jpg",
        "error_type": "PermissionError",
        "error_message": "denied by the filesystem",
        "attempts": DELETE_PHOTO_MAX_ATTEMPTS,
    }
    fields.update(overrides)
    row = MediaDeletionError.objects.create(**fields)
    MediaDeletionError.objects.filter(pk=row.pk).update(
        created_at=timezone.now() - timedelta(days=age_days)
    )
    row.refresh_from_db()
    return row


class TestPurgeMediaDeletionErrors:
    """Retention semantics of ``purge_media_deletion_errors``."""

    def test_dry_run_deletes_nothing(self) -> None:
        """--dry-run reports the eligible count and removes no row."""
        stale = _aged_row(age_days=40)
        fresh = _aged_row(age_days=1)

        call_command("purge_media_deletion_errors", "--dry-run")

        assert MediaDeletionError.objects.filter(pk=stale.pk).exists()
        assert MediaDeletionError.objects.filter(pk=fresh.pk).exists()
        assert MediaDeletionError.objects.count() == 2

    def test_row_inside_ttl_survives_with_message_intact(self) -> None:
        """A row inside the 30-day window survives with every field unchanged."""
        row = _aged_row(age_days=29, error_message="distinct message body")

        call_command("purge_media_deletion_errors")

        row.refresh_from_db()
        assert row.error_message == "distinct message body"
        assert row.attempts == DELETE_PHOTO_MAX_ATTEMPTS
        assert row.error_type == "PermissionError"
        assert MediaDeletionError.objects.filter(pk=row.pk).exists()

    def test_row_past_ttl_is_deleted(self) -> None:
        """A row past the 30-day window is removed by the default run."""
        row = _aged_row(age_days=31)

        call_command("purge_media_deletion_errors")

        assert not MediaDeletionError.objects.filter(pk=row.pk).exists()

    def test_default_retention_window_is_30_days(self) -> None:
        """The default window is 30 days, proven by behaviour with no flag."""
        inside = _aged_row(age_days=29)
        outside = _aged_row(age_days=31)

        call_command("purge_media_deletion_errors")

        assert MediaDeletionError.objects.filter(pk=inside.pk).exists()
        assert not MediaDeletionError.objects.filter(pk=outside.pk).exists()

    def test_second_run_is_a_no_op(self) -> None:
        """A second run deletes nothing and leaves the table count unchanged."""
        _aged_row(age_days=31)

        call_command("purge_media_deletion_errors")
        assert MediaDeletionError.objects.count() == 0

        call_command("purge_media_deletion_errors")
        assert MediaDeletionError.objects.count() == 0

    @pytest.mark.parametrize("older_than", [0, -1])
    def test_older_than_must_be_at_least_one_day(self, older_than: int) -> None:
        """A non-positive window raises CommandError and deletes nothing."""
        row = _aged_row(age_days=1)

        with pytest.raises(CommandError):
            call_command(
                "purge_media_deletion_errors", older_than=older_than
            )

        assert MediaDeletionError.objects.filter(pk=row.pk).exists()

    def test_command_exits_zero_on_an_empty_table(self) -> None:
        """An empty table is a clean no-op, not an error.

        This is the state the lock-structure spy runs the command in: the real
        body executes with advisory_lock replaced by a no-op, and a non-zero
        exit would age the scheduler liveness marker into ``unhealthy``.
        """
        assert MediaDeletionError.objects.count() == 0

        call_command("purge_media_deletion_errors")

        assert MediaDeletionError.objects.count() == 0

    def test_explicit_older_than_overrides_the_default(self) -> None:
        """--older-than widens the window: a 10-day row survives a 20-day TTL."""
        row = _aged_row(age_days=10)

        call_command("purge_media_deletion_errors", older_than=20)

        assert MediaDeletionError.objects.filter(pk=row.pk).exists()
