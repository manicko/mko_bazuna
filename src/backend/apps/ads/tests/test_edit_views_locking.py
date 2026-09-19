"""
Structural and concurrency regression tests for DB-003 locking in edit.py.

Mirrors the ``TestModerationReviewLocking`` structural pattern from
``test_moderation_views.py`` (Block 2) and the concurrency pattern from
``test_transition_concurrency.py``.

Tests that the ``select_for_update()`` / ``transaction.atomic()`` pattern in
``ads.views.edit`` prevents the stale-state race window between fetching an
``Ad`` and calling ``transition_to()`` (which calls ``refresh_from_db()``).

With ``select_for_update()``, a concurrent hard-delete sweep blocks on the
row lock until the editing transaction commits, guaranteeing the row exists
for the entire transition window. Without the lock, the sweep could delete
the row between the fetch and ``refresh_from_db()``, causing
``Ad.DoesNotExist`` to propagate from ``transition_to()``.
"""

from __future__ import annotations

import inspect
import threading
import time

import pytest
from django.db import connection, transaction

from apps.ads.models import Ad
from apps.core.enums import AdStatus
from conftest import create_test_ad

pytestmark = [pytest.mark.integration]


# ---------------------------------------------------------------------------
# Tests: Structural assertions for DB-003 locking (select_for_update)
# ---------------------------------------------------------------------------


class TestEditViewsLocking:
    """Verify that ad_edit, ad_archive, and ad_reactivate use row-level
    locking (DB-003).

    These structural assertions guard against accidental removal of the
    ``select_for_update()`` / ``transaction.atomic()`` pattern in
    ``ads/views/edit.py`` — the fix for the stale-state race window between
    fetching an ``Ad`` and transitioning it inside the bot/web two-process
    architecture.
    """

    def test_ad_edit_uses_select_for_update_and_atomic(self) -> None:
        """ad_edit source contains select_for_update inside transaction.atomic."""
        from apps.ads.views import edit

        source = inspect.getsource(edit.ad_edit)
        assert "transaction.atomic" in source
        assert "select_for_update" in source

    def test_ad_edit_get_path_not_locked(self) -> None:
        """GET path in ad_edit does NOT use select_for_update.

        Only the POST body (inside transaction.atomic) should acquire the row
        lock — the GET path is a read-only display that returns before the
        POST block. Exactly ONE ``select_for_update`` should appear in the
        full function source (only in the locked POST re-fetch).
        """
        from apps.ads.views import edit

        source = inspect.getsource(edit.ad_edit)
        # Exactly one select_for_update (only in the locked POST re-fetch)
        assert source.count("select_for_update") == 1
        # The GET prefetch must not lock (it is a read-only display)
        assert "prefetch_related" in source

    def test_ad_archive_uses_select_for_update_and_atomic(self) -> None:
        """ad_archive source contains select_for_update inside transaction.atomic."""
        from apps.ads.views import edit

        source = inspect.getsource(edit.ad_archive)
        assert "transaction.atomic" in source
        assert "select_for_update" in source

    def test_ad_reactivate_uses_select_for_update_and_atomic(self) -> None:
        """ad_reactivate source contains select_for_update inside transaction.atomic."""
        from apps.ads.views import edit

        source = inspect.getsource(edit.ad_reactivate)
        assert "transaction.atomic" in source
        assert "select_for_update" in source

    def test_submit_ad_uses_select_for_update_and_atomic(self) -> None:
        """submit_ad source contains select_for_update inside transaction.atomic."""
        from apps.ads.services.submission import submit_ad

        source = inspect.getsource(submit_ad)
        assert "select_for_update" in source
        assert "transaction.atomic" in source

    def test_submit_ad_fetches_inside_atomic(self) -> None:
        """The plain Ad.objects.get() fetch must be replaced by a locked
        select_for_update() fetch inside the transaction.atomic() block.

        Verifies DB-004: the unlocked ``Ad.objects.get(id=input.ad_id)`` at the
        top of ``submit_ad`` is gone, and the ``select_for_update`` re-fetch now
        appears inside (after) the ``transaction.atomic()`` block.
        """
        from apps.ads.services.submission import submit_ad

        source = inspect.getsource(submit_ad)
        # The plain unlocked fetch must not appear anywhere in the source
        assert "Ad.objects.get(id=input.ad_id)" not in source
        # The locked fetch must be present
        assert "Ad.objects.select_for_update()" in source
        # The select_for_update fetch must appear inside/after the atomic block
        atomic_idx = source.index("transaction.atomic")
        sfu_idx = source.index("select_for_update")
        assert sfu_idx > atomic_idx, (
            "select_for_update fetch must appear inside the transaction.atomic() "
            "block, not before it"
        )


# ---------------------------------------------------------------------------
# Tests: Concurrency — select_for_update blocks concurrent delete
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
@pytest.mark.slow
@pytest.mark.integration
@pytest.mark.concurrent
class TestEditViewsRowLockConcurrency:
    """DB-003: ``select_for_update()`` in edit views prevents stale-state races."""

    def test_select_for_update_blocks_concurrent_delete_during_archive(
        self, seller, category, city
    ) -> None:
        """A row locked with ``select_for_update()`` blocks a concurrent
        hard-delete until the locking transaction commits.

        This is the core guarantee of DB-003: the archiving view holds the
        lock from fetch through ``transition_to``, so a concurrent sweep
        cannot delete the row in the gap between fetch and
        ``refresh_from_db()``.

        Uses ``transaction=True`` so the main thread's ``transaction.atomic()``
        is a real transaction (not a savepoint) — in PostgreSQL, row locks are
        released only on transaction commit/rollback, not on savepoint commit.
        The background thread gets its own connection (thread-local) and its
        ``DELETE`` blocks on the row lock until the main thread commits.

        Mirrors ``test_select_for_update_blocks_concurrent_delete`` from
        ``test_transition_concurrency.py``.
        """
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        ad_id = ad.id

        started = threading.Event()
        finished = threading.Event()
        errors: list[BaseException] = []

        def concurrent_hard_delete() -> None:
            """Background thread: attempts to hard-delete the row.

            Should block while the main thread holds the ``FOR UPDATE`` lock.
            """
            started.set()
            try:
                with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
                    Ad.objects.filter(pk=ad_id).delete()
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                finished.set()
                connection.close()

        # --- Main thread: acquire the row lock ---
        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
            locked_ad = Ad.objects.select_for_update().get(pk=ad_id)
            assert locked_ad.id == ad_id

            # --- Start the concurrent delete sweep ---
            thread = threading.Thread(target=concurrent_hard_delete)
            thread.start()

            # Wait for the background thread to start and issue the DELETE
            assert started.wait(timeout=5), "Background thread did not start"

            # The DELETE should be blocked waiting for the row lock.
            # Give it a moment to reach the blocking point, then verify
            # it has NOT finished.
            time.sleep(1.0)
            assert not finished.is_set(), (
                "DELETE completed before lock was released — "
                "select_for_update did not block the concurrent delete"
            )

        # --- Main transaction commits, releasing the row lock ---
        # The background thread's DELETE can now proceed.
        assert finished.wait(timeout=10), (
            "DELETE did not complete after lock was released"
        )
        thread.join(timeout=10)

        assert not errors, f"Background thread raised: {errors}"
        assert not Ad.objects.filter(pk=ad_id).exists(), (
            "Ad should have been hard-deleted by the concurrent sweep "
            "after the lock was released"
        )
