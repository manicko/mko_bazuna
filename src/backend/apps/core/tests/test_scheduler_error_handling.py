"""Tests for scheduler structured logging, exit-code inspection, and marker file.

Covers the Block B enhancements to ``apps.core.utils.scheduler``:
  * ``_run_command_subprocess`` — logger.info on dispatch, logger.error on non-zero exit.
  * ``_dispatch`` — logger.exception on per-command failure (ERROR level).
  * ``run_one_cycle`` — error isolation (continues past per-command failures).
  * ``_write_liveness_marker`` + ``run_one_cycle`` — liveness marker file behavior.

All tests are pure unit tests (``pytest.mark.unit``) — no database, no
subprocess. ``subprocess.run`` and ``_write_liveness_marker`` are mocked where needed.
"""

from __future__ import annotations

import logging
import os
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings

import apps.core.utils.scheduler as scheduler_mod
from apps.core.utils.scheduler import (
    DAILY_COMMANDS,
    HOURLY_COMMANDS,
    _build_subprocess_runner,
    _dispatch,
    _run_command_subprocess,
    _stop_aware_dispatch,
    _write_liveness_marker,
    run_one_cycle,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    """Build a timezone-aware UTC datetime for tests."""
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def _noop_command(_name: str) -> int:
    """A run_command stub that always returns 0."""
    return 0


# ---------------------------------------------------------------------------
# _run_command_subprocess — structured logging + exit-code inspection
# ---------------------------------------------------------------------------


class TestRunCommandLogging:
    """Verify _run_command_subprocess logs dispatch + exit codes."""

    def test_run_command_logs_dispatch(
        self,
        caplog: pytest.LogCaptureFixture,
        tmp_path: Path,
    ) -> None:
        """logger.info fired with 'Running management command' before dispatch."""
        fake_result = MagicMock(returncode=0)
        with patch(
            "apps.core.utils.scheduler.subprocess.run",
            return_value=fake_result,
        ):
            with caplog.at_level(
                logging.INFO, logger="apps.core.utils.scheduler"
            ):
                _run_command_subprocess(
                    "test_cmd", tmp_path / "manage.py", "python"
                )

        assert any(
            "Running management command" in record.message
            and record.levelno == logging.INFO
            for record in caplog.records
        )

    def test_run_command_logs_error_on_nonzero_exit(
        self,
        caplog: pytest.LogCaptureFixture,
        tmp_path: Path,
    ) -> None:
        """logger.error fired with exit code on non-zero return."""
        fake_result = MagicMock(returncode=42)
        with patch(
            "apps.core.utils.scheduler.subprocess.run",
            return_value=fake_result,
        ):
            with caplog.at_level(
                logging.ERROR, logger="apps.core.utils.scheduler"
            ):
                _run_command_subprocess(
                    "test_cmd", tmp_path / "manage.py", "python"
                )

        assert any(
            "exited with code 42" in record.message
            and record.levelno == logging.ERROR
            for record in caplog.records
        )

    def test_run_command_does_not_log_error_on_success(
        self,
        caplog: pytest.LogCaptureFixture,
        tmp_path: Path,
    ) -> None:
        """No logger.error fired when subprocess exits with code 0."""
        fake_result = MagicMock(returncode=0)
        with patch(
            "apps.core.utils.scheduler.subprocess.run",
            return_value=fake_result,
        ):
            with caplog.at_level(
                logging.ERROR, logger="apps.core.utils.scheduler"
            ):
                _run_command_subprocess(
                    "test_cmd", tmp_path / "manage.py", "python"
                )

        assert not any(
            record.levelno == logging.ERROR for record in caplog.records
        )

    def test_run_command_returns_exit_code(self, tmp_path: Path) -> None:
        """Exit code from subprocess.run is returned."""
        fake_result = MagicMock(returncode=42)
        with patch(
            "apps.core.utils.scheduler.subprocess.run",
            return_value=fake_result,
        ) as mock_run:
            rc = _run_command_subprocess(
                "test_cmd", tmp_path / "manage.py", "python"
            )
            assert rc == 42
            mock_run.assert_called_once()

    def test_run_command_returns_zero_on_success(self, tmp_path: Path) -> None:
        """Zero exit code returned when subprocess succeeds."""
        fake_result = MagicMock(returncode=0)
        with patch(
            "apps.core.utils.scheduler.subprocess.run",
            return_value=fake_result,
        ):
            rc = _run_command_subprocess(
                "test_cmd", tmp_path / "manage.py", "python"
            )
        assert rc == 0


# ---------------------------------------------------------------------------
# _run_command_subprocess — configurable timeout handling (ENT-001)
# ---------------------------------------------------------------------------


class TestTimeoutHandling:
    """Verify the configurable subprocess timeout and TimeoutExpired handling."""

    def test_run_command_forwards_timeout_kwarg(self, tmp_path: Path) -> None:
        """subprocess.run receives timeout=settings.SCHEDULER_COMMAND_TIMEOUT."""
        fake_result = MagicMock(returncode=0)
        with patch(
            "apps.core.utils.scheduler.subprocess.run",
            return_value=fake_result,
        ) as mock_run:
            _run_command_subprocess("test_cmd", tmp_path / "manage.py", "python")

        mock_run.assert_called_once()
        _, kwargs = mock_run.call_args
        assert kwargs.get("timeout") == settings.SCHEDULER_COMMAND_TIMEOUT

    def test_run_command_timeout_logs_error_and_returns_sentinel(
        self,
        caplog: pytest.LogCaptureFixture,
        tmp_path: Path,
    ) -> None:
        """TimeoutExpired logs an ERROR containing 'timed out' and returns 1."""
        timeout = settings.SCHEDULER_COMMAND_TIMEOUT
        with patch(
            "apps.core.utils.scheduler.subprocess.run",
            side_effect=subprocess.TimeoutExpired(
                cmd=["python", "manage.py", "test_cmd"], timeout=timeout
            ),
        ):
            with caplog.at_level(
                logging.ERROR, logger="apps.core.utils.scheduler"
            ):
                rc = _run_command_subprocess(
                    "test_cmd", tmp_path / "manage.py", "python"
                )

        assert rc == 1
        assert any(
            "timed out" in record.message
            and record.levelno == logging.ERROR
            for record in caplog.records
        )

    def test_run_one_cycle_continues_after_timeout(self, daily_marker, tmp_path: Path) -> None:
        """A TimeoutExpired on one hourly command does not skip the rest."""
        timed_out_command = HOURLY_COMMANDS[2]

        def fake_run(
            cmd: list[str], check: bool = False, timeout: int | None = None
        ) -> MagicMock:
            if cmd[-1] == timed_out_command:
                raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout or 0)
            return MagicMock(returncode=0)

        with patch(
            "apps.core.utils.scheduler.subprocess.run",
            side_effect=fake_run,
        ) as mock_run:
            run_command = _build_subprocess_runner(
                tmp_path / "manage.py", "python"
            )
            now_func = lambda: _utc(2025, 6, 15, 6)  # noqa: E731
            last_daily = run_one_cycle(
                now_func=now_func,
                run_command=run_command,
                last_daily=None,
                daily_marker=daily_marker,
            )

        # All 9 hourly commands were attempted despite the timeout.
        assert mock_run.call_count == len(HOURLY_COMMANDS)
        # Hour < 8, so daily commands must not have fired.
        assert last_daily is None


