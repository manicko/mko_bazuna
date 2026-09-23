"""
Scheduler wiring test — verifies that ``docker/entrypoint-scheduler.sh`` calls
the importable ``apps.core.utils.scheduler`` module (ENT-006) instead of an
inline ``python -c`` block.

This is a static configuration test (no database interaction): if someone
refactors the scheduler script but forgets to point it at the canonical
module, the entrypoint would diverge from the tested, coverage-instrumented
code path.
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
    """Verify the entrypoint delegates to the scheduler Python module."""

    def test_entrypoint_invokes_scheduler_module(self) -> None:
        """entrypoint-scheduler.sh must call ``python -m apps.core.utils.scheduler``."""
        content = Path(_SCHEDULER_SCRIPT).read_text(encoding="utf-8")
        assert "apps.core.utils.scheduler" in content

    def test_entrypoint_no_longer_uses_inline_python_c(self) -> None:
        """The inline ``python -c`` block must be gone."""
        content = Path(_SCHEDULER_SCRIPT).read_text(encoding="utf-8")
        assert 'python -c "' not in content
        assert "hourly_commands" not in content
        assert "daily_commands" not in content

    def test_entrypoint_uses_exec(self) -> None:
        """The scheduler module is launched via ``exec`` (PID 1 signal handling)."""
        content = Path(_SCHEDULER_SCRIPT).read_text(encoding="utf-8")
        assert "exec" in content
