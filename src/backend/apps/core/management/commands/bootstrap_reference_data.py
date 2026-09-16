"""Management command to bootstrap all reference data on container startup.

Delegates to ``apps.core.utils.migrate_locked.main()``, which runs
``migrate --run-syncdb``, ``setup_search_triggers``, ``load_exchange_rates``,
and optionally ``backfill_translations`` (when ``RUN_TRANSLATION_BACKFILL=true``)
as a single atomic sequence under the ``AdvisoryLockId.MIGRATE`` (100)
session-scoped advisory lock. The optional backfill step is env-gated so that
operators can trigger a one-time translation backfill for pre-existing ads
without it running on every container start.

This command replaces the duplicated
``python -c 'from apps.core.utils.migrate_locked import main; sys.exit(main())'``
incantation that was copy-pasted across the prod Docker compose file, the CI
workflow files, and the test entrypoint (ENT-033, ENT-036). It is a thin
wrapper that preserves the lock + subprocess semantics of ``migrate_locked`` —
the session-scoped PostgreSQL lock must be held by a **parent** process across
all child ``manage.py`` subprocess invocations, which is why the delegation uses
``migrate_locked.main()`` (subprocess-aware) rather than ``call_command``
(in-process).

``conftest.py`` deliberately does **not** use this command: it calls
``call_command`` in-process under ``AdvisoryLockId.TEST_SCHEMA_SETUP`` (111)
instead, because ``migrate_locked.main()`` spawns subprocesses that would
connect to the hardcoded ``mko_bazuna`` database rather than pytest-django's
``test_mko_bazuna`` test database (``call_command`` swaps the DB name only on
the in-process connection).
"""

import logging

from django.core.management.base import BaseCommand

from apps.core.utils.migrate_locked import main as _migrate_locked_main

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Run the full reference-data bootstrap sequence under the MIGRATE lock.

    Executes ``migrate --run-syncdb``, ``setup_search_triggers``,
    ``load_exchange_rates``, and optionally ``backfill_translations`` (when
    ``RUN_TRANSLATION_BACKFILL=true``) in sequence inside
    ``AdvisoryLockId.MIGRATE`` (100) so that all post-migration setup is
    serialized by a single advisory lock, replacing the previous
    ``&&``-chained shell command that released the lock between steps.
    """

    help = (
        "Run migrate --run-syncdb, setup_search_triggers, and "
        "load_exchange_rates inside the MIGRATE advisory lock (ID 100). "
        "Includes backfill_translations when RUN_TRANSLATION_BACKFILL=true. "
        "Single entrypoint for prod compose, CI, and test container."
    )

    def handle(self, *args, **options) -> None:
        """Delegate to ``migrate_locked.main()`` and propagate the exit code.

        ``migrate_locked.main()`` runs all post-migration steps as
        subprocesses under the session-scoped ``MIGRATE`` lock and returns the
        first non-zero exit code (or ``0`` on full success). The optional
        ``backfill_translations`` step is included when
        ``RUN_TRANSLATION_BACKFILL=true``. We re-raise as ``SystemExit`` so
        Docker one-shot services and CI observe the real exit code, preserving
        the fail-closed semantics of the original chain.
        """
        exit_code = _migrate_locked_main()
        if exit_code != 0:
            self.stderr.write(
                self.style.ERROR(
                    f"Bootstrap reference data failed (exit code {exit_code})"
                )
            )
            raise SystemExit(exit_code)
        self.stdout.write(
            self.style.SUCCESS("Bootstrap reference data completed successfully")
        )
