"""
Tests for the ``bootstrap_reference_data`` management command (ENT-033, ENT-036).

Verifies:
  - Command discoverability via Django's management utility registry.
  - Delegation: the command calls ``migrate_locked.main()`` exactly once.
  - Exit-code propagation: ``0`` -> success message, non-zero -> ``SystemExit``
    preserving the exact code (so Docker/CI observe the real failure).
  - The command does NOT acquire its own advisory lock - delegation alone is
    what enforces lock discipline (the lock lives in ``migrate_locked.main``).

These are pure unit tests - ``migrate_locked.main`` is mocked because it spawns
subprocesses and connects to the DB, neither of which is meaningful to test
inside a DB-less pytest-xdist worker.
"""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command, get_commands

# Patch target: the name ``_migrate_locked_main`` bound inside the command
# module's namespace (imported via
# ``from apps.core.utils.migrate_locked import main as _migrate_locked_main``).
# Patching here intercepts the call at the command boundary without touching
# the real ``migrate_locked`` module.
_PATCH_TARGET = (
    "apps.core.management.commands.bootstrap_reference_data._migrate_locked_main"
)

pytestmark = [pytest.mark.unit]


class TestBootstrapReferenceDataDiscoverability:
    """The command is registered and discoverable by Django."""

    def test_command_is_discoverable(self) -> None:
        """``bootstrap_reference_data`` appears in ``get_commands()`` output."""
        assert "bootstrap_reference_data" in get_commands()


class TestBootstrapReferenceDataDelegation:
    """The command delegates to ``migrate_locked.main()``."""

    def test_calls_migrate_locked_main(self) -> None:
        """``handle`` invokes ``migrate_locked.main()`` exactly once."""
        out = StringIO()
        with patch(_PATCH_TARGET, return_value=0) as mock_main:
            call_command("bootstrap_reference_data", stdout=out)
        mock_main.assert_called_once_with()

    def test_does_not_acquire_own_lock(self) -> None:
        """The command delegates lock acquisition to ``migrate_locked`` - it
        must not import or call ``advisory_lock`` itself (which would
        double-acquire or conflict with the MIGRATE lock held by the
        subprocess parent)."""
        from apps.core.management.commands import bootstrap_reference_data

        assert not hasattr(bootstrap_reference_data, "advisory_lock")


class TestBootstrapReferenceDataExitCode:
    """Exit-code propagation to Docker and CI."""

    def test_zero_exit_code_succeeds(self) -> None:
        """When ``migrate_locked.main()`` returns 0, the command prints success."""
        out = StringIO()
        err = StringIO()
        with patch(_PATCH_TARGET, return_value=0):
            call_command("bootstrap_reference_data", stdout=out, stderr=err)
        assert "completed successfully" in out.getvalue()
        assert err.getvalue() == ""

    def test_nonzero_exit_code_raises_system_exit(self) -> None:
        """When ``migrate_locked.main()`` returns non-zero, ``SystemExit`` is
        raised with that exact code so Docker/CI observe the failure."""
        with patch(_PATCH_TARGET, return_value=1):
            with pytest.raises(SystemExit) as exc_info:
                call_command("bootstrap_reference_data")
        assert exc_info.value.code == 1

    def test_nonzero_exit_code_2_preserved(self) -> None:
        """Exit codes other than 1 (e.g. 2 from argparse) must also propagate."""
        with patch(_PATCH_TARGET, return_value=2):
            with pytest.raises(SystemExit) as exc_info:
                call_command("bootstrap_reference_data")
        assert exc_info.value.code == 2

    def test_nonzero_writes_error_to_stderr(self) -> None:
        """The failure path emits an error message to stderr before exiting."""
        out = StringIO()
        err = StringIO()
        with patch(_PATCH_TARGET, return_value=1):
            with pytest.raises(SystemExit):
                call_command("bootstrap_reference_data", stdout=out, stderr=err)
        assert "Bootstrap reference data failed" in err.getvalue()
        assert "exit code 1" in err.getvalue()
