"""
Restore-test workflow structural tests (B5 / finding 12-OPS-006).

Asserts that the restore-test CI workflow exists with a monthly schedule and
a restore-test job, and that the Makefile restore-test target includes the
migrate --plan --check step.

Follows the same pattern as test_docs_ci_parity.py and test_deploy_workflow.py:
string-level checks via Path.read_text(), no PyYAML dependency, repo-root
resolution by searching upward for pyproject.toml.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

# Resolve repository root by searching upward for pyproject.toml.
# Robust to varying CWD in Docker (WORKDIR=/app or /app/src/backend) and
# local development (from repo root).
_ROOT = Path(__file__).resolve().parent
while not (_ROOT / "pyproject.toml").exists():
    _ROOT = _ROOT.parent

_RESTORE_YML = _ROOT / ".github" / "workflows" / "restore-test.yml"
_MAKEFILE = _ROOT / "Makefile"


# --- restore-test.yml structural tests --------------------------------------


def test_restore_test_scheduled_in_ci() -> None:
    """restore-test.yml must exist, define a schedule trigger, and contain a restore-test job."""
    assert _RESTORE_YML.exists(), (
        "restore-test.yml must exist at .github/workflows/restore-test.yml (B5 / 12-OPS-006)"
    )
    text = _RESTORE_YML.read_text()
    assert "schedule:" in text, "restore-test.yml must have a schedule trigger"
    assert "workflow_dispatch:" in text, "restore-test.yml must support manual dispatch"
    assert "restore-test:" in text, "restore-test.yml must define a restore-test job"


def test_restore_test_has_migrate_plan() -> None:
    """Makefile restore-test target must reference migrate --plan --check."""
    text = _MAKEFILE.read_text()
    target_match = re.search(r"^restore-test:\s*$", text, re.MULTILINE)
    assert target_match, "Makefile must define a restore-test target"
    target_block = text[target_match.start():]
    assert "migrate --plan --check" in target_block, (
        "Makefile restore-test target must run migrate --plan --check (B5 / 12-OPS-006)"
    )


def test_restore_test_schedule_is_monthly() -> None:
    """restore-test.yml must schedule monthly on the first Monday (cron 1-7 * 1)."""
    text = _RESTORE_YML.read_text()
    match = re.search(r'cron:\s*"([^"]+)"', text)
    assert match, "restore-test.yml must define a cron schedule"
    cron = match.group(1)
    parts = cron.split()
    assert len(parts) == 5, f"cron must have 5 fields, got {len(parts)}"
    # Day-of-month 1-7 (first week) + day-of-week 1 (Monday) = first Monday of month.
    assert parts[2] == "1-7", (
        f"day-of-month must be 1-7 for first-week cadence, got {parts[2]}"
    )
    assert parts[4] == "1", (
        f"day-of-week must be 1 (Monday), got {parts[4]}"
    )
