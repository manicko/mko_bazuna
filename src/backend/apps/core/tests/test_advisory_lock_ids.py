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

import ast
from pathlib import Path

import pytest

from apps.core.enums import AdvisoryLockId

pytestmark = [pytest.mark.unit]


# Resolve repository root by searching upward for pyproject.toml.

_ROOT = Path(__file__).resolve().parent
while not (_ROOT / "pyproject.toml").exists():
    _ROOT = _ROOT.parent

_SRC_BACKEND = _ROOT / "src" / "backend"
_SRC_TELEGRAM_BOT = _ROOT / "src" / "telegram_bot"


class TestTestSchemaSetupLockId:
    """Verify the advisory lock ID used by the xdist test-schema setup fixture."""

    def test_advisory_lock_id_test_schema_setup(self) -> None:
        """AdvisoryLockId.TEST_SCHEMA_SETUP resolves to 111."""
        assert AdvisoryLockId.TEST_SCHEMA_SETUP == 111
        assert AdvisoryLockId.TEST_SCHEMA_SETUP.value == 111


class TestSweepOrphanedMediaLockId:
    """Verify the advisory lock ID for the orphaned-media reconciliation sweep."""

    def test_advisory_lock_id_sweep_orphaned_media(self) -> None:
        """AdvisoryLockId.SWEEP_ORPHANED_MEDIA resolves to 103."""
        assert AdvisoryLockId.SWEEP_ORPHANED_MEDIA == 103
        assert AdvisoryLockId.SWEEP_ORPHANED_MEDIA.value == 103


class TestCatalogLoadLockId:
    """Verify the advisory lock ID used by the catalog builder."""

    def test_advisory_lock_id_catalog_load(self) -> None:
        """AdvisoryLockId.CATALOG_LOAD resolves to 104."""
        assert AdvisoryLockId.CATALOG_LOAD == AdvisoryLockId(104)
        assert AdvisoryLockId.CATALOG_LOAD.value == 104


class TestAdvisoryLockIdReferences:
    """AST-scan all source to ensure every ``AdvisoryLockId.*`` reference
    resolves to a member defined on the ``AdvisoryLockId`` enum.

    Guards against typos (e.g. ``AdvisoryLockId.CATALO_LOAD``) that would
    silently fall through to ``IntEnum`` value lookup and return an
    unexpected integer at ``getattr`` rather than raising ``ValueError``.
    """

    def test_all_references_are_valid_members(self) -> None:
        """Every ``AdvisoryLockId.*`` attribute access in ``src/backend/`` and
        ``src/telegram_bot/`` must reference a member defined on the enum.
        """
        valid_members = {m.name for m in AdvisoryLockId}
        referenced: set[str] = set()
        for src_dir in (_SRC_BACKEND, _SRC_TELEGRAM_BOT):
            if src_dir.exists():
                for py_file in src_dir.rglob("*.py"):
                    tree = ast.parse(py_file.read_text(), filename=str(py_file))
                    for node in ast.walk(tree):
                        if (
                            isinstance(node, ast.Attribute)
                            and isinstance(node.value, ast.Name)
                            and node.value.id == "AdvisoryLockId"
                        ):
                            referenced.add(node.attr)
        unknown = referenced - valid_members
        assert not unknown, (
            f"AdvisoryLockId.* references not defined as enum members: "
            f"{sorted(unknown)}"
        )
