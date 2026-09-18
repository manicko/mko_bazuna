"""
Split from test_sweep_commands.py: Tests for the archive_sweep command.

Archive sweep moves ads older than 60 days from PUBLISHED to ARCHIVED status,
guarded by an advisory lock (lock id 1).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.ads.models import Ad
from apps.core.enums import AdStatus, AdvisoryLockId
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


class TestArchiveSweep:
    """Tests for archive_sweep command (advisory lock 1, 60-day window)."""

    def test_dry_run_does_not_mutate(self, seller, category, city):

        stale = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.PUBLISHED,
            published_at=timezone.now() - timedelta(days=90),
        )
        call_command("archive_sweep", "--dry-run")
        stale.refresh_from_db()
        assert stale.status == AdStatus.PUBLISHED

    def test_archives_published_older_than_60_days(self, seller, category, city):

        stale = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.PUBLISHED,
            published_at=timezone.now() - timedelta(days=90),
        )
        fresh = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.PUBLISHED,
            published_at=timezone.now() - timedelta(days=10),
        )
        call_command("archive_sweep")
        stale.refresh_from_db()
        fresh.refresh_from_db()
        assert stale.status == AdStatus.ARCHIVED
        assert stale.archived_at is not None
        assert fresh.status == AdStatus.PUBLISHED

    def test_idempotent_on_rerun(self, seller, category, city):

        stale = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.PUBLISHED,
            published_at=timezone.now() - timedelta(days=90),
        )
        call_command("archive_sweep")
        stale.refresh_from_db()
        assert stale.status == AdStatus.ARCHIVED
        # Re-running should not error and count should be zero.
        call_command("archive_sweep")
        assert Ad.objects.filter(status=AdStatus.ARCHIVED).count() == 1

    def test_lock_id_is_archive_sweep(self):
        assert AdvisoryLockId.ARCHIVE_SWEEP == 1
