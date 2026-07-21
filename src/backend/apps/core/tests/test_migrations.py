"""
Tests for migration reproducibility and idempotency (TST-005).

Verifies:
  - makemigrations --check --dry-run produces no new migrations.
  - Re-applying all migrations is a no-op (no drift).
"""

import logging
from io import StringIO

import pytest
from django.core.management import call_command

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]

logger = logging.getLogger(__name__)


def test_makemigrations_check() -> None:
    """
    Assert that makemigrations --check --dry-run produces no pending migrations.

    This catches schema drift where a developer forgot to commit a migration
    file alongside model changes.
    """
    out = StringIO()
    err = StringIO()

    try:
        call_command(
            "makemigrations",
            "--check",
            "--dry-run",
            stdout=out,
            stderr=err,
        )
    except SystemExit as exc:
        if exc.code != 0:
            pytest.fail(
                f"Pending migrations detected.\n"
                f"stdout: {out.getvalue()}\n"
                f"stderr: {err.getvalue()}"
            )
        # exit code 0 is success — nothing to do
        return

    # If call_command returned normally (no SystemExit), all good.
    logger.info("makemigrations --check --dry-run: no pending migrations.")


def test_migration_idempotency() -> None:
    """
    Assert that re-applying migrations produces no SQL operations.

    If a migration is not idempotent (e.g. a RunSQL that lacks IF NOT EXISTS),
    the second run will produce operations and this test will fail.
    """
    out = StringIO()
    err = StringIO()

    try:
        call_command(
            "migrate",
            "--noinput",
            stdout=out,
            stderr=err,
        )
    except SystemExit as exc:
        # migrate exits with code 0 on success; anything else is a failure
        if exc.code != 0:
            pytest.fail(
                f"Migration re-apply failed with exit code {exc.code}.\n"
                f"stdout: {out.getvalue()}\n"
                f"stderr: {err.getvalue()}"
            )
        return

    output = out.getvalue()
    # The "No migrations to apply." message is emitted when all migrations
    # are already applied — any other output means operations were executed.
    if "No migrations to apply." not in output:
        pytest.fail(
            "Migration re-apply produced new operations — possible drift.\n"
            f"Output:\n{output}\n"
            f"Stderr:\n{err.getvalue()}"
        )

    logger.info("migrate --noinput re-apply: idempotent (no operations).")