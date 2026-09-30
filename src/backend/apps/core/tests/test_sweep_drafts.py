"""
Split from test_sweep_commands.py: Tests for the sweep_drafts command.

Draft sweep deletes DRAFT-status ads with no seller activity for 30 minutes
(measured on ``Ad.updated_at``), guarded by an advisory lock (lock id 4).
Also covers the 0003 dedup migration.
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

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


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

    def test_dry_run_does_not_delete(self, seller, category, city, caplog):
        """``--dry-run`` deletes nothing, and the fixture is proven eligible.

        The predicate measures **inactivity**: it back-dates ``updated_at``, not
        ``created_at``.  The ``caplog`` assertion is what makes this test
        non-vacuous — it proves the sweep actually *saw* one eligible row and
        would have deleted it, so the survival assertion is a real ``--dry-run``
        guarantee and not merely the absence of an eligible row.
        """
        import logging

        old = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.DRAFT,
        )
        Ad.objects.filter(pk=old.pk).update(
            updated_at=timezone.now() - timedelta(minutes=90)
        )
        old.refresh_from_db()
        with caplog.at_level(logging.INFO, logger="apps.core.management.commands.sweep_drafts"):
            call_command("sweep_drafts", "--dry-run")
        # Non-vacuity: the sweep counted one eligible draft and would delete it.
        assert "DRY RUN: Would delete 1 draft ads" in caplog.text
        assert Ad.objects.filter(pk=old.pk).exists()

    def test_deletes_drafts_older_than_30_minutes(self, seller, category, city, user):
        """An inactive draft (old ``updated_at``) is deleted; an active one survives.

        The predicate measures **inactivity**, not age: both rows' ``updated_at``
        are back-dated, and the two-sided assertion is what makes this a
        predicate test rather than a delete test.
        """

        old = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.DRAFT,
        )
        Ad.objects.filter(pk=old.pk).update(
            updated_at=timezone.now() - timedelta(minutes=90)
        )
        old.refresh_from_db()
        recent = create_test_ad(
            user,
            category,
            city,
            status=AdStatus.DRAFT,
        )
        Ad.objects.filter(pk=recent.pk).update(
            updated_at=timezone.now() - timedelta(minutes=5)
        )
        recent.refresh_from_db()
        call_command("sweep_drafts")
        assert not Ad.objects.filter(pk=old.pk).exists()
        assert Ad.objects.filter(pk=recent.pk).exists()

    def test_old_created_at_with_fresh_updated_at_survives(
        self, seller, category, city
    ):
        """A draft whose ``created_at`` is ancient but ``updated_at`` is fresh survives.

        This is the direct regression guard for 03-DB-003: an in-progress dialog
        is older than 30 minutes since ``/post`` but has been heartbeated, so it
        must NOT be reaped.
        """
        ad = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.DRAFT,
        )
        Ad.objects.filter(pk=ad.pk).update(
            created_at=timezone.now() - timedelta(hours=5),
            updated_at=timezone.now(),
        )
        ad.refresh_from_db()
        call_command("sweep_drafts")
        assert Ad.objects.filter(pk=ad.pk).exists()

    def test_old_updated_at_is_deleted_even_with_older_created_at(
        self, seller, category, city
    ):
        """An old ``updated_at`` is deleted even when ``created_at`` is older still.

        Pins that the predicate is ``updated_at`` ONLY — it did not become
        "``created_at`` OR ``updated_at``".
        """
        ad = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.DRAFT,
        )
        Ad.objects.filter(pk=ad.pk).update(
            created_at=timezone.now() - timedelta(hours=5),
            updated_at=timezone.now() - timedelta(minutes=90),
        )
        ad.refresh_from_db()
        call_command("sweep_drafts")
        assert not Ad.objects.filter(pk=ad.pk).exists()

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

    @pytest.mark.django_db(transaction=True)
    def test_collects_thumbnail_keys_for_media_cleanup(
        self, seller, category, city, monkeypatch
    ):
        """The AdImage ``pre_delete`` signal unlinks every key when the sweep cascades.

        The sweep itself passes **nothing** to ``delete_photo``: it calls
        ``queryset.delete()`` and the ``AdImage`` ``pre_delete`` signal collects
        ``AdImage.storage_keys()`` (image + all three thumbnail derivatives) and
        unlinks them via ``transaction.on_commit()``.  The sweep's only obligation
        is to make the row eligible for the cascade.  (The prior docstring
        credited the sweep with passing the keys — that was BLOCK 1 /
        ``03-DB-011`` documentation debt: the key pre-collection was removed and
        the signal has been the mechanism since.)

        The predicate measures **inactivity**, so ``updated_at`` is back-dated.
        """
        ad = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.DRAFT,
        )
        Ad.objects.filter(pk=ad.pk).update(
            updated_at=timezone.now() - timedelta(minutes=90)
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
            "apps.media.signals.delete_photo",
            _record,
        )

        call_command("sweep_drafts")

        expected = img.storage_keys()
        assert sorted(deleted_keys) == sorted(expected)
        assert not Ad.objects.filter(pk=ad.pk).exists()

    def test_lock_id_is_sweep_drafts(self):
        assert AdvisoryLockId.SWEEP_DRAFTS == 4

    def test_draft_sweep_index_leads_on_updated_at(self):
        """``IX_ads_draft_sweep`` indexes ``updated_at`` (03-DB-003).

        The index is load-bearing for the flipped predicate: with ``created_at``
        the sweep degenerates into a heap ``Filter`` over every draft row. It
        asserts the model-declared index (what ``syncdb`` builds, and what the
        ``ads/0008_*`` migration is supposed to build).  ``DisableMigrations``
        means no gate replays the migration file, so the migration itself is
        verified manually on a scratch database.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT indexdef FROM pg_indexes "
                "WHERE tablename = 'ads' AND lower(indexname) = lower('IX_ads_draft_sweep')"
            )
            row = cursor.fetchone()

        assert row is not None, "IX_ads_draft_sweep is missing from pg_indexes"
        indexdef = row[0]
        assert "updated_at" in indexdef
        assert "created_at" not in indexdef

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
