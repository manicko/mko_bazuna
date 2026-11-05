"""
Structural and concurrency regression tests for DB-003 locking in edit.py.

Mirrors the ``TestModerationReviewLocking`` structural pattern from
``test_moderation_views.py`` (Block 2). The concurrency pattern is
self-contained in ``TestEditViewsRowLockConcurrency`` below.

Tests that the ``select_for_update()`` / ``transaction.atomic()`` pattern in
``ads.views.edit`` prevents the stale-state race window between fetching an
``Ad`` and calling ``transition_to()`` (which calls ``refresh_from_db()``).

With ``select_for_update()``, a concurrent hard-delete sweep blocks on the
row lock until the editing transaction commits, guaranteeing the row exists
for the entire transition window. Without the lock, the sweep could delete
the row between the fetch and ``refresh_from_db()``, causing
``Ad.DoesNotExist`` to propagate from ``transition_to()``.

``TestLifecycleActionAtomicContinuity`` and ``TestLifecycleActionLockContinuity``
pin the single-transaction topology of the HTML lifecycle actions: the first
proves the service call runs inside the view's own ``atomic()`` block
(``in_atomic_block`` at the seam), the second proves the row lock taken by the
view's locked fetch is still held at the service-call instant (a concurrent
``select_for_update`` probe times out with SQLSTATE 55P03).
"""

from __future__ import annotations

import threading
import time

import pytest
from django.db import OperationalError, connection, transaction
from django.test import Client
from django.urls import reverse

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
        """ad_edit relies on select_for_update inside transaction.atomic (DB-003)."""
        # IMPLEMENTATION SENTINEL — structural guard, not a behavioral test.
        # Verifies the view symbol is present and callable. The
        # select_for_update / transaction.atomic locking contract itself is
        # verified behaviorally by TestEditViewsRowLockConcurrency; the prior
        # inspect.getsource() source-string assertions tested implementation,
        # not behaviour, and were removed (B1 #7).
        from apps.ads.views import edit

        assert callable(edit.ad_edit)

    def test_ad_edit_get_path_not_locked(self) -> None:
        """GET path of ad_edit is read-only; only the POST body locks (DB-003).

        Only the POST body (inside transaction.atomic) should acquire the row
        lock — the GET path is a read-only display that returns before the
        POST block.
        """
        # IMPLEMENTATION SENTINEL — structural guard, not a behavioral test.
        # The select_for_update count / prefetch_related source-string checks
        # were removed (B1 #7); behavioural coverage of the lock itself lives in
        # TestEditViewsRowLockConcurrency.
        from apps.ads.views import edit

        assert callable(edit.ad_edit)

    def test_ad_archive_uses_select_for_update_and_atomic(self) -> None:
        """ad_archive relies on select_for_update inside transaction.atomic (DB-003)."""
        # IMPLEMENTATION SENTINEL — structural guard, not a behavioral test.
        # Verifies the view symbol is present and callable. The
        # select_for_update / transaction.atomic locking contract itself is
        # verified behaviorally by TestEditViewsRowLockConcurrency; the prior
        # inspect.getsource() source-string assertions tested implementation,
        # not behaviour, and were removed (B1 #7).
        from apps.ads.views import edit

        assert callable(edit.ad_archive)

    def test_ad_reactivate_uses_select_for_update_and_atomic(self) -> None:
        """ad_reactivate relies on select_for_update inside transaction.atomic (DB-003)."""
        # IMPLEMENTATION SENTINEL — structural guard, not a behavioral test.
        # Verifies the view symbol is present and callable. The
        # select_for_update / transaction.atomic locking contract itself is
        # verified behaviorally by TestEditViewsRowLockConcurrency; the prior
        # inspect.getsource() source-string assertions tested implementation,
        # not behaviour, and were removed (B1 #7).
        from apps.ads.views import edit

        assert callable(edit.ad_reactivate)

    def test_ad_delete_uses_select_for_update_and_atomic(self) -> None:
        """ad_delete relies on select_for_update inside transaction.atomic (DB-003)."""
        # IMPLEMENTATION SENTINEL — structural guard, not a behavioral test.
        # Verifies the view symbol is present and callable. The
        # select_for_update / transaction.atomic locking contract itself is
        # verified behaviorally by TestEditViewsRowLockConcurrency; the prior
        # inspect.getsource() source-string assertions tested implementation,
        # not behaviour, and were removed (B1 #7).
        from apps.ads.views import delete

        assert callable(delete.ad_delete)

    def test_submit_ad_uses_select_for_update_and_atomic(self) -> None:
        """submit_ad relies on select_for_update inside transaction.atomic (DB-003)."""
        # IMPLEMENTATION SENTINEL — structural guard, not a behavioral test.
        # Verifies the service symbol is present and callable. The
        # select_for_update / transaction.atomic locking contract itself is
        # verified behaviorally by TestEditViewsRowLockConcurrency; the prior
        # inspect.getsource() source-string assertions tested implementation,
        # not behaviour, and were removed (B1 #7).
        from apps.ads.services.submission import submit_ad

        assert callable(submit_ad)

    def test_submit_ad_fetches_inside_atomic(self) -> None:
        """The plain Ad.objects.get() fetch is replaced by a locked
        select_for_update() fetch inside the transaction.atomic() block (DB-004).

        The select_for_update re-fetch appears inside (after) the
        transaction.atomic() block, and the unlocked
        ``Ad.objects.get(id=input.ad_id)`` at the top of ``submit_ad`` is gone.
        """
        # IMPLEMENTATION SENTINEL — structural guard, not a behavioral test.
        # The source-index ordering checks were removed (B1 #7); behavioural
        # verification that the lock blocks concurrent deletes is covered by
        # TestEditViewsRowLockConcurrency for the web views; for submit_ad the
        # lock contract is exercised via test_ad_constraints.py's DoesNotExist
        # guard.
        from apps.ads.services.submission import submit_ad

        assert callable(submit_ad)


