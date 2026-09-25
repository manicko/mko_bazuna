"""
Structural tests for the production deployment workflow (``deploy.yml``).

Covers the automated image-tag rollback logic added in Block 2 of Plan 0016
(finding 12-OPS-010).  These are non-execution tests — they assert on the
structure of the YAML file, not on a running deployment.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.conf import settings

pytestmark = [pytest.mark.unit]
_PROJECT_ROOT = settings.BASE_DIR.parent


def _read(*parts: str) -> str:
    """Read a text file from the project root."""
    return (_PROJECT_ROOT / Path(*parts)).read_text(encoding="utf-8")


def test_deploy_workflow_has_rollback_step() -> None:
    """deploy.yml contains an automated rollback branch triggered by health-check failure."""
    text = _read(".github", "workflows", "deploy.yml")
    assert "rollback" in text.lower(), "deploy.yml must reference rollback"
    assert "PREVIOUS_IMAGE_TAG" in text or "previous_tag" in text, (
        "deploy.yml must capture a previous image tag variable"
    )
    assert "force-recreate" in text or "up -d" in text, (
        "deploy.yml must recreate services during rollback (force-recreate or up -d)"
    )
