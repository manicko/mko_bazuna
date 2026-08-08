#!/usr/bin/env python
"""
One-shot migration runner with advisory lock.
Session-scoped lock safe because migrate runs before PgBouncer is attached.
Idempotent: subsequent runs will find lock already held and skip.
"""

import subprocess
import sys
from pathlib import Path

from apps.core.enums import AdvisoryLockId
from apps.core.utils.advisory_lock import advisory_lock


def main() -> int:
    """Run migrations inside advisory lock, return exit code."""
    manage_py = Path(__file__).resolve().parents[3] / "manage.py"
    with advisory_lock(AdvisoryLockId.MIGRATE, session=True):
        result = subprocess.run(
            [sys.executable, str(manage_py), "migrate", "--noinput"],
        )
        return result.returncode


if __name__ == "__main__":
    sys.exit(main())