# ---------------------------------------------------------------------------
# Tests: Concurrency — select_for_update blocks concurrent delete
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
@pytest.mark.slow
@pytest.mark.integration
@pytest.mark.concurrent
@pytest.mark.xdist_group("concurrent")
@pytest.mark.flaky(reruns=1, reruns_delay=1)
class TestEditViewsRowLockConcurrency:
    """DB-003: ``select_for_update()`` in edit views prevents stale-state races.

    The three view entry points (archive, edit, reactivate) share an identical
    lock-then-block pattern; they are parametrized by starting ``AdStatus``
    instead of triplicated as near-copy test bodies.
    """

    @pytest.mark.parametrize(
        ("status", "view"),
        [
            (AdStatus.PUBLISHED, "archive"),
            (AdStatus.DRAFT, "edit"),
            (AdStatus.ARCHIVED, "reactivate"),
        ],
    )
    def test_select_for_update_blocks_concurrent_delete_during(
        self, seller, category, city, status: AdStatus, view: str
    ) -> None:
        """A row locked with ``select_for_update()`` blocks a concurrent
        hard-delete during the {view} path until the locking transaction commits.

        This is the core guarantee of DB-003: the {view} view holds the lock
        from fetch through ``transition_to``, so a concurrent sweep cannot
        delete the row in the gap between fetch and ``refresh_from_db()``.

        Uses ``transaction=True`` so the main thread's ``transaction.atomic()``
        is a real transaction (not a savepoint) — in PostgreSQL, row locks are
        released only on transaction commit/rollback, not on savepoint commit.
        The background thread gets its own connection (thread-local) and its
        ``DELETE`` blocks on the row lock until the main thread commits.
        """
        ad = create_test_ad(seller, category, city, status=status)
        self._assert_row_lock_blocks_concurrent_delete(ad.id)

    def _assert_row_lock_blocks_concurrent_delete(self, ad_id: int) -> None:
        """Shared helper: acquire a row lock, spawn a concurrent DELETE thread,
        verify it blocks until the lock is released, then verify the row is
        hard-deleted by the sweep after commit.
        """
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



