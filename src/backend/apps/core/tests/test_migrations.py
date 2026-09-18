"""
Tests for migration reproducibility and idempotency (TST-001).

Verifies:
  - makemigrations --check --dry-run produces no pending migrations (drift check).
  - Re-applying all migrations is a no-op (idempotency / no drift).

These tests run in an isolated subprocess with migration discovery re-enabled
(config.settings.test_migrations), because the main test suite uses
DisableMigrations (syncdb-only schema) which makes migration-based assertions
meaningless. See docs/99-agent/architecture.md for the rationale.
"""

import logging
import os
import subprocess
import sys
import textwrap

import pytest

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.settings,
    pytest.mark.xdist_group("migrations"),
]

# The migration-enabled settings module (inherits test.py, sets MIGRATION_MODULES = {}).
_MIGRATION_SETTINGS = "config.settings.test_migrations"


def _migration_env() -> dict[str, str]:
    """Environment for subprocess: inherit parent env but set migration settings."""
    env = {
        k: v
        for k, v in os.environ.items()
        if k != "DJANGO_SETTINGS_MODULE"
    }
    env["DJANGO_SETTINGS_MODULE"] = _MIGRATION_SETTINGS
    env["PYTHONPATH"] = os.pathsep.join(sys.path)
    return env


# Inline script for makemigrations --check --dry-run.
# No DB needed: MigrationLoader(None) reads MIGRATION_MODULES from settings
# and does not query the database.
_MAKEMIGRATIONS_CHECK_SCRIPT = textwrap.dedent(
    """
    import sys
    import django
    django.setup()
    from django.core.management import call_command
    from io import StringIO
    out, err = StringIO(), StringIO()
    try:
        call_command("makemigrations", "--check", "--dry-run", stdout=out, stderr=err)
    except SystemExit:
        # --check exits 1 if pending migrations exist; print captured output
        # so the parent process can show it in the failure message.
        print(out.getvalue(), end="")
        print(err.getvalue(), end="", file=sys.stderr)
        raise
    """
)

# Inline script for migration idempotency check.
# Creates a fresh test database with ALL migrations replayed, then re-runs
# migrate --noinput which must report "No migrations to apply."
_MIGRATION_IDEMPOTENCY_SCRIPT = textwrap.dedent(
    """
    import django
    django.setup()
    from django.core.management import call_command
    from django.test.utils import setup_databases, teardown_databases
    from io import StringIO

    # Create a fresh test database by replaying ALL migration files in order.
    old_names = setup_databases(verbosity=0, interactive=False)

    # First migrate (should apply all migrations during DB creation).
    out1 = StringIO()
    call_command("migrate", "--noinput", stdout=out1)

    # Second migrate (should be no-op -- idempotent).
    out2 = StringIO()
    call_command("migrate", "--noinput", stdout=out2)

    if "No migrations to apply" not in out2.getvalue():
        print(f"FIRST RUN:\\n{out1.getvalue()}")
        print(f"SECOND RUN:\\n{out2.getvalue()}")
        raise SystemExit(1)

    teardown_databases(old_names, verbosity=0)
    """
)


@pytest.mark.slow
def test_makemigrations_check() -> None:
    """Assert that makemigrations --check --dry-run produces no pending migrations.

    Runs in an isolated subprocess with config.settings.test_migrations,
    which sets MIGRATION_MODULES = {} (real migration files discoverable).
    """
    result = subprocess.run(
        [sys.executable, "-c", _MAKEMIGRATIONS_CHECK_SCRIPT],
        env=_migration_env(),
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        pytest.fail(
            f"Pending migrations detected.\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
    logger.info("makemigrations --check --dry-run: no pending migrations.")


@pytest.mark.slow
def test_migration_idempotency() -> None:
    """Assert that re-applying migrations is a no-op (idempotent).

    Runs in an isolated subprocess that creates a FRESH test database
    (test_migration_repro) by replaying ALL migration files in order,
    then verifies a second migrate --noinput is a no-op.
    """
    result = subprocess.run(
        [sys.executable, "-c", _MIGRATION_IDEMPOTENCY_SCRIPT],
        env=_migration_env(),
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        pytest.fail(
            f"Migration idempotency check failed.\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
    logger.info("migrate --noinput re-apply: idempotent (no operations).")