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
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings

from apps.core.utils.scheduler import (
    DAILY_COMMANDS,
    HOURLY_COMMANDS,
    _dispatch,
    _run_command_subprocess,
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

    def test_hourly_cycle_continues_past_failure(self) -> None:
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
        )

        # All 9 hourly commands were attempted (3rd raised, but _dispatch caught it)
        assert dispatched == HOURLY_COMMANDS

    def test_hourly_failure_does_not_skip_daily(self) -> None:
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
        )

        # All hourly commands dispatched despite the first one failing
        assert HOURLY_COMMANDS == dispatched[: len(HOURLY_COMMANDS)]
        # Daily command also dispatched
        assert "send_alerts" in dispatched

    def test_daily_cycle_continues_past_failure(self) -> None:
        """If the daily command raises, the cycle completes and last_daily updates."""
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
        )

        # Daily command was still dispatched (exception caught by _dispatch)
        assert DAILY_COMMANDS[0] in dispatched
        # last_daily was updated despite the exception
        assert result == date(2025, 6, 15)


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
        )

        assert marker.exists()

    def test_daily_cycle_does_not_write_marker(
        self,
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
            )

        # Written exactly once — after hourly commands, before the daily section
        assert mock_marker.call_count == 1
        assert marker.exists()

    def test_marker_written_even_when_hourly_command_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Liveness marker is written even if a hourly command raises.

        The marker is written after the hourly loop completes (failures caught
        by _dispatch), not gated on command success.
        """
        marker = tmp_path / "scheduler_alive"
        monkeypatch.setattr(
            settings, "SCHEDULER_LIVENESS_FILE", str(marker)
        )

        def failing_command(name: str) -> int:
            if name == HOURLY_COMMANDS[0]:
                raise RuntimeError("crash")
            return 0

        now_func = lambda: _utc(2025, 6, 15, 0)  # noqa: E731

        run_one_cycle(
            now_func=now_func,
            run_command=failing_command,
            last_daily=None,
        )

        assert marker.exists()
