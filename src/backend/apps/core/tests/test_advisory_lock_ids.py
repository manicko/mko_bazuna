"""Unit tests for ``AdvisoryLockId`` enum values used by test infrastructure.

Each lock ID is a fixed integer allocated in ``apps/core/enums.py``. These
tests guard against accidental renumbering — a changed ID would silently
break lock serialization (e.g. the xdist conftest fixture and the seed service
could target mismatched IDs and fail to exclude each other).

Follows the pattern established in ``test_sweep_commands.py`` (e.g.
``test_lock_id_is_archive_sweep``) and ``test_seed.py``
(``test_advisory_lock_id_seed``): assert the member exists and its value is
the expected integer — both membership and magnitude.
"""

from __future__ import annotations

import pytest

from apps.core.enums import AdvisoryLockId

pytestmark = [pytest.mark.unit]


class TestTestSchemaSetupLockId:
    """Verify the advisory lock ID used by the xdist test-schema setup fixture."""

    def test_advisory_lock_id_test_schema_setup(self) -> None:
        """AdvisoryLockId.TEST_SCHEMA_SETUP resolves to 111."""
        assert AdvisoryLockId.TEST_SCHEMA_SETUP == 111
        assert AdvisoryLockId.TEST_SCHEMA_SETUP.value == 111
