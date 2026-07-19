#!/usr/bin/env python
"""
One-shot migration runner with advisory lock.
Session-scoped lock safe because migrate runs before PgBouncer is attached.
Idempotent: subsequent runs will find lock already held and skip.
"""

import subprocess
import sys

from apps.core.enums import AdvisoryLockId
from apps.core.utils.advisory_lock import advisory_lock


def main() -> int:
    """Run migrations inside advisory lock, return exit code."""
    with advisory_lock(AdvisoryLockId.MIGRATE, session=True):
        result = subprocess.run(
            [sys.executable, "src/backend/manage.py", "migrate", "--noinput"],
            cwd="/app",
        )
        return result.returncode


if __name__ == "__main__":
    sys.exit(main())