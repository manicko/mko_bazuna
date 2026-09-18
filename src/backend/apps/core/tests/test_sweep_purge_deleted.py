"""
Split from test_sweep_commands.py: Tests for the purge_deleted_ads command.

Purge deleted ads deletes ads in DELETED status older than 120 days,
guarded by an advisory lock (lock id 11).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.ads.models import Ad, AdImage
from apps.core.enums import AdStatus, AdvisoryLockId
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestPurgeDeletedAds:
    """Tests for purge_deleted_ads command (advisory lock 11, 120-day window)."""

    def test_purge_deleted_ads_deletes_old_deleted(self, seller, category, city):

        old = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.DELETED,
            deleted_at=timezone.now() - timedelta(days=200),
        )
        call_command("purge_deleted_ads")
        assert not Ad.objects.filter(pk=old.pk).exists()

    def test_purge_deleted_ads_preserves_recent(self, seller, category, city):

        recent = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.DELETED,
            deleted_at=timezone.now() - timedelta(days=30),
        )
        call_command("purge_deleted_ads")
        assert Ad.objects.filter(pk=recent.pk).exists()

    def test_purge_deleted_ads_skips_non_deleted(self, seller, category, city):

        published = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.PUBLISHED,
            deleted_at=timezone.now() - timedelta(days=200),
        )
        call_command("purge_deleted_ads")
        assert Ad.objects.filter(pk=published.pk).exists()

    def test_purge_deleted_ads_advisory_lock(self):
        assert AdvisoryLockId.PURGE_DELETED_ADS == 11

    def test_purge_deleted_ads_dry_run(self, seller, category, city):

        old = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.DELETED,
            deleted_at=timezone.now() - timedelta(days=200),
        )
        call_command("purge_deleted_ads", "--dry-run")
        assert Ad.objects.filter(pk=old.pk).exists()

    def test_purge_deleted_ads_media_cleanup(self, seller, category, city, monkeypatch):

        old = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.DELETED,
            deleted_at=timezone.now() - timedelta(days=200),
        )
        AdImage.objects.create(ad=old, image="test-uuid-deleted.jpg")

        deleted_keys: list[str] = []

        def _record(storage_key: str) -> None:
            deleted_keys.append(storage_key)

        monkeypatch.setattr(
            "apps.core.management.commands.purge_deleted_ads.delete_photo",
            _record,
        )

        call_command("purge_deleted_ads")

        assert "test-uuid-deleted.jpg" in deleted_keys
        assert not Ad.objects.filter(pk=old.pk).exists()

    def test_collects_thumbnail_keys_for_media_cleanup(
        self, seller, category, city, monkeypatch
    ):
        """Purge deleted ads passes all storage keys (image + thumbnails) to delete_photo.

        Verifies PC-004: the sweep uses AdImage.storage_keys() so thumbnail
        derivatives are not orphaned on disk alongside the main image.
        """
        ad = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.DELETED,
            deleted_at=timezone.now() - timedelta(days=200),
        )
        img = AdImage.objects.create(
            ad=ad,
            image="test-uuid-purge-deleted.jpg",
            thumbnail_small="test-uuid-purge-deleted-small.jpg",
            thumbnail_medium="test-uuid-purge-deleted-medium.jpg",
            thumbnail_large="test-uuid-purge-deleted-large.jpg",
        )

        deleted_keys: list[str] = []

        def _record(storage_key: str) -> None:
            deleted_keys.append(storage_key)

        monkeypatch.setattr(
            "apps.core.management.commands.purge_deleted_ads.delete_photo",
            _record,
        )

        call_command("purge_deleted_ads")

        expected = img.storage_keys()
        assert sorted(deleted_keys) == sorted(expected)
        assert not Ad.objects.filter(pk=ad.pk).exists()
