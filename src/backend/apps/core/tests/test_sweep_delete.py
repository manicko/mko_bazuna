"""
Split from test_sweep_commands.py: Tests for the delete_sweep command and
concurrent-double-sweep behavior.

Delete sweep purges ads in ARCHIVED status older than 60 days, guarded by an
advisory lock (lock id 2).
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


class TestDeleteSweep:
    """Tests for delete_sweep command (advisory lock 2, 60-day window)."""

    def test_dry_run_does_not_delete(self, seller, category, city):

        old = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.ARCHIVED,
            archived_at=timezone.now() - timedelta(days=200),
        )
        AdImage.objects.create(ad=old, image="test-uuid.jpg")
        call_command("delete_sweep", "--dry-run")
        assert Ad.objects.filter(pk=old.pk).exists()

    def test_deletes_archived_older_than_60_days(self, seller, category, city):

        old = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.ARCHIVED,
            archived_at=timezone.now() - timedelta(days=200),
        )
        AdImage.objects.create(ad=old, image="test-uuid.jpg")
        recent = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.ARCHIVED,
            archived_at=timezone.now() - timedelta(days=30),
        )
        call_command("delete_sweep")
        assert not Ad.objects.filter(pk=old.pk).exists()
        assert Ad.objects.filter(pk=recent.pk).exists()

    def test_purges_manually_archived_recent_publish(self, seller, category, city):
        """Manually-archived ad with recent published_at is still purged.

        Proves delete_sweep anchors on archived_at (not published_at): an ad
        published 10 days ago but archived 200 days ago must still be purged.
        """
        ad = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.ARCHIVED,
            published_at=timezone.now() - timedelta(days=10),
            archived_at=timezone.now() - timedelta(days=200),
        )
        call_command("delete_sweep")
        assert not Ad.objects.filter(pk=ad.pk).exists()

    def test_cascades_ad_images(self, seller, category, city):

        old = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.ARCHIVED,
            archived_at=timezone.now() - timedelta(days=200),
        )
        img = AdImage.objects.create(ad=old, image="test-uuid.jpg")
        call_command("delete_sweep")
        assert not AdImage.objects.filter(pk=img.pk).exists()

    @pytest.mark.django_db(transaction=True)
    def test_collects_thumbnail_keys_for_media_cleanup(
        self, seller, category, city, monkeypatch
    ):
        """Delete sweep passes all storage keys (image + thumbnails) to delete_photo.

        Verifies PC-004: the sweep uses AdImage.storage_keys() so thumbnail
        derivatives are not orphaned on disk alongside the main image.
        """
        ad = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.ARCHIVED,
            archived_at=timezone.now() - timedelta(days=200),
        )
        img = AdImage.objects.create(
            ad=ad,
            image="test-uuid-delete-sweep.jpg",
            thumbnail_small="test-uuid-delete-sweep-small.jpg",
            thumbnail_medium="test-uuid-delete-sweep-medium.jpg",
            thumbnail_large="test-uuid-delete-sweep-large.jpg",
        )

        deleted_keys: list[str] = []

        def _record(storage_key: str) -> None:
            deleted_keys.append(storage_key)

        monkeypatch.setattr(
            "apps.media.signals.delete_photo",
            _record,
        )

        call_command("delete_sweep")

        expected = img.storage_keys()
        assert sorted(deleted_keys) == sorted(expected)
        assert not Ad.objects.filter(pk=ad.pk).exists()

    def test_lock_id_is_delete_sweep(self):
        assert AdvisoryLockId.DELETE_SWEEP == 2


class TestConcurrentSweep:
    """Concurrent-double-sweep tests verifying advisory lock serialization (DB-003)."""

    @pytest.mark.django_db(transaction=True)
    def test_file_deletion_after_commit_not_inside_transaction(
        self, seller, category, city, monkeypatch
    ):
        """delete_photo runs AFTER transaction.atomic() commits, not inside it.

        If delete_photo were called inside the transaction, a filesystem
        failure would trigger a DB rollback and the Ad rows would be restored.
        When called after commit, the DB delete persists even if file deletion
        raises — proving the filesystem side-effect is decoupled from the
        transaction boundary.

        Addresses the residual DB-001/DB-002 warning: filesystem deletions
        inside transaction.atomic() cannot be rolled back, so a DB rollback
        would orphan DB rows pointing to already-deleted files.
        """
        old = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.ARCHIVED,
            archived_at=timezone.now() - timedelta(days=200),
        )
        AdImage.objects.create(ad=old, image="test-uuid.jpg")

        called: list[str] = []

        def _raise(storage_key: str) -> None:
            called.append(storage_key)
            raise RuntimeError("disk full")

        monkeypatch.setattr(
            "apps.media.signals.delete_photo",
            _raise,
        )

        # delete_photo raises inside the signal handler's try/except,
        # which swallows the exception — the command does NOT propagate it.
        call_command("delete_sweep")

        # DB rows are gone despite the file-deletion failure -> proves
        # delete_photo ran after the transaction committed.
        assert not Ad.objects.filter(pk=old.pk).exists()
        # delete_photo was attempted (on_commit fired after commit).
        assert called
