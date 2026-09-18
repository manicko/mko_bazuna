"""
Concurrency regression tests for DB-003: ``select_for_update()`` locking.

Tests that the ``select_for_update()`` row lock in ``review.py`` moderation
views prevents the stale-state race window between fetching an ``Ad`` and
calling ``transition_to()`` (which calls ``refresh_from_db()``).

With ``select_for_update()``, a concurrent hard-delete sweep blocks on the
row lock until the moderation transaction commits, guaranteeing the row
exists for the entire transition window. Without the lock, the sweep could
delete the row between the fetch and ``refresh_from_db()``, causing
``Ad.DoesNotExist`` to propagate from ``transition_to()``.

See also: Block 1's ``test_transition_after_concurrent_hard_delete_raises``
in ``test_ad_lifecycle.py`` for the ``DoesNotExist`` contract when the lock
is NOT held.
"""

from __future__ import annotations

import threading
import time

import pytest
from django.db import connection, transaction

from apps.ads.models import Ad
from apps.core.enums import AdStatus
from conftest import create_test_ad

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.integration,
    pytest.mark.concurrent,
]


class TestAdRowLockConcurrency:
    """DB-003: ``select_for_update()`` in review views prevents stale-state races."""

    def test_select_for_update_blocks_concurrent_delete(
        self, seller, category, city
    ) -> None:
        """A row locked with ``select_for_update()`` blocks a concurrent
        hard-delete until the locking transaction commits.

        This is the core guarantee of DB-003: the moderation view holds the
        lock from fetch through ``transition_to``, so a concurrent sweep
        cannot delete the row in the gap between fetch and
        ``refresh_from_db()``.

        Uses ``transaction=True`` so the main thread's ``transaction.atomic()``
        is a real transaction (not a savepoint) — in PostgreSQL, row locks
        are released only on transaction commit/rollback, not on savepoint
        commit. The background thread gets its own connection (thread-local)
        and its ``DELETE`` blocks on the row lock until the main thread
        commits.
        """
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)
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
                with transaction.atomic():  # type: ignore[reportGeneralTypeIssues]
                    Ad.objects.filter(pk=ad_id).delete()
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                finished.set()
                connection.close()

        # --- Main thread: acquire the row lock ---
        with transaction.atomic():  # type: ignore[reportGeneralTypeIssues]
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
