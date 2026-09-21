#!/usr/bin/env python
"""
One-shot migration runner with advisory lock.
Session-scoped lock safe because migrate runs before PgBouncer is attached.
Idempotent: subsequent runs will find lock already held and skip.

Runs ``migrate --run-syncdb``, ``setup_search_triggers --backfill``,
``load_exchange_rates``, and optionally ``backfill_translations`` (when
``RUN_TRANSLATION_BACKFILL=true`` inside the single session-scoped lock,
replacing the previous ``&&`` shell chain that released the lock between steps.

``--backfill`` on ``setup_search_triggers`` ensures trigger-populated vectors
for existing rows during bootstrap, preventing regrowth of NULL vectors from
``COPY`` or pre-trigger inserts. Idempotent: subsequent runs update 0 rows.

``--run-syncdb`` ensures tables are created for unmigrated apps. When the test
settings (``MIGRATION_MODULES = DisableMigrations``) are active, ALL apps
— including Django built-ins like ``contenttypes`` and ``auth`` — are treated
as unmigrated, so ``migrate`` alone creates no tables and the post-migrate
signal crashes on the missing ``django_content_type`` table. With normal
(dev/prod) settings, ``--run-syncdb`` is a harmless no-op because every app
has migrations.
"""

import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _build_steps() -> tuple[tuple[str, ...], ...]:
    """Build the ordered tuple of post-migration setup steps.

    The first three steps (``migrate``, ``setup_search_triggers --backfill``,
    ``load_exchange_rates``) always run. The optional fourth step
    (``backfill_translations``) is included only when the
    ``RUN_TRANSLATION_BACKFILL`` environment variable is set to ``"true"``,
    allowing operators to trigger a one-time translation backfill during
    bootstrap without it running by default.
    """
    steps_list: list[tuple[str, ...]] = [
        ("migrate", "--noinput", "--run-syncdb"),
        ("setup_search_triggers", "--backfill"),
        ("load_exchange_rates",),
    ]
    if os.getenv("RUN_TRANSLATION_BACKFILL") == "true":
        steps_list.append(("backfill_translations",))
        logger.info("Translation backfill enabled (RUN_TRANSLATION_BACKFILL=true)")
    return tuple(steps_list)


def main() -> int:
    """Run migration and post-migration setup inside the advisory lock.

    Executes ``migrate --run-syncdb``, ``setup_search_triggers``,
    ``load_exchange_rates``, and optionally ``backfill_translations`` (when
    ``RUN_TRANSLATION_BACKFILL=true``) in sequence under
    ``AdvisoryLockId.MIGRATE``. All steps run regardless of individual
    failures so that a DDL error in one command does not starve the others
    (fixing the previous ``&&`` shell-chain coupling). Returns the first
    non-zero exit code, or 0 if all succeeded.
    """
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    django.setup()

    from apps.core.enums import AdvisoryLockId
    from apps.core.utils.advisory_lock import advisory_lock

    manage_py = Path(__file__).resolve().parents[3] / "manage.py"
    with advisory_lock(AdvisoryLockId.MIGRATE, session=True):
        steps: tuple[tuple[str, ...], ...] = _build_steps()
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
