"""
Split from test_sweep_commands.py: Tests for the archive_sweep command.

Archive sweep moves ads older than 60 days from PUBLISHED to ARCHIVED status,
guarded by an advisory lock (lock id 1).
"""

from __future__ import annotations

import threading
import time
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.db import connection, transaction
from django.db.models.query import QuerySet
from django.utils import timezone

from apps.ads.models import Ad
from apps.core.enums import AdStatus, AdvisoryLockId
from apps.search.services.cache import get_search_version
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


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

    def test_archive_sweep_bumps_search_cache(self, seller, category, city):
        """archive_sweep calls transition_to() per-row, which fires post_save
        and bumps the search content version (AD-002).

        Previously the sweep used queryset.update() (bypassing save() and
        post_save), so the search cache version was not invalidated when
        published ads were archived.
        """
        stale = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.PUBLISHED,
            published_at=timezone.now() - timedelta(days=90),
        )
        # create_test_ad already bumps the cache version once (post_save on PUBLISHED);
        # record the baseline so we can assert the sweep causes a *second* bump.
        version_before = get_search_version()

        call_command("archive_sweep")

        stale.refresh_from_db()
        assert stale.status == AdStatus.ARCHIVED
        assert get_search_version() > version_before

    def test_archive_sweep_locks_batch_with_select_for_update(self) -> None:
        """``archive_sweep`` genuinely calls ``select_for_update()`` at runtime.

        Replaces an ``inspect.getsource`` token assertion (finding 03-DB-008):
        token presence is the wrong oracle, because a *vestigial*
        ``with transaction.atomic():`` left in ``handle`` (now only a savepoint)
        keeps both tokens present while silently defeating the per-batch commit.
        This asserts a real call instead — the ``QuerySet.select_for_update``
        runtime-spy pattern from
        ``test_db_lock_timeout_boundary.py::TestBulkLockTimeout``.
        """
        calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
        original = QuerySet.select_for_update

        def _spy(queryset: QuerySet, *args: object, **kwargs: object) -> QuerySet:
            calls.append((args, kwargs))
            return original(queryset, *args, **kwargs)

        with patch.object(QuerySet, "select_for_update", _spy):
            call_command("archive_sweep")

        assert calls, "archive_sweep never called select_for_update()"

    @pytest.mark.django_db(transaction=True)
    def test_batches_commit_independently(
        self, seller, category, city, monkeypatch
    ) -> None:
        """Each batch commits independently; a later failure keeps earlier work.

        The direct assertion of finding 03-DB-008: ``transaction=True`` is
        required so each per-batch ``atomic()`` is a real transaction (not a
        savepoint). A small batch size makes the population span at least three
        batches, and ``Ad.transition_to`` fails on the second batch. Pre-fix the
        whole sweep is one transaction and rolls back — no row is ``ARCHIVED``,
        which is exactly why this test is RED against the pre-fix code.
        """
        from apps.core.management.commands import archive_sweep

        monkeypatch.setattr(archive_sweep, "_BATCH_SIZE", 2)

        stale = [
            create_test_ad(
                seller,
                category,
                city,
                status=AdStatus.PUBLISHED,
                published_at=timezone.now() - timedelta(days=90),
            )
            for _ in range(6)
        ]
        stale.sort(key=lambda ad: (ad.published_at, ad.pk))
        batch_one_pks = {ad.pk for ad in stale[:2]}

        original_transition_to = Ad.transition_to
        failing_pk = stale[2].pk

        def _transition_to(self: Ad, target, *args, **kwargs):
            if self.pk == failing_pk:
                raise RuntimeError("injected failure in batch 2")
            return original_transition_to(self, target, *args, **kwargs)

        monkeypatch.setattr(Ad, "transition_to", _transition_to)

        with pytest.raises(RuntimeError, match="injected failure in batch 2"):
            call_command("archive_sweep")

        archived_pks = set(
            Ad.objects.filter(pk__in=batch_one_pks, status=AdStatus.ARCHIVED)
            .values_list("pk", flat=True)
        )
        assert archived_pks == batch_one_pks, (
            "batch 1 must be committed when a later batch fails — the per-batch "
            "commit is not taking effect (03-DB-008)"
        )


