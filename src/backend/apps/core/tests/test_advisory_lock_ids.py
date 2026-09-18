"""Unit tests for ``AdvisoryLockId`` enum integrity.

Advisory lock IDs are fixed integers allocated in ``apps/core/enums.py``.
These tests guard against:

- **Missing or renamed members** — if a member referenced in the codebase
  is deleted or renamed, the AST + grep reference scan catches it at test
  time rather than letting it fail silently with ``AttributeError`` or
  ``ValueError`` at runtime.
- **Typo references** (e.g. ``AdvisoryLockId.CATALO_LOAD``) that would
  silently fall through to ``IntEnum`` value lookup and return an
  unexpected integer instead of raising ``ValueError``.
- **Invalid member names** — every member name must be a valid Python
  identifier so that ``AdvisoryLockId.MEMBER`` attribute access works
  reliably.

Follows the pattern established in ``test_sweep_commands.py`` and
``test_seed.py`` for advisory lock verification.

The specific integer *values* (e.g. 104, 111) are no longer asserted
directly — they are an implementation detail that can evolve.  Instead we
verify member existence, value type, and reference validity.
"""

from __future__ import annotations

import ast
import re
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


class TestAdvisoryLockIdMembers:
    """Verify expected advisory lock members exist with valid values."""

    def test_test_schema_setup_lock_member(self) -> None:
        """AdvisoryLockId.TEST_SCHEMA_SETUP exists with a valid int value."""
        assert hasattr(AdvisoryLockId, "TEST_SCHEMA_SETUP")
        member = AdvisoryLockId.TEST_SCHEMA_SETUP
        assert isinstance(member.value, int)
        assert member.name == "TEST_SCHEMA_SETUP"

    def test_sweep_orphaned_media_lock_member(self) -> None:
        """AdvisoryLockId.SWEEP_ORPHANED_MEDIA exists with a valid int value."""
        assert hasattr(AdvisoryLockId, "SWEEP_ORPHANED_MEDIA")
        member = AdvisoryLockId.SWEEP_ORPHANED_MEDIA
        assert isinstance(member.value, int)
        assert member.name == "SWEEP_ORPHANED_MEDIA"

    def test_catalog_load_lock_member(self) -> None:
        """AdvisoryLockId.CATALOG_LOAD exists with a valid int value."""
        assert hasattr(AdvisoryLockId, "CATALOG_LOAD")
        member = AdvisoryLockId.CATALOG_LOAD
        assert isinstance(member.value, int)
        assert member.name == "CATALOG_LOAD"


class TestAdvisoryLockIdReferences:
    """Scan all source to ensure every ``AdvisoryLockId.*`` reference
    resolves to a member defined on the ``AdvisoryLockId`` enum.

    Guards against typos (e.g. ``AdvisoryLockId.CATALO_LOAD``) that would
    silently fall through to ``IntEnum`` value lookup and return an
    unexpected integer at ``getattr`` rather than raising ``ValueError``.
    """

    def test_all_references_are_valid_members(self) -> None:
        """Every ``AdvisoryLockId.*`` reference in ``src/backend/`` and
        ``src/telegram_bot/`` must reference a member defined on the enum.

        Uses two complementary strategies:
        - AST walking catches standard ``AdvisoryLockId.MEMBER`` attribute
          access.
        - String grep catches references that AST might miss (e.g. aliased
          imports, ``getattr``, or dynamically constructed references).

        The test file itself is excluded from the scan to avoid false
        positives from docstrings that mention illustrative typos.
        """
        valid_members = {m.name for m in AdvisoryLockId}
        referenced: set[str] = set()
        current_file = Path(__file__).resolve()

        for src_dir in (_SRC_BACKEND, _SRC_TELEGRAM_BOT):
            if src_dir.exists():
                for py_file in src_dir.rglob("*.py"):
                    if py_file.resolve() == current_file:
                        continue
                    source = py_file.read_text()
                    # AST-based detection catches standard attribute access.
                    tree = ast.parse(source, filename=str(py_file))
                    for node in ast.walk(tree):
                        if (
                            isinstance(node, ast.Attribute)
                            and isinstance(node.value, ast.Name)
                            and node.value.id == "AdvisoryLockId"
                        ):
                            referenced.add(node.attr)
                    # String-based grep catches references AST might miss.
                    for match in re.finditer(r"AdvisoryLockId\.(\w+)", source):
                        referenced.add(match.group(1))

        unknown = referenced - valid_members
        assert not unknown, (
            f"AdvisoryLockId.* references not defined as enum members: "
            f"{sorted(unknown)}"
        )

    def test_all_enum_members_are_valid_identifiers(self) -> None:
        """Every ``AdvisoryLockId`` member name is a valid Python identifier.

        If a member name were not a valid identifier, attribute access
        (``AdvisoryLockId.MEMBER``) would fail while ``AdvisoryLockId("value")``
        would still succeed, making the reference scan above unreliable.
        """
        for member in AdvisoryLockId:
            assert member.name.isidentifier(), (
                f"AdvisoryLockId.{member.name} is not a valid Python identifier"
            )
