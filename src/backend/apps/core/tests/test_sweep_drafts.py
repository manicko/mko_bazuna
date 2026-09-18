"""
Split from test_sweep_commands.py: Tests for the sweep_drafts command.

Draft sweep deletes DRAFT-status ads older than 30 minutes, guarded by an
advisory lock (lock id 4). Also covers the 0003 dedup migration.
"""

from __future__ import annotations

import importlib
from datetime import timedelta

import pytest
from django.apps import apps as django_apps
from django.core.management import call_command
from django.db import connection
from django.utils import timezone

from apps.ads.models import Ad, AdImage
from apps.core.enums import AdStatus, AdvisoryLockId
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


@pytest.fixture
def collapse_per_user_drafts():
    """Load the ``collapse_per_user_drafts`` forward function from migration 0003.

    Test settings disable migration replay (``DisableMigrations``), so the
    migration module is imported directly via ``importlib`` and invoked
    against the live app registry (``django.apps.apps``).
    """
    migration_module = importlib.import_module(
        "apps.ads.migrations.0003_dedup_per_user_drafts"
    )
    return migration_module.collapse_per_user_drafts


class TestSweepDrafts:
    """Tests for sweep_drafts command (advisory lock 4, 30-minute window)."""

    def test_dry_run_does_not_delete(self, seller, category, city):

        old = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.DRAFT,
        )
        Ad.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(minutes=90)
        )
        old.refresh_from_db()
        call_command("sweep_drafts", "--dry-run")
        assert Ad.objects.filter(pk=old.pk).exists()

    def test_deletes_drafts_older_than_30_minutes(self, seller, category, city, user):

        old = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.DRAFT,
        )
        Ad.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(minutes=90)
        )
        old.refresh_from_db()
        recent = create_test_ad(
            user,
            category,
            city,
            status=AdStatus.DRAFT,
        )
        Ad.objects.filter(pk=recent.pk).update(
            created_at=timezone.now() - timedelta(minutes=5)
        )
        recent.refresh_from_db()
        call_command("sweep_drafts")
        assert not Ad.objects.filter(pk=old.pk).exists()
        assert Ad.objects.filter(pk=recent.pk).exists()

    def test_does_not_touch_published_drafts(self, seller, category, city):

        # Published ads with old created_at must survive the draft sweep.
        ad = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.PUBLISHED,
        )
        Ad.objects.filter(pk=ad.pk).update(
            created_at=timezone.now() - timedelta(days=10)
        )
        ad.refresh_from_db()
        call_command("sweep_drafts")
        assert Ad.objects.filter(status=AdStatus.PUBLISHED).count() == 1

    def test_collects_thumbnail_keys_for_media_cleanup(
        self, seller, category, city, monkeypatch
    ):
        """Sweep drafts passes all storage keys (image + thumbnails) to delete_photo.

        Verifies PC-004: the sweep uses AdImage.storage_keys() so thumbnail
        derivatives are not orphaned on disk alongside the main image.
        """
        ad = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.DRAFT,
        )
        Ad.objects.filter(pk=ad.pk).update(
            created_at=timezone.now() - timedelta(minutes=90)
        )
        ad.refresh_from_db()
        img = AdImage.objects.create(
            ad=ad,
            image="test-uuid-sweep-drafts.jpg",
            thumbnail_small="test-uuid-sweep-drafts-small.jpg",
            thumbnail_medium="test-uuid-sweep-drafts-medium.jpg",
            thumbnail_large="test-uuid-sweep-drafts-large.jpg",
        )

        deleted_keys: list[str] = []

        def _record(storage_key: str) -> None:
            deleted_keys.append(storage_key)

        monkeypatch.setattr(
            "apps.core.management.commands.sweep_drafts.delete_photo",
            _record,
        )

        call_command("sweep_drafts")

        expected = img.storage_keys()
        assert sorted(deleted_keys) == sorted(expected)
        assert not Ad.objects.filter(pk=ad.pk).exists()

    def test_lock_id_is_sweep_drafts(self):
        assert AdvisoryLockId.SWEEP_DRAFTS == 4

    def test_dedup_migration_collapses_duplicate_drafts(
        self, seller, category, city, collapse_per_user_drafts
    ):
        """Migration 0003 collapses per-user duplicate DRAFTs, keeping newest by id.

        Addresses AD-009a: ``create_draft_ad`` has no existence check, so a user
        can accumulate multiple DRAFT rows. The migration keeps the newest
        (greatest id) and deletes the older ones.
        """
        first = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.DRAFT,
        )
        # Drop the single-draft-per-user unique index so we can simulate the
        # pre-migration state where duplicate DRAFTs existed for one user.
        # In PostgreSQL, Django creates UniqueConstraint with a condition as a
        # unique *index*, not a table-level constraint, so SET CONSTRAINTS
        # cannot defer it. DROP INDEX is transactional: it is automatically
        # restored when the test transaction rolls back (TestCase semantics).
        with connection.cursor() as _cursor:
            _cursor.execute("DROP INDEX uq_ads_single_draft_per_user")
        second = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.DRAFT,
        )

        assert Ad.objects.filter(user=seller, status=AdStatus.DRAFT).count() == 2

        # Run the migration forward function directly.
        collapse_per_user_drafts(django_apps, None)

        remaining = Ad.objects.filter(user=seller, status=AdStatus.DRAFT)
        assert remaining.count() == 1
        # The newest (greatest id) survives; the older one is deleted.
        assert remaining.get().pk == second.pk
        assert not Ad.objects.filter(pk=first.pk).exists()