# ---------------------------------------------------------------------------
# Tests: Concurrency — archive_sweep row lock blocks concurrent web edit
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
@pytest.mark.slow
@pytest.mark.integration
@pytest.mark.concurrent
class TestArchiveSweepRowLockConcurrency:
    """DB-010: ``select_for_update()`` in archive_sweep prevents lost-update race
    with concurrent web/bot writes."""

    def test_archive_row_lock_blocks_concurrent_edit(
        self, seller, category, city
    ) -> None:
        """A row locked by archive_sweep's ``select_for_update()`` blocks a
        concurrent web-edit transition on the same ad until the lock is
        released.

        This is the core guarantee of the DB-010 fix: ``archive_sweep`` holds the
        ``FOR UPDATE`` row lock from fetch through ``transition_to()``, so a
        concurrent web/bot edit (which itself uses ``select_for_update()``)
        cannot silently overwrite the ad's state in the gap between fetch and
        ``refresh_from_db()``.

        Uses ``transaction=True`` so the main thread's ``transaction.atomic()``
        is a real transaction (not a savepoint) — row locks are released only on
        commit/rollback, not on savepoint commit. The background thread gets its
        own connection (thread-local) and its conflicting ``select_for_update``
        blocks on the row lock until the main thread commits.

        Mirrors ``test_select_for_update_blocks_concurrent_delete_during_archive``
        from ``test_edit_views_locking.py`` and
        ``test_select_for_update_blocks_concurrent_delete`` from
        ``test_transition_concurrency.py``.
        """
        ad = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.PUBLISHED,
            published_at=timezone.now() - timedelta(days=90),
        )
        ad_id = ad.id

        started = threading.Event()
        finished = threading.Event()
        errors: list[BaseException] = []

        def concurrent_web_edit() -> None:
            """Background thread: simulates a concurrent web/bot edit
            (e.g., ad_archive or moderator re-submission) that tries to
            acquire the same row lock — must block until archive_sweep
            releases it.
            """
            started.set()
            try:
                with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
                    # This select_for_update will block while the main thread
                    # holds the FOR UPDATE lock (simulating archive_sweep).
                    conflicting_ad = Ad.objects.select_for_update().get(pk=ad_id)
                    # PUBLISHED -> ON_MODERATION is a valid transition
                    # (mirroring ad_archive / moderator re-submission paths).
                    conflicting_ad.transition_to(AdStatus.ON_MODERATION)
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                finished.set()
                connection.close()

        # --- Main thread: simulate archive_sweep's locked row iteration ---
        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
            locked_ad = Ad.objects.select_for_update().get(pk=ad_id)
            assert locked_ad.id == ad_id

            # --- Start the concurrent web edit ---
            thread = threading.Thread(target=concurrent_web_edit)
            thread.start()

            # Wait for the background thread to start and issue its
            # select_for_update
            assert started.wait(timeout=5), "Background thread did not start"

            # The concurrent edit should be blocked waiting for the row lock.
            # Give it a moment to reach the blocking point, then verify
            # it has NOT finished.
            time.sleep(1.0)
            assert not finished.is_set(), (
                "Concurrent edit completed before lock was released — "
                "select_for_update did not block the concurrent transition"
            )

        # --- Main transaction commits, releasing the row lock ---
        # The background thread's select_for_update can now proceed.
        assert finished.wait(timeout=10), (
            "Concurrent edit did not complete after lock was released"
        )
        thread.join(timeout=10)

        assert not errors, f"Background thread raised: {errors}"

        # The background thread transitioned the ad to ON_MODERATION (its
        # transition_to was the only mutation — the main thread only held the
        # lock without modifying). The ad state must reflect a valid final
        # status, not a lost update.
        ad.refresh_from_db()
        assert ad.status == AdStatus.ON_MODERATION
