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
  * ``run_scheduler()`` — production infinite loop with injectable
    ``sleep_func`` / ``now_func`` / ``run_command_fn`` for testability.
  * ``main()`` — Django setup + entry point for standalone / Docker execution.

The original ``check=False`` and ``except Exception: pass`` semantics are
preserved; structured logging and exit-code inspection are added in Block B.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

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
# will be added here in a follow-up block (ENT-003).
DAILY_COMMANDS: list[str] = [
    "send_alerts",
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

    Structured logging and exit-code inspection are added in Block B.
    """
    cmd = [python_executable, str(manage_py), name]
    logger.debug("Running %s", " ".join(cmd))
    result = subprocess.run(cmd, check=False)
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
        logger.debug("Failed to dispatch command %s", cmd, exc_info=True)
        return 1


def run_one_cycle(
    *,
    now_func: Callable[[], datetime] = _utcnow,
    run_command: Callable[[str], int],
    last_daily: date | None,
) -> date | None:
    """Execute one scheduler tick.

    Dispatches all hourly commands unconditionally. If ``should_run_daily()``
    returns ``True``, dispatches all daily commands and updates ``last_daily``
    to today's date. No infinite loop, no sleep — pure unit-testable function.

    Args:
        now_func: Callable returning ``datetime`` (injectable for tests).
        run_command: Callable dispatching a single command name (injectable
            mock in tests, ``_run_command_subprocess`` in production).
        last_daily: The date the daily commands were last dispatched, or
            ``None`` on first run.

    Returns:
        The updated ``last_daily`` value — ``now.date()`` if daily commands
        ran, otherwise the previous ``last_daily`` unchanged.
    """
    now = now_func()

    # Hourly commands — run every tick
    for cmd in HOURLY_COMMANDS:
        _dispatch(cmd, run_command)

    # Daily commands — once per calendar day at/after 08:00 UTC
    new_last_daily = last_daily
    if should_run_daily(now, last_daily, DAILY_HOUR_UTC):
        for cmd in DAILY_COMMANDS:
            _dispatch(cmd, run_command)
        new_last_daily = now.date()

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


def run_scheduler(
    manage_py: str | Path | None = None,
    python_executable: str | None = None,
    sleep_func: Callable[[float], None] = time.sleep,
    now_func: Callable[[], datetime] = _utcnow,
    run_command_fn: Callable[[str], int] | None = None,
    interval_seconds: float = SCHEDULE_INTERVAL_SECONDS,
) -> None:
    """Infinite scheduler loop — hourly sweeps + daily jobs.

    Delegates to :func:`run_one_cycle` each tick, then sleeps
    ``interval_seconds``. All collaborators are injectable for testability:

    Args:
        manage_py: Path to ``manage.py`` (auto-resolved if ``None``).
        python_executable: Python binary for subprocess dispatch
            (defaults to ``sys.executable``).
        sleep_func: Sleep callable (inject ``lambda s: None`` in tests to
            make the loop terminate quickly).
        now_func: Time callable for daily-scheduling decisions.
        run_command_fn: Command dispatch callable (inject a mock to avoid
            subprocess spawns in tests).
        interval_seconds: Tick interval in seconds (default 3600).
    """
    python_executable = python_executable or sys.executable
    resolved_manage_py = Path(manage_py) if manage_py else _default_manage_py()
    if run_command_fn is None:
        run_command_fn = _build_subprocess_runner(resolved_manage_py, python_executable)

    # Fail-fast: validate all scheduled commands are discoverable before
    # entering the infinite loop. Prevents silent crash-loops.
    _validate_commands(HOURLY_COMMANDS + DAILY_COMMANDS)

    logger.info("Scheduler started (interval=%s seconds)", interval_seconds)
    last_daily: date | None = None
    while True:
        try:
            last_daily = run_one_cycle(
                now_func=now_func,
                run_command=run_command_fn,
                last_daily=last_daily,
            )
        except Exception:
            logger.debug("Scheduler cycle failed — continuing", exc_info=True)
        sleep_func(interval_seconds)


def main() -> int:
    """Entry point for standalone / Docker execution.

    Mirrors ``migrate_locked.py``: ``django.setup()`` inside ``main()``,
    ``DJANGO_SETTINGS_MODULE`` defaults to the production settings module.
    Django-dependent imports are deferred to runtime so the module itself
    can be imported without Django configured.
    """
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")
    django.setup()

    run_scheduler()
    return 0


if __name__ == "__main__":
    sys.exit(main())
