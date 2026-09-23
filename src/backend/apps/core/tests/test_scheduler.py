"""
Unit tests for ``apps.core.utils.scheduler``.

Covers:
  * ``should_run_daily()`` — the daily-timing predicate (all edge cases).
  * ``run_one_cycle()`` — single-tick dispatch of hourly + daily commands
    with injectable ``now_func`` and ``run_command`` mock.
  * ``run_scheduler()`` — infinite loop with injectable ``sleep_func``
    (no-op sleep that raises after one cycle, so the loop terminates).
  * ``_validate_commands()`` — fail-fast discovery of management commands.
  * ``HOURLY_COMMANDS`` / ``DAILY_COMMANDS`` / ``DAILY_HOUR_UTC`` /
    ``SCHEDULE_INTERVAL_SECONDS`` — constant-value verification.
  * ``_default_manage_py()`` — path resolution relative to this file.
  * ``_dispatch()`` — per-command exception isolation.

All tests are pure unit tests (``pytest.mark.unit``) — no database, no
subprocess. ``run_command`` is a no-op callable returning 0, so the dispatch
path is exercised without spawning children.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from apps.core.utils.scheduler import (
    DAILY_COMMANDS,
    DAILY_HOUR_UTC,
    HOURLY_COMMANDS,
    SCHEDULE_INTERVAL_SECONDS,
    run_one_cycle,
    run_scheduler,
    should_run_daily,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    """Build a timezone-aware UTC datetime for tests."""
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def _noop_command(name: str) -> int:
    """A run_command stub that always returns 0."""
    return 0


# ---------------------------------------------------------------------------
# Constants — must match the original inline script in entrypoint-scheduler.sh
# ---------------------------------------------------------------------------


class TestSchedulerConstants:
    """Verify the module-level command lists and thresholds."""

    def test_hourly_commands_match_spec(self) -> None:
        """HOURLY_COMMANDS must match the canonical Phase 4 sweep list."""
        assert HOURLY_COMMANDS == [
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

    def test_daily_commands_include_send_alerts(self) -> None:
        """DAILY_COMMANDS must include send_alerts."""
        assert DAILY_COMMANDS == ["send_alerts"]

    def test_daily_hour_utc_is_8(self) -> None:
        """DAILY_HOUR_UTC must be 08:00 UTC per phase-02 spec."""
        assert DAILY_HOUR_UTC == 8

    def test_schedule_interval_is_3600(self) -> None:
        """SCHEDULE_INTERVAL_SECONDS must be 1 hour."""
        assert SCHEDULE_INTERVAL_SECONDS == 3600.0

    def test_sweep_orphaned_media_in_hourly(self) -> None:
        """sweep_orphaned_media must be present in HOURLY_COMMANDS."""
        assert "sweep_orphaned_media" in HOURLY_COMMANDS

    def test_all_hourly_commands_are_distinct(self) -> None:
        """No duplicate command names in HOURLY_COMMANDS."""
        assert len(HOURLY_COMMANDS) == len(set(HOURLY_COMMANDS))


# ---------------------------------------------------------------------------
# should_run_daily() — pure predicate, all edge cases
# ---------------------------------------------------------------------------


class TestShouldRunDaily:
    """Test the daily-timing predicate."""

    def test_first_run_before_threshold(self) -> None:
        """First run (last_daily=None) before 08:00 UTC -> False."""
        now = _utc(2025, 6, 15, 7, 59)
        assert should_run_daily(now, None, DAILY_HOUR_UTC) is False

    def test_first_run_at_threshold(self) -> None:
        """First run at exactly 08:00 UTC -> True."""
        now = _utc(2025, 6, 15, 8, 0)
        assert should_run_daily(now, None, DAILY_HOUR_UTC) is True

    def test_first_run_after_threshold(self) -> None:
        """First run after 08:00 UTC -> True."""
        now = _utc(2025, 6, 15, 23, 0)
        assert should_run_daily(now, None, DAILY_HOUR_UTC) is True

    def test_same_day_does_not_repeat(self) -> None:
        """Same date as last_daily -> False (daily already ran today)."""
        now = _utc(2025, 6, 15, 12, 0)
        last = date(2025, 6, 15)
        assert should_run_daily(now, last, DAILY_HOUR_UTC) is False

    def test_next_day_before_threshold(self) -> None:
        """New calendar day but before 08:00 -> False (wait for threshold)."""
        now = _utc(2025, 6, 16, 7, 59)
        last = date(2025, 6, 15)
        assert should_run_daily(now, last, DAILY_HOUR_UTC) is False

    def test_next_day_at_threshold(self) -> None:
        """New calendar day at 08:00 -> True."""
        now = _utc(2025, 6, 16, 8, 0)
        last = date(2025, 6, 15)
        assert should_run_daily(now, last, DAILY_HOUR_UTC) is True

    def test_next_day_after_threshold(self) -> None:
        """New calendar day after 08:00 -> True."""
        now = _utc(2025, 6, 16, 14, 30)
        last = date(2025, 6, 15)
        assert should_run_daily(now, last, DAILY_HOUR_UTC) is True

    def test_next_day_before_threshold_does_not_update_last(self) -> None:
        """If before threshold on new day, should_run_daily is False so
        last_daily is not updated — next tick re-evaluates."""
        now = _utc(2025, 6, 16, 7, 59)
        last = date(2025, 6, 15)
        assert should_run_daily(now, last, DAILY_HOUR_UTC) is False

    def test_custom_threshold(self) -> None:
        """should_run_daily respects a custom daily_hour_utc."""
        now = _utc(2025, 6, 15, 10, 0)
        assert should_run_daily(now, None, 10) is True

    def test_custom_threshold_not_met(self) -> None:
        """Custom threshold not yet reached on first run -> False."""
        now = _utc(2025, 6, 15, 9, 0)
        assert should_run_daily(now, None, 10) is False


# ---------------------------------------------------------------------------
# run_one_cycle() — single tick with injectable now_func and run_command mock
# ---------------------------------------------------------------------------


class TestRunOneCycle:
    """Test single-cycle dispatch logic."""

    @staticmethod
    def _make_mock_run_command() -> MagicMock:
        """Create a mock run_command that returns 0 for all calls."""
        return MagicMock(return_value=0)

    def test_hourly_commands_all_dispatched(self) -> None:
        """Every command in HOURLY_COMMANDS is dispatched exactly once per cycle."""
        run_command = self._make_mock_run_command()
        now_func = lambda: _utc(2025, 6, 15, 0)  # noqa: E731

        run_one_cycle(
            now_func=now_func,
            run_command=run_command,
            last_daily=None,
        )

        # Every hourly command was called exactly once
        called_names = [call.args[0] for call in run_command.call_args_list]
        for cmd in HOURLY_COMMANDS:
            assert cmd in called_names, f"{cmd} was not dispatched"
        assert len(called_names) == len(HOURLY_COMMANDS)

    def test_daily_commands_not_dispatched_before_threshold_first_run(
        self,
    ) -> None:
        """First run before 08:00 UTC — daily commands are NOT dispatched."""
        run_command = self._make_mock_run_command()
        now_func = lambda: _utc(2025, 6, 15, 7)  # noqa: E731

        result = run_one_cycle(
            now_func=now_func,
            run_command=run_command,
            last_daily=None,
        )

        called_names = [call.args[0] for call in run_command.call_args_list]
        for cmd in DAILY_COMMANDS:
            assert cmd not in called_names
        assert result is None  # last_daily unchanged

    def test_daily_commands_dispatched_at_threshold_first_run(self) -> None:
        """First run at 08:00 UTC — daily commands ARE dispatched."""
        run_command = self._make_mock_run_command()
        now_func = lambda: _utc(2025, 6, 15, 8)  # noqa: E731

        result = run_one_cycle(
            now_func=now_func,
            run_command=run_command,
            last_daily=None,
        )

        called_names = [call.args[0] for call in run_command.call_args_list]
        for cmd in DAILY_COMMANDS:
            assert cmd in called_names, f"{cmd} was not dispatched"
        assert result == date(2025, 6, 15)

    def test_daily_commands_dispatched_after_threshold(self) -> None:
        """First run after 08:00 UTC — daily commands dispatched."""
        run_command = self._make_mock_run_command()
        now_func = lambda: _utc(2025, 6, 15, 14, 30)  # noqa: E731

        result = run_one_cycle(
            now_func=now_func,
            run_command=run_command,
            last_daily=None,
        )

        called_names = [call.args[0] for call in run_command.call_args_list]
        for cmd in DAILY_COMMANDS:
            assert cmd in called_names
        assert result == date(2025, 6, 15)

    def test_daily_not_repeated_same_day(self) -> None:
        """Same day as last_daily — daily commands NOT dispatched again."""
        run_command = self._make_mock_run_command()
        now_func = lambda: _utc(2025, 6, 15, 12)  # noqa: E731

        result = run_one_cycle(
            now_func=now_func,
            run_command=run_command,
            last_daily=date(2025, 6, 15),
        )

        called_names = [call.args[0] for call in run_command.call_args_list]
        for cmd in DAILY_COMMANDS:
            assert cmd not in called_names
        assert result == date(2025, 6, 15)  # unchanged

    def test_daily_not_run_next_day_before_threshold(self) -> None:
        """New day but before 08:00 — daily not dispatched, last_daily unchanged."""
        run_command = self._make_mock_run_command()
        now_func = lambda: _utc(2025, 6, 16, 7)  # noqa: E731

        result = run_one_cycle(
            now_func=now_func,
            run_command=run_command,
            last_daily=date(2025, 6, 15),
        )

        called_names = [call.args[0] for call in run_command.call_args_list]
        for cmd in DAILY_COMMANDS:
            assert cmd not in called_names
        assert result == date(2025, 6, 15)  # unchanged

    def test_daily_runs_next_day_at_threshold(self) -> None:
        """New day at 08:00 — daily dispatched, last_daily updated to new date."""
        run_command = self._make_mock_run_command()
        now_func = lambda: _utc(2025, 6, 16, 8)  # noqa: E731

        result = run_one_cycle(
            now_func=now_func,
            run_command=run_command,
            last_daily=date(2025, 6, 15),
        )

        called_names = [call.args[0] for call in run_command.call_args_list]
        for cmd in DAILY_COMMANDS:
            assert cmd in called_names
        assert result == date(2025, 6, 16)

    def test_hourly_plus_daily_count(self) -> None:
        """Total dispatches = len(HOURLY) + len(DAILY) when daily runs."""
        run_command = self._make_mock_run_command()
        now_func = lambda: _utc(2025, 6, 15, 8)  # noqa: E731

        run_one_cycle(
            now_func=now_func,
            run_command=run_command,
            last_daily=date(2025, 6, 14),
        )

        expected = len(HOURLY_COMMANDS) + len(DAILY_COMMANDS)
        assert run_command.call_count == expected

    def test_hourly_only_count_no_daily(self) -> None:
        """Total dispatches = len(HOURLY) when daily does not run."""
        run_command = self._make_mock_run_command()
        now_func = lambda: _utc(2025, 6, 15, 7)  # noqa: E731

        run_one_cycle(
            now_func=now_func,
            run_command=run_command,
            last_daily=None,
        )

        assert run_command.call_count == len(HOURLY_COMMANDS)


# ---------------------------------------------------------------------------
# run_scheduler() — infinite loop with injectable sleep_func (no-op terminates)
# ---------------------------------------------------------------------------


class TestRunScheduler:
    """Test the infinite loop with injectable collaborators."""

    def test_single_cycle_then_stop(self) -> None:
        """Inject a no-op sleep that raises to break the loop after one cycle."""
        run_command = MagicMock(return_value=0)
        sleep_calls: list[float] = []

        def stop_after_one(_seconds: float) -> None:
            sleep_calls.append(_seconds)
            raise StopIteration  # break the while True

        now_func = lambda: _utc(2025, 6, 15, 8)  # noqa: E731

        with pytest.raises(StopIteration):
            run_scheduler(
                sleep_func=stop_after_one,
                now_func=now_func,
                run_command_fn=run_command,
                interval_seconds=0,
            )

        # One sleep call (the loop ran exactly once before StopIteration)
        assert len(sleep_calls) == 1
        # Hourly + daily commands dispatched
        assert run_command.call_count == len(HOURLY_COMMANDS) + len(DAILY_COMMANDS)

    def test_cycle_failure_does_not_crash(self) -> None:
        """A cycle-level exception is caught; scheduler continues."""
        call_count = [0]

        def failing_run_command(name: str) -> int:
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("boom")
            return 0

        sleep_calls: list[float] = []

        def stop_after_one(_seconds: float) -> None:
            sleep_calls.append(_seconds)
            raise StopIteration

        now_func = lambda: _utc(2025, 6, 15, 8)  # noqa: E731

        with pytest.raises(StopIteration):
            run_scheduler(
                sleep_func=stop_after_one,
                now_func=now_func,
                run_command_fn=failing_run_command,
                interval_seconds=0,
            )

        # Sleep was still called — the cycle exception was caught
        assert len(sleep_calls) == 1

    def test_command_exception_does_not_skip_remaining(self) -> None:
        """Per-command exception is isolated; remaining commands still dispatch."""
        call_count = [0]

        def selective_fail(name: str) -> int:
            call_count[0] += 1
            if name == HOURLY_COMMANDS[0]:
                raise RuntimeError("skip me")
            return 0

        sleep_calls: list[float] = []

        def stop_after_one(_seconds: float) -> None:
            sleep_calls.append(_seconds)
            raise StopIteration

        now_func = lambda: _utc(2025, 6, 15, 8)  # noqa: E731

        with pytest.raises(StopIteration):
            run_scheduler(
                sleep_func=stop_after_one,
                now_func=now_func,
                run_command_fn=selective_fail,
                interval_seconds=0,
            )

        # All hourly + all daily commands were attempted (none skipped)
        expected = len(HOURLY_COMMANDS) + len(DAILY_COMMANDS)
        assert call_count[0] == expected


# ---------------------------------------------------------------------------
# _validate_commands() — fail-fast command discovery
# ---------------------------------------------------------------------------


class TestValidateCommands:
    """Test fail-fast validation of scheduled command names."""

    def test_all_scheduled_commands_exist(self) -> None:
        """All commands in HOURLY + DAILY must be discoverable by Django.

        Requires Django setup (provided by pytest-django).
        """
        from apps.core.utils.scheduler import _validate_commands

        # Should not raise — all commands exist in the codebase
        _validate_commands(HOURLY_COMMANDS + DAILY_COMMANDS)

    def test_missing_command_raises(self) -> None:
        """A non-existent command name raises CommandError."""
        from django.core.management import CommandError

        from apps.core.utils.scheduler import _validate_commands

        with pytest.raises(CommandError, match="Unreachable scheduler commands"):
            _validate_commands(["this_command_does_not_exist"])

    def test_empty_list_passes(self) -> None:
        """An empty list passes validation trivially."""
        from apps.core.utils.scheduler import _validate_commands

        _validate_commands([])

    def test_partial_missing_raises_with_name(self) -> None:
        """The missing command name appears in the error message."""
        from django.core.management import CommandError

        from apps.core.utils.scheduler import _validate_commands

        with pytest.raises(CommandError, match="this_command_does_not_exist"):
            _validate_commands(["archive_sweep", "this_command_does_not_exist"])


# ---------------------------------------------------------------------------
# _default_manage_py() — path resolution
# ---------------------------------------------------------------------------


class TestDefaultManagePy:
    """Test manage.py path resolution."""

    def test_manage_py_resolves_to_src_backend(self) -> None:
        """_default_manage_py() points to src/backend/manage.py."""
        from apps.core.utils.scheduler import _default_manage_py

        manage_py = _default_manage_py()
        # parents[3] of scheduler.py (apps/core/utils/scheduler.py) is src/backend/
        assert manage_py.name == "manage.py"
        # The path should exist (manage.py is a real file in the repo)
        assert manage_py.exists()


# ---------------------------------------------------------------------------
# _run_command_subprocess() — faithful check=False port
# ---------------------------------------------------------------------------


class TestRunCommandSubprocess:
    """Test the subprocess dispatch function (mocking subprocess.run)."""

    def test_returns_exit_code(self, tmp_path: Path) -> None:
        """_run_command_subprocess returns the subprocess return code."""
        from apps.core.utils.scheduler import _run_command_subprocess

        fake_result = MagicMock(returncode=42)
        with patch(
            "apps.core.utils.scheduler.subprocess.run",
            return_value=fake_result,
        ) as mock_run:
            rc = _run_command_subprocess("test_cmd", tmp_path / "manage.py", "python")
            assert rc == 42
            mock_run.assert_called_once()

    def test_check_false_does_not_raise_on_nonzero(self, tmp_path: Path) -> None:
        """check=False means non-zero exit does not raise."""
        from apps.core.utils.scheduler import _run_command_subprocess

        fake_result = MagicMock(returncode=1)
        with patch(
            "apps.core.utils.scheduler.subprocess.run",
            return_value=fake_result,
        ):
            rc = _run_command_subprocess("test_cmd", tmp_path / "manage.py", "python")
            assert rc == 1


# ---------------------------------------------------------------------------
# _dispatch() — per-command exception isolation
# ---------------------------------------------------------------------------


class TestDispatchIsolation:
    """Test that _dispatch catches exceptions and returns 1."""

    def test_dispatch_catches_exception(self) -> None:
        """_dispatch catches exceptions and returns 1."""
        from apps.core.utils.scheduler import _dispatch

        def failing_command(_name: str) -> int:
            raise RuntimeError("command crash")

        result = _dispatch("test_cmd", failing_command)
        assert result == 1

    def test_dispatch_returns_success_code(self) -> None:
        """_dispatch returns the command's exit code on success."""
        from apps.core.utils.scheduler import _dispatch

        def success_command(_name: str) -> int:
            return 0

        result = _dispatch("test_cmd", success_command)
        assert result == 0

    def test_dispatch_logs_on_exception(self, caplog: pytest.LogCaptureFixture) -> None:
        """_dispatch logs at DEBUG level on exception."""
        from apps.core.utils.scheduler import _dispatch

        def crashing_command(_name: str) -> int:
            raise RuntimeError("crash")

        with caplog.at_level(logging.DEBUG, logger="apps.core.utils.scheduler"):
            result = _dispatch("test_cmd", crashing_command)

        assert result == 1
        assert any(
            "Failed to dispatch command" in record.message
            for record in caplog.records
        )