# ---------------------------------------------------------------------------
# _dispatch — per-command exception isolation + logging
# ---------------------------------------------------------------------------


class TestDispatchIsolation:
    """Verify _dispatch isolates per-command failures."""

    def test_dispatch_catches_exception_and_logs(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Exception is caught, logged via logger.exception, returns 1."""

        def failing_command(_name: str) -> int:
            raise RuntimeError("boom")

        with caplog.at_level(
            logging.ERROR, logger="apps.core.utils.scheduler"
        ):
            result = _dispatch("test_cmd", failing_command)

        assert result == 1
        assert any(
            "Failed to dispatch command" in record.message
            and record.levelno == logging.ERROR
            for record in caplog.records
        )

    def test_dispatch_logs_includes_command_name(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """The failing command name appears in the exception log message."""

        def failing_command(_name: str) -> int:
            raise RuntimeError("crash")

        with caplog.at_level(
            logging.ERROR, logger="apps.core.utils.scheduler"
        ):
            _dispatch("purge_deleted_ads", failing_command)

        assert any(
            "purge_deleted_ads" in record.message
            for record in caplog.records
        )

    def test_dispatch_returns_exit_code_on_success(self) -> None:
        """Normal return code propagated through _dispatch."""

        def success_command(_name: str) -> int:
            return 0

        result = _dispatch("test_cmd", success_command)
        assert result == 0

    def test_dispatch_propagates_nonzero_exit_code(self) -> None:
        """Non-zero exit code from the command is propagated by _dispatch."""

        def nonzero_command(_name: str) -> int:
            return 3

        result = _dispatch("test_cmd", nonzero_command)
        assert result == 3


# ---------------------------------------------------------------------------
# run_one_cycle — error isolation
# ---------------------------------------------------------------------------


class TestCycleErrorIsolation:
    """Verify run_one_cycle continues past per-command failures."""

    def test_hourly_cycle_continues_past_failure(self, daily_marker) -> None:
        """If the 3rd hourly command raises, commands 4-9 are still dispatched."""
        dispatched: list[str] = []

        def mock_run_command(name: str) -> int:
            dispatched.append(name)
            if name == HOURLY_COMMANDS[2]:  # 3rd command (index 2)
                raise RuntimeError("boom")
            return 0

        now_func = lambda: _utc(2025, 6, 15, 0)  # noqa: E731

        run_one_cycle(
            now_func=now_func,
            run_command=mock_run_command,
            last_daily=None,
            daily_marker=daily_marker,
        )

        # All 9 hourly commands were attempted (3rd raised, but _dispatch caught it)
        assert dispatched == HOURLY_COMMANDS

    def test_hourly_failure_does_not_skip_daily(self, daily_marker) -> None:
        """If an hourly command raises, daily commands are still dispatched."""
        dispatched: list[str] = []

        def mock_run_command(name: str) -> int:
            dispatched.append(name)
            if name == HOURLY_COMMANDS[0]:
                raise RuntimeError("hourly boom")
            return 0

        now_func = lambda: _utc(2025, 6, 15, 8)  # noqa: E731

        run_one_cycle(
            now_func=now_func,
            run_command=mock_run_command,
            last_daily=None,
            daily_marker=daily_marker,
        )

        # All hourly commands dispatched despite the first one failing
        assert HOURLY_COMMANDS == dispatched[: len(HOURLY_COMMANDS)]
        # Daily command also dispatched
        assert "send_alerts" in dispatched

    def test_daily_cycle_continues_past_failure(self, daily_marker) -> None:
        """If the daily command raises, the cycle completes but the day is NOT marked.

        The daily set did not complete, so the day must not be recorded.
        Leaving ``last_daily`` unchanged is what makes the next hourly tick
        retry it. (This test was previously green asserting the marker was
        written despite the exception — a test pinning the defect it now guards
        against.)
        """
        dispatched: list[str] = []

        def mock_run_command(name: str) -> int:
            dispatched.append(name)
            if name == DAILY_COMMANDS[0]:
                raise RuntimeError("daily boom")
            return 0

        now_func = lambda: _utc(2025, 6, 15, 8)  # noqa: E731

        result = run_one_cycle(
            now_func=now_func,
            run_command=mock_run_command,
            last_daily=None,
            daily_marker=daily_marker,
        )

        # Daily command was still dispatched (exception caught by _dispatch)
        assert DAILY_COMMANDS[0] in dispatched
        # The daily set did not complete, so the day must NOT be marked. Leaving
        # last_daily unchanged is what makes the next hourly tick retry it.
        assert result is None
        assert daily_marker.recorded == []

    def test_daily_cycle_retries_on_the_next_tick(self, daily_marker) -> None:
        """A failed daily set is retried on the next tick and marked on success."""
        dispatched: list[str] = []
        failed_once = {"done": False}

        def mock_run_command(name: str) -> int:
            dispatched.append(name)
            if name == DAILY_COMMANDS[0] and not failed_once["done"]:
                failed_once["done"] = True
                return 1
            return 0

        now_func = lambda: _utc(2025, 6, 15, 8)  # noqa: E731

        # First tick: DAILY_COMMANDS[0] fails, so the day is NOT marked.
        result1 = run_one_cycle(
            now_func=now_func,
            run_command=mock_run_command,
            last_daily=None,
            daily_marker=daily_marker,
        )
        assert result1 is None
        assert daily_marker.recorded == []

        # Second tick: same recording marker, carrying the first return as
        # last_daily (exactly what the scheduler loop does).
        result2 = run_one_cycle(
            now_func=now_func,
            run_command=mock_run_command,
            last_daily=result1,
            daily_marker=daily_marker,
        )

        # Both daily commands were dispatched on BOTH ticks — no short-circuit.
        assert dispatched.count(DAILY_COMMANDS[0]) == 2
        assert dispatched.count(DAILY_COMMANDS[1]) == 2
        # Marked exactly once, on the successful retry.
        assert daily_marker.recorded == [date(2025, 6, 15)]
        assert result2 == date(2025, 6, 15)


# ---------------------------------------------------------------------------
# _write_liveness_marker — fail-open marker file behavior
# ---------------------------------------------------------------------------


class TestWriteLivenessMarker:
    """Verify the liveness marker helper is fail-open."""

    def test_creates_marker_file(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """_write_liveness_marker creates the file when SCHEDULER_LIVENESS_FILE is set."""
        marker = tmp_path / "scheduler_alive"
        monkeypatch.setattr(
            settings, "SCHEDULER_LIVENESS_FILE", str(marker)
        )

        _write_liveness_marker()

        assert marker.exists()

    def test_noop_when_path_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """_write_liveness_marker is a no-op when path is empty (test settings)."""
        monkeypatch.setattr(settings, "SCHEDULER_LIVENESS_FILE", "")

        # Should not raise
        _write_liveness_marker()

    def test_fail_open_on_oserror(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """_write_liveness_marker does not raise on OSError (fail-open)."""
        monkeypatch.setattr(
            settings,
            "SCHEDULER_LIVENESS_FILE",
            "/nonexistent/dir/scheduler_alive",
        )

        with caplog.at_level(
            logging.DEBUG, logger="apps.core.utils.scheduler"
        ):
            # Should not raise — fail-open
            _write_liveness_marker()

        assert any(
            "Could not update scheduler liveness marker" in record.message
            for record in caplog.records
        )


# ---------------------------------------------------------------------------
# run_one_cycle — liveness marker integration
# ---------------------------------------------------------------------------


class TestLivenessMarkerIntegration:
    """Verify the marker is written after hourly commands in run_one_cycle."""

    def test_hourly_cycle_writes_marker(
        self,
        daily_marker,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """run_one_cycle writes the liveness marker after hourly commands."""
        marker = tmp_path / "scheduler_alive"
        monkeypatch.setattr(
            settings, "SCHEDULER_LIVENESS_FILE", str(marker)
        )

        now_func = lambda: _utc(2025, 6, 15, 0)  # noqa: E731

        run_one_cycle(
            now_func=now_func,
            run_command=_noop_command,
            last_daily=None,
            daily_marker=daily_marker,
        )

        assert marker.exists()

    def test_daily_cycle_does_not_write_marker(
        self,
        daily_marker,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Marker written once per cycle — after hourly, not again after daily."""
        marker = tmp_path / "scheduler_alive"
        monkeypatch.setattr(
            settings, "SCHEDULER_LIVENESS_FILE", str(marker)
        )

        with patch(
            "apps.core.utils.scheduler._write_liveness_marker",
            wraps=_write_liveness_marker,
        ) as mock_marker:
            now_func = lambda: _utc(  # noqa: E731
                2025, 6, 15, 8
            )

            run_one_cycle(
                now_func=now_func,
                run_command=_noop_command,
                last_daily=None,
                daily_marker=daily_marker,
            )

        # Written exactly once — after both the hourly and daily sets complete
        assert mock_marker.call_count == 1
        assert marker.exists()

    def test_marker_not_refreshed_when_hourly_command_fails(
        self,
        daily_marker,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """A failing hourly command leaves the liveness marker untouched.

        The marker is pre-created with a known old mtime; a failing cycle must
        not refresh it (ENT-013). Assert the mtime is *unchanged* rather than
        that the file is absent — a deletion would also pass the latter, which
        is the opposite of the contract.
        """
        marker = tmp_path / "scheduler_alive"
        marker.touch()
        old_mtime = 1_000_000
        os.utime(marker, (old_mtime, old_mtime))
        monkeypatch.setattr(
            settings, "SCHEDULER_LIVENESS_FILE", str(marker)
        )

        def failing_command(name: str) -> int:
            if name == HOURLY_COMMANDS[0]:
                return 1
            return 0

        now_func = lambda: _utc(2025, 6, 15, 0)  # noqa: E731

        run_one_cycle(
            now_func=now_func,
            run_command=failing_command,
            last_daily=None,
            daily_marker=daily_marker,
        )

        assert marker.stat().st_mtime_ns == old_mtime * 1_000_000_000

    def test_marker_not_refreshed_when_daily_command_fails(
        self,
        daily_marker,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """A failing daily command leaves the liveness marker untouched.

        ``now`` is at 08:00 UTC so the daily set fires; ``daily_marker`` is not
        recorded either, keeping the two markers distinct.
        """
        marker = tmp_path / "scheduler_alive"
        marker.touch()
        old_mtime = 1_000_000
        os.utime(marker, (old_mtime, old_mtime))
        monkeypatch.setattr(
            settings, "SCHEDULER_LIVENESS_FILE", str(marker)
        )

        def failing_command(name: str) -> int:
            if name == DAILY_COMMANDS[0]:
                return 1
            return 0

        now_func = lambda: _utc(2025, 6, 15, 8)  # noqa: E731

        run_one_cycle(
            now_func=now_func,
            run_command=failing_command,
            last_daily=None,
            daily_marker=daily_marker,
        )

        assert marker.stat().st_mtime_ns == old_mtime * 1_000_000_000
        assert daily_marker.recorded == []

    def test_marker_not_refreshed_when_cycle_raises(
        self,
        daily_marker,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """A cycle that raises before the marker write leaves the marker untouched.

        The raise is induced at the daily gate — the only point after the hourly
        set where a raise is both reachable in production and distinguishable
        from pre-fix behaviour. The ``run_one_cycle`` caller observes the raise;
        the swallow belongs to ``run_scheduler``, not here.
        """
        marker = tmp_path / "scheduler_alive"
        marker.touch()
        old_mtime = 1_000_000
        os.utime(marker, (old_mtime, old_mtime))
        monkeypatch.setattr(
            settings, "SCHEDULER_LIVENESS_FILE", str(marker)
        )

        now_func = lambda: _utc(2025, 6, 15, 8)  # noqa: E731

        with patch(
            "apps.core.utils.scheduler.should_run_daily",
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(RuntimeError):
                run_one_cycle(
                    now_func=now_func,
                    run_command=_noop_command,
                    last_daily=None,
                    daily_marker=daily_marker,
                )

        assert marker.stat().st_mtime_ns == old_mtime * 1_000_000_000

    def test_marker_not_refreshed_when_stop_requested_mid_cycle(
        self,
        daily_marker,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """A stop-truncated cycle leaves the marker untouched even with all 0s.

        ``_stop_aware_dispatch`` returns 0 for every command it declines, so all
        nine exit codes are 0; the marker must still not be refreshed. The stop
        flag is driven directly and cleared in a ``finally`` (pytest-randomly).
        """
        marker = tmp_path / "scheduler_alive"
        marker.touch()
        old_mtime = 1_000_000
        os.utime(marker, (old_mtime, old_mtime))
        monkeypatch.setattr(
            settings, "SCHEDULER_LIVENESS_FILE", str(marker)
        )

        def stop_on_first(name: str) -> int:
            if name == HOURLY_COMMANDS[0]:
                scheduler_mod._stop_event.set()
            return 0

        dispatch = _stop_aware_dispatch(stop_on_first)
        now_func = lambda: _utc(2025, 6, 15, 0)  # noqa: E731

        try:
            run_one_cycle(
                now_func=now_func,
                run_command=dispatch,
                last_daily=None,
                daily_marker=daily_marker,
            )
        finally:
            scheduler_mod._stop_event.clear()

        assert marker.stat().st_mtime_ns == old_mtime * 1_000_000_000

    def test_marker_written_after_a_failing_first_cycle(
        self,
        daily_marker,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """A failing first cycle still writes the marker (first-cycle grace).

        Design guard for the ``is_first_cycle`` parameter: a fresh container is
        born without a marker, so its first cycle must write it unconditionally
        to avoid a restart storm under a persistent failure. Green pre-fix by
        construction — it pins a deliberate deviation from a pure conditional
        write and protects the grace from being removed.
        """
        marker = tmp_path / "scheduler_alive"
        monkeypatch.setattr(
            settings, "SCHEDULER_LIVENESS_FILE", str(marker)
        )

        def failing_command(name: str) -> int:
            if name == HOURLY_COMMANDS[0]:
                return 1
            return 0

        now_func = lambda: _utc(2025, 6, 15, 0)  # noqa: E731

        run_one_cycle(
            now_func=now_func,
            run_command=failing_command,
            last_daily=None,
            daily_marker=daily_marker,
            is_first_cycle=True,
        )

        assert marker.exists()
