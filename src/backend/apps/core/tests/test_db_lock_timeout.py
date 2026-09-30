"""Bounds on the row-lock wait and the shared lock-timeout predicate (03-DB-004).

Two layers are covered here:

1. **The connection-level bound.** ``DATABASES["default"]["OPTIONS"]["options"]``
   carries ``-c lock_timeout=<N>s``, so *every* connection — web, bot and the
   management commands — abandons a contended row, table or advisory lock after
   the configured number of seconds instead of hanging forever. A blocked
   ``SELECT ... FOR UPDATE`` therefore raises ``OperationalError`` whose
   ``__cause__`` is ``psycopg.errors.LockNotAvailable`` (SQLSTATE ``55P03``).

2. **The shared classifier.** ``is_lock_timeout`` is the single predicate both
   processes use to decide whether an ``OperationalError`` is a lock timeout or
   something that must keep its existing behaviour. It matches SQLSTATE
   ``55P03`` only — never ``57014`` (a ``statement_timeout``), never a
   connection refusal, and never on the message text.

``test_lock_wait_is_bounded`` was written **before** the setting landed and was
observed RED (it carries its own bounded join + explicit deadline failure, so the
pre-fix run fails fast instead of hanging forever).
"""

from __future__ import annotations

import threading

import pytest
from django.db import OperationalError, connection, transaction

from conftest import create_test_ad

pytestmark = [pytest.mark.integration]


# The bound the production ``OPTIONS`` is expected to render. Asserted as the
# rendered string (not the int) because a bare PostgreSQL GUC number is
# MILLISECONDS — the explicit ``s`` suffix is the 1000x guard.
_EXPECTED_RENDERED_OPTION = "-c lock_timeout=10s"

# How long the holding transaction keeps its row lock. The production bound is
# 10 s, so ~1 s leaves ample headroom for the waiter to acquire the lock *if*
# there were no bound at all. The pre-fix tree has no bound and the waiter would
# block until this sleep ends and then succeed — which is exactly the RED
# signature this test's deadline guard converts into a fast failure.
_HOLD_SECONDS = 1.0

# Wall-clock ceiling for the waiter to observe a bounded failure. Well above the
# 10 s production value plus scheduling jitter, but far below anything that would
# let an unbounded wait "pass". The asserting thread does the timed join so a
# never-returning waiter cannot hang the suite.
_WAITER_DEADLINE_SECONDS = 20.0


class TestLockWaitIsBounded:
    """A contended row lock fails within the configured bound."""

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.concurrent
    def test_lock_wait_is_bounded(self, seller, category, city) -> None:
        """A second connection waiting on a held row lock fails with 55P03.

        The main thread holds ``SELECT ... FOR UPDATE`` on one row inside a real
        transaction. A second connection (the worker thread) then issues its own
        ``SELECT ... FOR UPDATE`` on the same row. With the connection-level
        ``lock_timeout`` in force the waiter must raise ``OperationalError``
        whose driver cause is ``psycopg.errors.LockNotAvailable`` (SQLSTATE
        ``55P03``) — not block until the holder releases.

        The waiting work runs on a worker thread joined by this thread with a
        deadline: against the pre-fix code (no bound) the waiter never returns,
        so the test fails on the deadline instead of hanging the suite.
        """
        ad = create_test_ad(seller, category, city)
        ad_id = ad.id

        started = threading.Event()
        outcome: dict[str, BaseException | None] = {"exc": None}
        waiter_returned = threading.Event()

        def contend() -> None:
            """Worker thread: block on the row lock, capture any error."""
            try:
                started.set()
                with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - django-stubs not installed; Atomic lacks CM stubs
                    from apps.ads.models import Ad

                    Ad.objects.select_for_update().get(pk=ad_id)
            except BaseException as exc:  # noqa: BLE001 - record, then assert
                outcome["exc"] = exc
            finally:
                waiter_returned.set()
                connection.close()

        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - django-stubs not installed; Atomic lacks CM stubs
            from apps.ads.models import Ad

            locked_ad = Ad.objects.select_for_update().get(pk=ad_id)
            assert locked_ad.id == ad_id

            thread = threading.Thread(target=contend)
            thread.start()
            assert started.wait(timeout=5), "worker thread did not start"

            # Bounded join: the worker must fail *while the lock is still held*.
            # Raise the deadline to > the hold so an unbounded waiter has time
            # to return (successfully) and be caught, rather than simply being
            # reported as "not yet finished".
            returned_in_time = waiter_returned.wait(
                timeout=_WAITER_DEADLINE_SECONDS
            )

            # Hold the lock for a short, explicit window regardless, so the
            # pre-fix "waiter succeeds once the holder commits" path is
            # exercised and produces the honest RED failure below.
            if not returned_in_time:
                threading.Event().wait(timeout=_HOLD_SECONDS)

        thread.join(timeout=_WAITER_DEADLINE_SECONDS)
        if thread.is_alive():
            pytest.fail("lock wait was not bounded: the waiter never returned")

        assert returned_in_time, (
            "lock wait was not bounded: the waiter did not return within "
            f"{_WAITER_DEADLINE_SECONDS:.0f}s while the lock holder was still "
            "holding the row lock (pre-fix behaviour: it should have failed "
            "with SQLSTATE 55P03)"
        )

        exc = outcome["exc"]
        assert exc is not None, (
            "the contending SELECT ... FOR UPDATE succeeded — the lock wait was "
            "not bounded and the waiter acquired the lock only after the holder "
            "released it"
        )
        assert isinstance(exc, OperationalError), (
            f"expected django.db.OperationalError, got {type(exc).__name__}: {exc!r}"
        )
        assert getattr(exc.__cause__, "sqlstate", None) == "55P03", (
            "expected SQLSTATE 55P03 (lock_timeout / LockNotAvailable) on the "
            f"driver cause, got {exc.__cause__!r}"
        )