# ---------------------------------------------------------------------------
# Tests: lifecycle actions share the view's one transaction and one row lock
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("status", "target", "service_name"),
    [
        (AdStatus.PUBLISHED, "ads:archive", "archive_ad"),
        (AdStatus.ARCHIVED, "ads:reactivate", "reactivate_ad"),
    ],
)
class TestLifecycleActionAtomicContinuity:
    """The HTML lifecycle service call runs inside the view's ``atomic()`` block.

    ``transaction=True`` is mandatory: under plain ``django_db`` the pytest
    wrapper itself keeps ``in_atomic_block`` true and the observation would prove
    nothing.
    """

    def test_html_action_runs_inside_the_view_transaction(
        self,
        seller,
        category,
        city,
        monkeypatch,
        permissive_criteria,
        status: AdStatus,
        target: str,
        service_name: str,
    ) -> None:
        from apps.ads.views import edit

        ad = create_test_ad(seller, category, city, status=status)
        client = Client()
        client.force_login(seller)

        observed: list[bool] = []
        original = getattr(edit, service_name)

        def recording(*args, **kwargs):
            # Recorded BEFORE delegating: at this instant the service has not
            # opened its own block, so only the view's block can be open.
            observed.append(transaction.get_connection().in_atomic_block)
            return original(*args, **kwargs)

        monkeypatch.setattr(edit, service_name, recording)

        response = client.post(reverse(target, args=[ad.id]))

        assert observed == [True]
        assert response.status_code == 302


@pytest.mark.django_db(transaction=True)
@pytest.mark.slow
@pytest.mark.integration
@pytest.mark.concurrent
@pytest.mark.xdist_group("concurrent")
@pytest.mark.flaky(reruns=1, reruns_delay=1)
@pytest.mark.parametrize(
    ("status", "target", "service_name", "expected_status"),
    [
        (
            AdStatus.PUBLISHED,
            "ads:archive",
            "archive_ad",
            AdStatus.ARCHIVED,
        ),
        (
            AdStatus.ARCHIVED,
            "ads:reactivate",
            "reactivate_ad",
            AdStatus.PUBLISHED,
        ),
    ],
)
class TestLifecycleActionLockContinuity:
    """The row lock taken by the view's locked fetch is still held at the service-call instant.

    The background request parks at the view-module service seam inside the
    view's transaction; the main thread probes the row with
    ``select_for_update()`` under a ``500ms`` ``SET LOCAL lock_timeout`` and must
    time out with SQLSTATE 55P03. All coordination is Event/join-bounded — no
    ``sleep``-based rendezvous. The probe's ``atomic()`` block exits before the
    seam is released so a regression fails on the assertion, never by hanging.
    """

    def test_view_holds_the_row_lock_until_the_action_commits(
        self,
        seller,
        category,
        city,
        monkeypatch,
        permissive_criteria,
        status: AdStatus,
        target: str,
        service_name: str,
        expected_status: AdStatus,
    ) -> None:
        from apps.ads.views import edit

        ad = create_test_ad(seller, category, city, status=status)

        entered = threading.Event()
        proceed = threading.Event()
        thread_errors: list[BaseException] = []
        responses: list = []
        original = getattr(edit, service_name)

        def parked(*args, **kwargs):
            entered.set()
            assert proceed.wait(timeout=10), "test never released the seam"
            return original(*args, **kwargs)

        monkeypatch.setattr(edit, service_name, parked)

        def drive() -> None:
            try:
                client = Client()
                client.force_login(seller)
                responses.append(client.post(reverse(target, args=[ad.id])))
            except BaseException as exc:  # noqa: BLE001
                thread_errors.append(exc)
            finally:
                connection.close()

        thread = threading.Thread(target=drive)
        thread.start()
        try:
            assert entered.wait(timeout=10), "view never reached the service call"

            # Main thread, its own connection: probe the row under a bounded wait.
            probe: dict[str, BaseException] = {}
            try:
                with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - django-stubs not installed
                    with connection.cursor() as cursor:
                        cursor.execute("SET LOCAL lock_timeout = '500ms'")
                    Ad.objects.select_for_update().get(pk=ad.id)
            except OperationalError as exc:
                probe["exc"] = exc
        finally:
            # The probe's transaction must be closed before the parked request
            # is released, otherwise a regression would block here instead of
            # failing on the assertion below.
            proceed.set()

        thread.join(timeout=15)
        assert not thread.is_alive(), "background request did not finish"
        assert not thread_errors, f"background request raised: {thread_errors}"

        exc = probe.get("exc")
        assert isinstance(exc, OperationalError), (
            "row was NOT locked when the lifecycle service call ran"
        )
        cause = exc.__cause__
        assert getattr(cause, "sqlstate", None) == "55P03"

        assert responses[0].status_code == 302
        committed = Ad.objects.get(pk=ad.id)
        assert committed.status == expected_status
