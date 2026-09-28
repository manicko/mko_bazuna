#!/usr/bin/env python
"""Scheduler module — hourly sweep + daily job dispatch loop.

Extracted from the inline ``python -c`` block in ``docker/entrypoint-scheduler.sh``.
Mirrors the ``migrate_locked.py`` utility-module pattern: ``main()`` calls
``django.setup()``, resolves ``manage.py`` via ``Path(__file__).resolve().parents[3]``,
and dispatches management commands via ``subprocess``.

Design (Block A — faithful extraction):
  * ``HOURLY_COMMANDS`` / ``DAILY_COMMANDS`` — module-level constants preserving
    the exact command lists from the inline script.
  * ``should_run_daily()`` — pure, independently testable timing predicate.
  * ``run_one_cycle()`` — unit-testable single tick (no infinite loop, no sleep).
    On a clean daily cycle it **writes** the durable daily marker (see below);
    it does **not** re-read it — the read is a start-up concern in
    :func:`run_scheduler`.
  * ``run_scheduler()`` — production infinite loop with injectable
    ``sleep_func`` / ``now_func`` / ``run_command_fn`` for testability. The
    inter-cycle wait is backed by the module stop event (interruptible), and a
    stop request short-circuits the commands not yet started in the current
    cycle (see :func:`_stop_aware_dispatch`).
  * ``main()`` — Django setup + entry point for standalone / Docker execution.

Durable daily-dispatch marker: the daily set fires once per calendar day per
*recorded success*, not once per process. The completion date lives in the
``scheduler_daily_state`` singleton row (see
``apps.core.services.scheduler_daily_state``), not process memory.
``main()`` constructs the DB-backed marker and injects it; the unit suite
injects a recording double that satisfies the :class:`DailyMarker` protocol.

The original ``check=False`` and ``except Exception: pass`` semantics are
preserved; structured logging and exit-code inspection are added in Block B.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import threading
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class DailyMarker(Protocol):
    """Read/write seam over the durable daily-dispatch marker.

    Declared here (rather than imported) so the module keeps its Django-free
    import surface with zero app-level imports. ``read_last_daily`` is the
    start-up read in :func:`run_scheduler`; ``record_daily`` is the write in
    :func:`run_one_cycle` after a clean daily cycle. See
    ``apps.core.services.scheduler_daily_state`` for the production
    implementation.
    """

    def read_last_daily(self) -> date | None:
        """Return the date the daily set last completed, or ``None``."""
        ...

    def record_daily(self, day: date) -> None:
        """Record *day* as the date the daily set completed."""
        ...


# Set by the SIGTERM/SIGINT handler (in main()) to request a graceful break
# of the run_scheduler() while-True loop. Signal handlers run in the main
# thread; run_scheduler() also runs in the main thread, so a threading.Event
# is the safe, idiomatic handoff (no cross-thread locking concerns).
_stop_event = threading.Event()


def _handle_shutdown_signal(signum: int, frame: Any) -> None:
    """Minimal SIGTERM/SIGINT handler: set the stop flag and let the loop break.

    Deliberately does only logging + flag-setting (no I/O, no DB work) so the
    handler stays async-signal-safe in practice; all teardown happens in main().
    """
    logger.info("Received signal %s; requesting graceful scheduler shutdown", signum)
    _stop_event.set()

# Phase 4 hourly sweeps + Phase 2 purges (run every hour)
HOURLY_COMMANDS: list[str] = [
    "archive_sweep",
    "delete_sweep",
    "consent_hard_delete",
    "sweep_drafts",
    "sweep_orphaned_media",
    "cleanup_login_tokens",
    "purge_failed_ads",
    "purge_rejected_ads",
    "purge_deleted_ads",
]

# Daily at 08:00 UTC — first hourly tick >= 08:00 UTC each calendar day.
# ``send_alerts`` is the search-alert delivery task; ``rollup_daily_metrics``
# is the daily analytics rollup (AdvisoryLockId.ROLLUP_DAILY_METRICS).
DAILY_COMMANDS: list[str] = [
    "send_alerts",
    "rollup_daily_metrics",
]

# Daily threshold hour (UTC). Daily commands fire on the first hourly tick
# at or after this hour each calendar day.
DAILY_HOUR_UTC: int = 8

# Ticks every hour (3600 seconds).
SCHEDULE_INTERVAL_SECONDS: float = 3600.0


def _utcnow() -> datetime:
    """Return current UTC time (injectable in tests via ``now_func``)."""
    return datetime.now(UTC)


def should_run_daily(
    now: datetime,
    last_daily: date | None,
    daily_hour_utc: int,
) -> bool:
    """Return ``True`` if daily commands should fire on this tick.

    Daily commands run once per calendar day, at the first hourly tick >= ``daily_hour_utc``.
    On the very first run (``last_daily is None``), they fire only if ``now.hour >= daily_hour_utc``.
    On subsequent days, they fire only if ``now.date()`` differs from ``last_daily``
    **and** ``now.hour >= daily_hour_utc``.

    If it is a new calendar day but *before* the threshold hour, ``last_daily`` is
    **not** updated — the check re-evaluates on the next tick. This preserves the
    "first hourly tick >= 08:00 UTC" semantics from the original inline script.
    """
    if last_daily is None or now.date() != last_daily:
        return now.hour >= daily_hour_utc
    return False


def _validate_commands(command_names: list[str]) -> None:
    """Verify all scheduled command names are discoverable by Django.

    Fail-fast at scheduler startup: if a command module is removed/renamed but
    the scheduler list isn't updated, the scheduler would silently subprocess
    into a crash loop (``manage.py <name>`` prints an error and exits non-zero).
    ``get_commands()`` is ``functools.cache``'d, so this is a one-time cost.

    Import is deferred to runtime (inside ``main`` / ``_validate_commands``) so
    that the module can be imported without a configured Django environment,
    enabling pure unit tests of timing and dispatch logic.
    """
    from django.core.management import CommandError, get_commands

    available = get_commands()
    missing = [name for name in command_names if name not in available]
    if missing:
        raise CommandError(f"Unreachable scheduler commands: {missing}")


def _default_manage_py() -> Path:
    """Resolve ``manage.py`` relative to this file (``src/backend/manage.py``).

    ``scheduler.py`` lives at ``src/backend/apps/core/utils/scheduler.py``;
    ``parents[3]`` is ``src/backend/`` so the result is ``src/backend/manage.py``.
    """
    return Path(__file__).resolve().parents[3] / "manage.py"


def _run_command_subprocess(name: str, manage_py: Path, python_executable: str) -> int:
    """Dispatch a single management command via ``subprocess.run``.

    Uses ``check=False`` (faithful to the original inline script) so that a
    non-zero exit code does **not** raise — the scheduler continues to the
    next command regardless. Returns the subprocess exit code.

    A ``SCHEDULER_COMMAND_TIMEOUT`` timeout is enforced so a hung command
    cannot stall the cycle (ENT-001). On ``TimeoutExpired`` the subprocess is
    terminated, an error is logged, and ``1`` is returned so ``_dispatch``
    continues to the next command.
    """
    from django.conf import settings

    timeout = settings.SCHEDULER_COMMAND_TIMEOUT
    cmd = [python_executable, str(manage_py), name]
    logger.info("Running management command: %s", name)
    try:
        result = subprocess.run(cmd, check=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        logger.error("Command %s timed out after %s seconds", name, timeout)
        return 1
    if result.returncode != 0:
        logger.error("Command %s exited with code %d", name, result.returncode)
    return result.returncode


def _dispatch(
    cmd: str,
    run_command: Callable[[str], int],
) -> int:
    """Dispatch a single command, isolating per-command failures.

    A per-command ``try/except`` ensures one command's exception (e.g.
    ``FileNotFoundError`` if the Python executable vanishes mid-run) does not
    skip the remaining commands in the cycle. This is a structural improvement
    over the original loop-level ``try/except Exception: pass`` while preserving
    the "never crash the scheduler on an individual command failure" intent.
    """
    try:
        return run_command(cmd)
    except Exception:
        logger.exception("Failed to dispatch command %s", cmd)
        return 1


def _write_liveness_marker() -> None:
    """Write the scheduler liveness marker file (for Docker healthcheck).

    Fail-open: if the marker path is empty or the write fails, log at debug
    level and continue — the scheduler must never crash on a healthcheck concern.
    """
    from django.conf import settings

    marker = getattr(settings, "SCHEDULER_LIVENESS_FILE", "")
    if not marker:
        return
    try:
        Path(marker).touch()
        logger.debug("Scheduler liveness marker updated: %s", marker)
    except OSError as exc:
        logger.debug("Could not update scheduler liveness marker %s: %s", marker, exc)


def run_one_cycle(
    *,
    now_func: Callable[[], datetime] = _utcnow,
    run_command: Callable[[str], int],
    last_daily: date | None,
    daily_marker: DailyMarker,
) -> date | None:
    """Execute one scheduler tick.

    Dispatches all hourly commands unconditionally. If ``should_run_daily()``
    returns ``True``, dispatches all daily commands and, only when every daily
    command exited 0 with no stop requested, records the day on
    ``daily_marker`` and returns it as the new ``last_daily``. No infinite
    loop, no sleep — pure unit-testable function.

    Args:
        now_func: Callable returning ``datetime`` (injectable for tests).
        run_command: Callable dispatching a single command name (injectable
            mock in tests, ``_run_command_subprocess`` in production).
        last_daily: The date the daily commands were last dispatched, or
            ``None`` on first run.
        daily_marker: The durable daily-dispatch marker seam (``DailyMarker``
            protocol). Written only on a clean daily cycle; never re-read here
            (the read is a start-up concern in :func:`run_scheduler`).

    Returns:
        The new ``last_daily`` value. It is ``now.date()`` **only** when the
        daily set was dispatched **and** every daily command exited 0 **and**
        no stop was requested; otherwise the previous value unchanged, so the
        next hourly tick retries. A failing daily command leaves the marker
        untouched and is retried (bounded ~16 attempts/day); both daily
        commands are idempotent after the delivery fix, and a failing
        ``rollup_daily_metrics`` genuinely should be retried.
    """
    now = now_func()

    # Hourly commands — run every tick
    for cmd in HOURLY_COMMANDS:
        _dispatch(cmd, run_command)

    # Write liveness marker after hourly cycle completes (before daily section).
    # Fail-open: if the path is empty or the write fails, the scheduler continues.
    _write_liveness_marker()

    # Daily commands — once per calendar day at/after 08:00 UTC
    new_last_daily = last_daily
    if should_run_daily(now, last_daily, DAILY_HOUR_UTC):
        # Dispatch EVERY daily command before judging the outcome: the list is
        # deliberate. all(_dispatch(c, r) == 0 for c in DAILY_COMMANDS) would
        # short-circuit on the first failure and skip the remaining commands.
        daily_exit_codes = [_dispatch(cmd, run_command) for cmd in DAILY_COMMANDS]
        daily_ok = all(code == 0 for code in daily_exit_codes)
        # The stop-flag check is load-bearing: _stop_aware_dispatch returns 0
        # for every command it declines, so exit codes alone cannot reveal that
        # the daily set never actually ran.
        if _stop_event.is_set():
            logger.warning(
                "Stop requested during the daily cycle for %s - the daily marker "
                "is left unchanged so the daily set re-runs on the next start",
                now.date().isoformat(),
            )
        elif not daily_ok:
            logger.warning(
                "Daily commands for %s did not all succeed (exit codes %s) - the "
                "daily marker is left unchanged and the set is retried on the next "
                "hourly tick",
                now.date().isoformat(),
                daily_exit_codes,
            )
        else:
            day = now.date()
            # Order matters: the durable record is attempted first, then the
            # in-memory carrier advances. record_daily is fail-open, so a marker
            # failure never blocks the tick; the cost is that this process will
            # not retry within the day, and the next start will re-run the set.
            daily_marker.record_daily(day)
            new_last_daily = day
            logger.info(
                "Daily commands completed for %s - durable marker recorded",
                day.isoformat(),
            )

    return new_last_daily


def _build_subprocess_runner(manage_py: Path, python_executable: str) -> Callable[[str], int]:
    """Create a ``run_command`` callable bound to a specific manage.py path.

    Returns a function that dispatches a single management command via
    :func:`_run_command_subprocess`. Used by :func:`run_scheduler` when no
    explicit ``run_command_fn`` is injected.
    """
    def run_command(name: str) -> int:
        return _run_command_subprocess(name, manage_py, python_executable)

    return run_command


def _wait_for_interval(seconds: float) -> None:
    """Wait up to ``seconds``, returning early once shutdown has been requested.

    The default ``sleep_func`` of :func:`run_scheduler`. Blocking on the module
    ``_stop_event`` rather than on ``time.sleep`` makes the inter-cycle wait
    interruptible: ``_handle_shutdown_signal`` sets the event, this returns
    immediately, and the loop's top-of-iteration check breaks the cycle. If the
    event is already set when the wait is reached, the wait returns at once.

    A caller-supplied ``sleep_func`` replaces this entirely and owns the wait
    semantics for the whole loop — see :func:`run_scheduler`.
    """
    _stop_event.wait(seconds)


def _stop_aware_dispatch(
    run_command: Callable[[str], int],
) -> Callable[[str], int]:
    """Wrap a command dispatcher so it declines work once shutdown is requested.

    :func:`run_scheduler` hands the returned callable to :func:`run_one_cycle`
    in place of the raw dispatcher, so a stop request arriving *during* a cycle
    short-circuits the commands that have not started yet instead of waiting
    out every remaining command. The command already in flight is never
    interrupted; its child process runs to completion under the existing
    ``SCHEDULER_COMMAND_TIMEOUT``.

    Skipped commands are not lost work: the loop runs a full cycle on its first
    iteration after start, and the service is restarted immediately after a
    graceful stop, so every skipped sweep runs on the next start.

    Returns the wrapped dispatcher's exit code unchanged. A skipped command
    returns ``0`` — nothing failed, it was deliberately not run — and that
    ``0`` is now **load-bearing**, because the daily gate in
    :func:`run_one_cycle` combines "all daily exit codes are 0" with an
    explicit ``_stop_event.is_set()`` check, since exit codes alone cannot
    distinguish a skipped command from a successful one.
    """
    def dispatch(name: str) -> int:
        if _stop_event.is_set():
            logger.info("Stop requested — skipping remaining command %s", name)
            return 0
        return run_command(name)

    return dispatch


def run_scheduler(
    manage_py: str | Path | None = None,
    python_executable: str | None = None,
    sleep_func: Callable[[float], None] = _wait_for_interval,
    now_func: Callable[[], datetime] = _utcnow,
    run_command_fn: Callable[[str], int] | None = None,
    interval_seconds: float = SCHEDULE_INTERVAL_SECONDS,
    *,
    daily_marker: DailyMarker,
) -> None:
    """Infinite scheduler loop — hourly sweeps + daily jobs.

    Delegates to :func:`run_one_cycle` each tick, then waits
    ``interval_seconds``. All collaborators are injectable for testability.

    Shutdown contract: a stop request (SIGTERM/SIGINT, handled by
    :func:`_handle_shutdown_signal`) is observed at two points. The inter-cycle
    wait is interruptible — the default ``sleep_func`` blocks on the module stop
    event, so the flag ends the wait immediately instead of at the end of the
    interval. A flag set *during* a cycle short-circuits the commands that have
    not started yet (see :func:`_stop_aware_dispatch`); the command already in
    flight is never interrupted and runs to completion under
    ``SCHEDULER_COMMAND_TIMEOUT``. The loop then breaks at its next top-of-loop
    check, so a stop is bounded by one in-flight command rather than by the
    interval.

    Args:
        manage_py: Path to ``manage.py`` (auto-resolved if ``None``).
        python_executable: Python binary for subprocess dispatch
            (defaults to ``sys.executable``).
        sleep_func: Callable invoked once per cycle to wait out
            ``interval_seconds``. The default (:func:`_wait_for_interval`)
            returns early as soon as a stop is requested. A caller-supplied
            ``sleep_func`` takes over the wait entirely and therefore owns the
            stop semantics for the whole loop: it must return control to the
            loop within ``interval_seconds`` and must not block past a stop
            request, or the loop will never observe the flag. Tests that inject
            a no-op wait own their own termination — raise, or set the module
            stop event.
        now_func: Time callable for daily-scheduling decisions.
        run_command_fn: Command dispatch callable (inject a mock to avoid
            subprocess spawns in tests). It is wrapped by
            :func:`_stop_aware_dispatch` before being handed to
            :func:`run_one_cycle`.
        interval_seconds: Tick interval in seconds (default 3600).
        daily_marker: The durable daily-dispatch marker seam (``DailyMarker``
            protocol). Required, with no default: a ``None`` default would be a
            silent no-op that reintroduces the exact defect this seam prevents
            (the daily set re-running every tick). ``last_daily`` is recovered
            from this marker at start-up rather than assumed ``None``; a read
            failure reports ``None`` so the set **runs** — a marker problem must
            re-run, never skip.
    """
    python_executable = python_executable or sys.executable
    resolved_manage_py = Path(manage_py) if manage_py else _default_manage_py()
    if run_command_fn is None:
        run_command_fn = _build_subprocess_runner(resolved_manage_py, python_executable)

    dispatch = _stop_aware_dispatch(run_command_fn)

    # Fail-fast: validate all scheduled commands are discoverable before
    # entering the infinite loop. Prevents silent crash-loops.
    _validate_commands(HOURLY_COMMANDS + DAILY_COMMANDS)

    logger.info("Scheduler started (interval=%s seconds)", interval_seconds)
    # Recover the last daily-completion date from the durable marker rather
    # than assuming None. A read failure reports None, which makes the daily
    # set run on the first tick at/after DAILY_HOUR_UTC — a marker problem must
    # cause a re-run, never a silent skip.
    last_daily = daily_marker.read_last_daily()
    if last_daily is None:
        logger.info(
            "No scheduler daily marker found - the daily set will run on the "
            "first tick at/after %02d:00 UTC",
            DAILY_HOUR_UTC,
        )
    else:
        logger.info(
            "Recovered scheduler daily marker - daily set last completed %s",
            last_daily.isoformat(),
        )
    while True:
        if _stop_event.is_set():
            logger.info("Stop flag set — exiting scheduler loop after completed cycle")
            break
        try:
            last_daily = run_one_cycle(
                now_func=now_func,
                run_command=dispatch,
                last_daily=last_daily,
                daily_marker=daily_marker,
            )
        except Exception:
            logger.exception("Scheduler cycle failed — continuing")
        sleep_func(interval_seconds)


def _shutdown() -> None:
    """Graceful shutdown teardown: close Django DB connections and log.

    Called from main() after run_scheduler() returns (loop broken via signal).
    Kept separate from run_scheduler() so the loop stays pure/Django-free and
    remains unit-testable without a configured Django DB. Import of
    ``django.db.connections`` is deferred to runtime to preserve the module's
    "importable without Django configured" property.
    """
    from django.db import connections

    connections.close_all()
    logger.info("Scheduler shutdown complete; DB connections closed")


def main() -> int:
    """Entry point for standalone / Docker execution.

    Mirrors ``migrate_locked.py``: ``django.setup()`` inside ``main()``,
    ``DJANGO_SETTINGS_MODULE`` defaults to the production settings module.
    Django-dependent imports are deferred to runtime so the module itself
    can be imported without Django configured.

    Registers SIGTERM/SIGINT handlers before entering the scheduler loop and
    runs graceful teardown (:func:`_shutdown`) in a ``finally`` block so DB
    connections are always closed when the loop exits.

    After ``django.setup()`` the DB-backed daily marker
    (``SchedulerDailyMarker``) is constructed and injected into
    :func:`run_scheduler`. The import is deferred to runtime (and to after
    ``django.setup()``) because the marker's class imports the Django ORM; its
    construction touches no database.
    """
    import django

    from apps.core.services.scheduler_daily_state import SchedulerDailyMarker

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")
    django.setup()

    signal.signal(signal.SIGTERM, _handle_shutdown_signal)
    signal.signal(signal.SIGINT, _handle_shutdown_signal)

    try:
        run_scheduler(daily_marker=SchedulerDailyMarker())
    finally:
        _shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
