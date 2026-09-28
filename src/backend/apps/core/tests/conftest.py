"""
Shared fixtures for ``apps.core.tests`` scheduler tests.

Provides ``RecordingDailyMarker``, a recording stand-in for the scheduler's
durable daily marker, and the ``daily_marker`` fixture. Both scheduler test
modules are ``pytest.mark.unit`` with no database, so the production
DB-backed marker (``SchedulerDailyMarker``) cannot be used; the recording
double implements the ``apps.core.utils.scheduler.DailyMarker`` protocol
structurally. Precedent for a local ``conftest.py``:
``src/telegram_bot/tests/conftest.py``.
"""

from __future__ import annotations

from datetime import date

import pytest


class RecordingDailyMarker:
    """Recording stand-in for the scheduler's durable daily marker.

    Implements the ``apps.core.utils.scheduler.DailyMarker`` protocol
    structurally. Every ``record_daily`` call is appended to ``recorded`` so a
    test can assert *which* day was (or was not) marked — not merely that the
    collaborator was reached. ``read_last_daily`` returns the last recorded day,
    so the fake round-trips the way the real one does.
    """

    def __init__(self, last_daily: date | None = None) -> None:
        self.recorded: list[date] = []
        self._last_daily = last_daily

    def read_last_daily(self) -> date | None:
        return self._last_daily

    def record_daily(self, day: date) -> None:
        self.recorded.append(day)
        self._last_daily = day


@pytest.fixture
def daily_marker() -> RecordingDailyMarker:
    """A fresh recording daily marker, starting with nothing recorded."""
    return RecordingDailyMarker()
