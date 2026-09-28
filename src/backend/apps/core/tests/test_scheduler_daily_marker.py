"""
Integration tests for the scheduler's durable daily-dispatch marker.

Covers the DB-backed ``SchedulerDailyMarker`` seam and the daily gate in
``apps.core.utils.scheduler``: the daily set fires once per calendar day per
*recorded success*, the durable marker is what survives a restart, a failed
daily set is retried, and marker failures are fail-open (re-run, never skip).

``pytestmark`` is ``django_db``/``integration`` (mirroring
``test_alert_query.py``). This is deliberately a separate file from
``test_scheduler.py`` / ``test_scheduler_error_handling.py``, which are both
``unit``-marked with no database; adding DB-backed tests there would contradict
their own stated contract.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.core.models import SchedulerDailyState
from apps.core.services.scheduler_daily_state import SchedulerDailyMarker
from apps.core.utils.scheduler import (
    DAILY_COMMANDS,
    HOURLY_COMMANDS,
    run_one_cycle,
    run_scheduler,
)

from .conftest import RecordingDailyMarker

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    """Build a timezone-aware UTC datetime for tests."""
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


class TestDurableDailyMarker:
    """The durable marker, not process memory, governs the daily gate."""

    def test_durable_marker_suppresses_daily_on_a_fresh_scheduler_frame(self) -> None:
        """A fresh scheduler frame with a durable marker for today skips daily.

        This is the actual defect: before this change the marker lived only in
        process memory, so every restart re-ran the daily set even on the same
        calendar day. With the durable marker seeded for today, a fresh
        ``run_scheduler`` dispatches only the hourly commands.
        """
        state = SchedulerDailyState.get_singleton()
        state.last_daily = date(2025, 6, 15)
        state.last_daily_completed_at = timezone.now()
        state.save(
            update_fields=["last_daily", "last_daily_completed_at", "updated_at"]
        )

        run_command = MagicMock(return_value=0)

        def stop_after_one(_seconds: float) -> None:
            raise StopIteration  # break the while True after one cycle

        with pytest.raises(StopIteration):
            run_scheduler(
                run_command_fn=run_command,
                now_func=lambda: _utc(2025, 6, 15, 12),
                sleep_func=stop_after_one,
                interval_seconds=0,
                daily_marker=SchedulerDailyMarker(),
            )

        dispatched = [call.args[0] for call in run_command.call_args_list]
        assert dispatched == HOURLY_COMMANDS
        for cmd in DAILY_COMMANDS:
            assert cmd not in dispatched

    def test_clean_daily_cycle_records_the_marker_for_the_next_start(self) -> None:
        """A clean daily cycle records the marker so the next start skips it."""
        marker = SchedulerDailyMarker()
        run_command = MagicMock(return_value=0)

        result = run_one_cycle(
            now_func=lambda: _utc(2025, 6, 15, 8),
            run_command=run_command,
            last_daily=None,
            daily_marker=marker,
        )

        dispatched = [call.args[0] for call in run_command.call_args_list]
        for cmd in DAILY_COMMANDS:
            assert cmd in dispatched
        assert marker.read_last_daily() == date(2025, 6, 15)
        assert result == date(2025, 6, 15)


class TestDailyGate:
    """The daily gate: only a fully-clean cycle records the day."""

    def test_failing_daily_command_leaves_the_marker_unchanged(self) -> None:
        """A failing daily command leaves the marker unchanged and the day unset."""
        marker = RecordingDailyMarker(last_daily=date(2025, 6, 14))
        dispatched: list[str] = []

        def run_command(name: str) -> int:
            dispatched.append(name)
            if name == DAILY_COMMANDS[0]:
                return 1
            return 0

        result = run_one_cycle(
            now_func=lambda: _utc(2025, 6, 15, 8),
            run_command=run_command,
            last_daily=date(2025, 6, 14),
            daily_marker=marker,
        )

        # Both daily commands were dispatched — the list did not short-circuit.
        assert DAILY_COMMANDS[0] in dispatched
        assert DAILY_COMMANDS[1] in dispatched
        assert marker.recorded == []
        assert result == date(2025, 6, 14)

    def test_clean_daily_run_writes_the_marker(self) -> None:
        """An all-success daily cycle writes the marker and returns the new day."""
        marker = RecordingDailyMarker(last_daily=date(2025, 6, 14))
        run_command = MagicMock(return_value=0)

        result = run_one_cycle(
            now_func=lambda: _utc(2025, 6, 15, 8),
            run_command=run_command,
            last_daily=date(2025, 6, 14),
            daily_marker=marker,
        )

        assert marker.recorded == [date(2025, 6, 15)]
        assert result == date(2025, 6, 15)


class TestMarkerFailOpen:
    """Marker read/write failures are fail-open: re-run, never skip."""

    def test_record_daily_failure_is_swallowed(self, caplog: pytest.LogCaptureFixture) -> None:
        """A record_daily failure must not raise and must log a WARNING."""
        marker = SchedulerDailyMarker()
        with patch(
            "apps.core.models.SchedulerDailyState.get_singleton",
            side_effect=RuntimeError("db down"),
        ):
            with caplog.at_level(
                logging.WARNING, logger="apps.core.services.scheduler_daily_state"
            ):
                # Must not raise — fail-open.
                marker.record_daily(date(2025, 6, 15))

        assert any(
            "Could not record the scheduler daily marker" in record.message
            for record in caplog.records
        )

    def test_read_failure_reports_none(self, caplog: pytest.LogCaptureFixture) -> None:
        """A read failure reports None (not raise) so the caller re-runs."""
        marker = SchedulerDailyMarker()
        with patch(
            "apps.core.models.SchedulerDailyState.get_singleton",
            side_effect=RuntimeError("db down"),
        ):
            with caplog.at_level(
                logging.WARNING, logger="apps.core.services.scheduler_daily_state"
            ):
                # Must not raise — fail-open.
                result = marker.read_last_daily()

        assert result is None
        assert any(
            "Could not read the scheduler daily marker" in record.message
            for record in caplog.records
        )
