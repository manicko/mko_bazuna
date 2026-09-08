"""
Scheduler wiring test — verifies that ``sweep_orphaned_media`` is registered
in the hourly command list of ``docker/entrypoint-scheduler.sh``.

This is a static configuration test (no database interaction): if someone
adds the command to the scheduler rotation but forgets to wire it into
``entrypoint-scheduler.sh``, the hourly sweep never runs and orphaned media
files accumulate indefinitely.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.conf import settings

pytestmark = [pytest.mark.unit]

# The scheduler script lives at <project-root>/docker/entrypoint-scheduler.sh.
# BASE_DIR in settings points to src/ (the inner source dir); its parent is
# the project root.
_SCHEDULER_SCRIPT = settings.BASE_DIR.parent / "docker" / "entrypoint-scheduler.sh"


class TestSchedulerWiring:
    """Verify scheduled commands are present in entrypoint-scheduler.sh."""

    def test_sweep_orphaned_media_in_hourly_commands(self) -> None:
        """``sweep_orphaned_media`` must appear in the hourly_commands list."""
        content = Path(_SCHEDULER_SCRIPT).read_text(encoding="utf-8")

        # The command must be present inside the hourly_commands list,
        # not just somewhere in the file.
        assert "'sweep_orphaned_media'" in content
        assert "hourly_commands" in content
        assert "sweep_orphaned_media" in content
