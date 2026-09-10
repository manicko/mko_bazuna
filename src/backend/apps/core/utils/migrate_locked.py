#!/usr/bin/env python
"""
One-shot migration runner with advisory lock.
Session-scoped lock safe because migrate runs before PgBouncer is attached.
Idempotent: subsequent runs will find lock already held and skip.

Runs ``migrate --run-syncdb``, ``setup_search_triggers``, and
``load_exchange_rates`` inside the single session-scoped lock, replacing the
previous ``&&`` shell chain that released the lock between steps.

``--run-syncdb`` ensures tables are created for unmigrated apps. When the test
settings (``MIGRATION_MODULES = DisableMigrations``) are active, ALL apps
— including Django built-ins like ``contenttypes`` and ``auth`` — are treated
as unmigrated, so ``migrate`` alone creates no tables and the post-migrate
signal crashes on the missing ``django_content_type`` table. With normal
(dev/prod) settings, ``--run-syncdb`` is a harmless no-op because every app
has migrations.
"""

import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def main() -> int:
    """Run migration and post-migration setup inside the advisory lock.

    Executes ``migrate --run-syncdb``, ``setup_search_triggers``, and
    ``load_exchange_rates`` in sequence under ``AdvisoryLockId.MIGRATE``.
    All three steps run regardless of individual failures so that a DDL
    error in one command does not starve the others (fixing the previous
    ``&&`` shell-chain coupling). Returns the first non-zero exit code, or
    0 if all succeeded.
    """
    import os

    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    django.setup()

    from apps.core.enums import AdvisoryLockId
    from apps.core.utils.advisory_lock import advisory_lock

    manage_py = Path(__file__).resolve().parents[3] / "manage.py"
    with advisory_lock(AdvisoryLockId.MIGRATE, session=True):
        steps: tuple[tuple[str, ...], ...] = (
            ("migrate", "--noinput", "--run-syncdb"),
            ("setup_search_triggers",),
            ("load_exchange_rates",),
        )
        first_error: int | None = None
        for argv in steps:
            cmd = [sys.executable, str(manage_py), *argv]
            logger.info("Running %s", " ".join(cmd))
            result = subprocess.run(cmd)
            if result.returncode != 0 and first_error is None:
                first_error = result.returncode
                logger.error(
                    "manage.py %s exited with code %d",
                    " ".join(argv),
                    result.returncode,
                )
        return first_error if first_error is not None else 0


if __name__ == "__main__":
    sys.exit(main())
