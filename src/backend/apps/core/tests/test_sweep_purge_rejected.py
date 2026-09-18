"""
Split from test_sweep_commands.py: Tests for the purge_rejected_ads command.

Purge rejected ads deletes ads in REJECTED status older than 90 days,
guarded by an advisory lock (lock id 7).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.ads.models import Ad, AdImage
from apps.core.enums import AdStatus, AdvisoryLockId, ModeratorActionType
from apps.moderation.models import ModeratorActionLog
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestPurgeRejectedAds:
    """Tests for purge_rejected_ads command (advisory lock 7, 90-day window)."""

    def test_dry_run_does_not_delete(self, seller, category, city):

        old = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.REJECTED,
            rejected_at=timezone.now() - timedelta(days=120),
        )
        call_command("purge_rejected_ads", "--dry-run")
        assert Ad.objects.filter(pk=old.pk).exists()

    def test_purges_rejected_ads_older_than_90_days(self, seller, category, city):

        old = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.REJECTED,
            rejected_at=timezone.now() - timedelta(days=120),
        )
        recent = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.REJECTED,
            rejected_at=timezone.now() - timedelta(days=30),
        )
        call_command("purge_rejected_ads")
        assert not Ad.objects.filter(pk=old.pk).exists()
        assert Ad.objects.filter(pk=recent.pk).exists()

    def test_preserves_moderation_log_with_ad_set_null(self, seller, category, city):

        old = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.REJECTED,
            rejected_at=timezone.now() - timedelta(days=120),
        )
        log = ModeratorActionLog.objects.create(
            ad=old,
            user=seller,
            action_type=ModeratorActionType.REJECT,
            reason="internal",
        )
        call_command("purge_rejected_ads")
        log.refresh_from_db()
        assert ModeratorActionLog.objects.filter(pk=log.pk).exists()
        assert log.ad_id is None

    def test_collects_thumbnail_keys_for_media_cleanup(
        self, seller, category, city, monkeypatch
    ):
        """Purge rejected ads passes all storage keys (image + thumbnails) to delete_photo.

        Verifies PC-004: the sweep uses AdImage.storage_keys() so thumbnail
        derivatives are not orphaned on disk alongside the main image.
        """
        ad = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.REJECTED,
            rejected_at=timezone.now() - timedelta(days=120),
        )
        img = AdImage.objects.create(
            ad=ad,
            image="test-uuid-purge-rejected.jpg",
            thumbnail_small="test-uuid-purge-rejected-small.jpg",
            thumbnail_medium="test-uuid-purge-rejected-medium.jpg",
            thumbnail_large="test-uuid-purge-rejected-large.jpg",
        )

        deleted_keys: list[str] = []

        def _record(storage_key: str) -> None:
            deleted_keys.append(storage_key)

        monkeypatch.setattr(
            "apps.core.management.commands.purge_rejected_ads.delete_photo",
            _record,
        )

        call_command("purge_rejected_ads")

        expected = img.storage_keys()
        assert sorted(deleted_keys) == sorted(expected)
        assert not Ad.objects.filter(pk=ad.pk).exists()

    def test_lock_id_is_purge_rejected_ads(self):
        assert AdvisoryLockId.PURGE_REJECTED_ADS == 7
