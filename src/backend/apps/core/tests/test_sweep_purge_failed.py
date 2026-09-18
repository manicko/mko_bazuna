"""
Split from test_sweep_commands.py: Tests for the purge_failed_ads command.

Purge failed ads deletes ads in ON_MODERATION_FAILED status older than 7 days,
guarded by an advisory lock (lock id 6).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.ads.models import Ad, AdImage
from apps.core.enums import AdStatus, AdvisoryLockId
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


class TestPurgeFailedAds:
    """Tests for purge_failed_ads command (advisory lock 6, 7-day window)."""

    def test_dry_run_does_not_delete(self, seller, category, city):

        old = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.ON_MODERATION_FAILED,
            moderation_failed_at=timezone.now() - timedelta(days=10),
        )
        call_command("purge_failed_ads", "--dry-run")
        assert Ad.objects.filter(pk=old.pk).exists()

    def test_purges_failed_ads_older_than_7_days(self, seller, category, city):

        old = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.ON_MODERATION_FAILED,
            moderation_failed_at=timezone.now() - timedelta(days=10),
        )
        recent = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.ON_MODERATION_FAILED,
            moderation_failed_at=timezone.now() - timedelta(days=2),
        )
        call_command("purge_failed_ads")
        assert not Ad.objects.filter(pk=old.pk).exists()
        assert Ad.objects.filter(pk=recent.pk).exists()

    def test_does_not_purge_other_statuses(self, seller, category, city):

        rejected = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.REJECTED,
            rejected_at=timezone.now() - timedelta(days=200),
        )
        call_command("purge_failed_ads")
        assert Ad.objects.filter(pk=rejected.pk).exists()

    def test_collects_thumbnail_keys_for_media_cleanup(
        self, seller, category, city, monkeypatch
    ):
        """Purge failed ads passes all storage keys (image + thumbnails) to delete_photo.

        Verifies PC-004: the sweep uses AdImage.storage_keys() so thumbnail
        derivatives are not orphaned on disk alongside the main image.
        """
        ad = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.ON_MODERATION_FAILED,
            moderation_failed_at=timezone.now() - timedelta(days=10),
        )
        img = AdImage.objects.create(
            ad=ad,
            image="test-uuid-purge-failed.jpg",
            thumbnail_small="test-uuid-purge-failed-small.jpg",
            thumbnail_medium="test-uuid-purge-failed-medium.jpg",
            thumbnail_large="test-uuid-purge-failed-large.jpg",
        )

        deleted_keys: list[str] = []

        def _record(storage_key: str) -> None:
            deleted_keys.append(storage_key)

        monkeypatch.setattr(
            "apps.core.management.commands.purge_failed_ads.delete_photo",
            _record,
        )

        call_command("purge_failed_ads")

        expected = img.storage_keys()
        assert sorted(deleted_keys) == sorted(expected)
        assert not Ad.objects.filter(pk=ad.pk).exists()

    def test_lock_id_is_purge_failed_ads(self):
        assert AdvisoryLockId.PURGE_FAILED_ADS == 6
