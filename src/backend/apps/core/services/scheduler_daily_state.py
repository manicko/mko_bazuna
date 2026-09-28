"""
Durable marker for the scheduler's daily command set.

Records the calendar date the daily set last completed cleanly. The scheduler
reads it once on start-up and writes it only after every daily command exited
0. Both operations are fail-open, mirroring ``_write_liveness_marker`` — a
marker problem must cause a re-run, never a silent skip. Django imports are
deferred to keep the scheduler's importable-without-Django property.
"""

import logging
from datetime import date
from typing import cast

logger = logging.getLogger(__name__)


class SchedulerDailyMarker:
    """Read/write seam over the ``scheduler_daily_state`` singleton row."""

    def read_last_daily(self) -> date | None:
        """Return the date the daily set last completed, or ``None`` if unknown.

        Fail-open: any error (table missing, connection refused, permissions)
        is logged at WARNING and reported as ``None``, which makes the caller
        re-run the daily set rather than skip it.
        """
        from apps.core.models import SchedulerDailyState

        try:
            return cast(date | None, SchedulerDailyState.get_singleton().last_daily)
        except Exception as exc:
            logger.warning("Could not read the scheduler daily marker: %s", exc)
            return None

    def record_daily(self, day: date) -> None:
        """Record *day* as the date the daily set completed.

        Fail-open: any error is logged at WARNING and swallowed.
        """
        from django.utils import timezone

        from apps.core.models import SchedulerDailyState

        try:
            state = SchedulerDailyState.get_singleton()
            state.last_daily = day
            state.last_daily_completed_at = timezone.now()
            state.save(
                update_fields=["last_daily", "last_daily_completed_at", "updated_at"]
            )
        except Exception as exc:
            logger.warning(
                "Could not record the scheduler daily marker for %s: %s", day, exc
            )
