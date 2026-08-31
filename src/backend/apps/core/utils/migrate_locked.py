#!/usr/bin/env python
"""
One-shot migration runner with advisory lock.
Session-scoped lock safe because migrate runs before PgBouncer is attached.
Idempotent: subsequent runs will find lock already held and skip.
"""

import subprocess
import sys
from pathlib import Path


def main() -> int:
    """Run migrations inside advisory lock, return exit code."""
    import os
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    django.setup()

    from apps.core.enums import AdvisoryLockId
    from apps.core.utils.advisory_lock import advisory_lock

    manage_py = Path(__file__).resolve().parents[3] / "manage.py"
    with advisory_lock(AdvisoryLockId.MIGRATE, session=True):
        result = subprocess.run(
            [sys.executable, str(manage_py), "migrate", "--noinput"],
        )
        return result.returncode


if __name__ == "__main__":
    sys.exit(main())
