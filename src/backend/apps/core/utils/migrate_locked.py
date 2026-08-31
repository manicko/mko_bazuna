#!/usr/bin/env python
"""
One-shot migration runner with advisory lock.
Session-scoped lock safe because migrate runs before PgBouncer is attached.
Idempotent: subsequent runs will find lock already held and skip.

``--run-syncdb`` ensures tables are created for unmigrated apps. When the test
settings (``MIGRATION_MODULES = DisableMigrations``) are active, ALL apps
— including Django built-ins like ``contenttypes`` and ``auth`` — are treated
as unmigrated, so ``migrate`` alone creates no tables and the post-migrate
signal crashes on the missing ``django_content_type`` table. With normal
(dev/prod) settings, ``--run-syncdb`` is a harmless no-op because every app
has migrations.
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
            [sys.executable, str(manage_py), "migrate", "--noinput", "--run-syncdb"],
        )
        return result.returncode


if __name__ == "__main__":
    sys.exit(main())