class TestDatabaseOptionsRenderTheBound:
    """The rendered ``options`` string carries the unit (1000x guard)."""

    def test_options_carry_explicit_seconds_suffix(self) -> None:
        """``DATABASES`` renders ``-c lock_timeout=<N>s``, never a bare number."""
        from django.conf import settings

        options = settings.DATABASES["default"]["OPTIONS"]
        rendered = options["options"]
        assert rendered == _EXPECTED_RENDERED_OPTION, (
            f"expected {_EXPECTED_RENDERED_OPTION!r}, got {rendered!r}. A bare "
            "PostgreSQL GUC number is MILLISECONDS — the 's' suffix is "
            "load-bearing."
        )

    def test_lock_timeout_seconds_negative_is_clamped_to_disabled(self) -> None:
        """A negative ``LOCK_TIMEOUT_SECONDS`` degrades to 0, not a boot crash.

        PostgreSQL FATALs every process on a negative ``lock_timeout`` (it is
        outside ``0 ms .. 2147483647 ms``); the helper clamps the value to ``0``
        so a bad env value disables the bound instead.
        """
        import config.settings.base as base

        original = base.LOCK_TIMEOUT_SECONDS
        try:
            base.LOCK_TIMEOUT_SECONDS = -1000
            assert base._db_options()["options"] == "-c lock_timeout=0s"
        finally:
            base.LOCK_TIMEOUT_SECONDS = original

    def test_lock_timeout_seconds_default_is_nonzero(self) -> None:
        """The shipped default leaves the bound enabled (0 would disable it)."""
        from config.settings.base import LOCK_TIMEOUT_SECONDS

        assert LOCK_TIMEOUT_SECONDS != 0

    def test_prepare_threshold_is_preserved(self) -> None:
        """The PgBouncer async-safety key survives the OPTIONS change."""
        from django.conf import settings

        options = settings.DATABASES["default"]["OPTIONS"]
        assert options["prepare_threshold"] is None

    def test_discrete_postgres_branch_options_shape_matches(self) -> None:
        """BOTH ``DATABASES`` branches build their OPTIONS from one helper.

        The ``DATABASE_URL`` branch is the live one in every deployment; the
        discrete ``POSTGRES_*`` branch is parsed by prod.py subprocesses and
        tests. Both must express the bound identically.
        """
        from config.settings.base import _db_options

        assert _db_options() == {
            "prepare_threshold": None,
            "options": _EXPECTED_RENDERED_OPTION,
        }


class TestIsLockTimeoutPredicate:
    """The shared classifier matches 55P03 only, on ``__cause__``."""

    def test_lock_not_available_is_a_lock_timeout(self) -> None:
        import psycopg

        from apps.core.utils.db_lock_timeout import is_lock_timeout

        wrapped = OperationalError("canceling statement due to lock timeout")
        wrapped.__cause__ = psycopg.errors.LockNotAvailable(
            "canceling statement due to lock timeout"
        )
        assert is_lock_timeout(wrapped)

    def test_statement_timeout_is_not_a_lock_timeout(self) -> None:
        """A ``statement_timeout`` (SQLSTATE 57014) is a different policy."""
        import psycopg

        from apps.core.utils.db_lock_timeout import is_lock_timeout

        wrapped = OperationalError("canceling statement due to statement timeout")
        wrapped.__cause__ = psycopg.errors.QueryCanceled(
            "canceling statement due to statement timeout"
        )
        assert not is_lock_timeout(wrapped)

    def test_connection_refused_is_not_a_lock_timeout(self) -> None:
        """A connection refusal must keep its existing behaviour."""
        import psycopg

        from apps.core.utils.db_lock_timeout import is_lock_timeout

        wrapped = OperationalError(
            "connection failed: Connection refused"
        )
        wrapped.__cause__ = psycopg.OperationalError("connection refused")
        assert not is_lock_timeout(wrapped)

    def test_bare_error_without_cause_is_not_a_lock_timeout(self) -> None:
        """No wrapped driver error means no 55P03 to find."""
        from apps.core.utils.db_lock_timeout import is_lock_timeout

        assert not is_lock_timeout(OperationalError("server closed the connection"))
        assert not is_lock_timeout(ValueError("not a db error"))

    def test_message_text_alone_does_not_match(self) -> None:
        """The message is never string-matched (locale/version fragile)."""
        from apps.core.utils.db_lock_timeout import is_lock_timeout

        exc = OperationalError("canceling statement due to lock timeout")
        assert not is_lock_timeout(exc)
