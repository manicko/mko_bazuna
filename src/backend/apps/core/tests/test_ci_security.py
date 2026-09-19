"""
Structural tests for CI/CD security scanning (Block 2: OPS-002 + OPS-007).

Verifies that the CI pipeline includes security scanning tooling and
configuration files exist. These are non-execution tests — they assert
on the structure of config files, not on running security tools.
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


def test_ci_yml_has_security_scan_tools() -> None:
    """ci.yml references pip-audit, trivy, and gitleaks (>= 3 tools)."""
    content = _read(".github", "workflows", "ci.yml")
    tools = ["pip-audit", "trivy", "gitleaks"]
    found = sum(1 for t in tools if t in content)
    assert found >= 3, f"Only found {found}/3 security scanning tools in ci.yml"


def test_ci_yml_has_security_job() -> None:
    """ci.yml defines a 'security' job."""
    content = _read(".github", "workflows", "ci.yml")
    assert "  security:" in content


def test_security_steps_are_blocking() -> None:
    """Security scan steps in ci.yml are blocking (no continue-on-error; Trivy/gitleaks use exit-code: 1)."""
    content = _read(".github", "workflows", "ci.yml")
    assert "continue-on-error: true" not in content
    assert "exit-code: 1" in content
    assert "--exit-code 1" in content


def test_dependabot_config_exists() -> None:
    """.github/dependabot.yml exists with github-actions and uv ecosystems."""
    dependabot_path = _PROJECT_ROOT / ".github" / "dependabot.yml"
    assert dependabot_path.exists(), "dependabot.yml not found"
    content = dependabot_path.read_text(encoding="utf-8")
    assert "github-actions" in content
    assert "uv" in content


def test_dockerfile_has_sbom_generation() -> None:
    """Dockerfile builder stage generates a CycloneDX SBOM (via syft)."""
    content = _read("docker", "Dockerfile")
    assert "sbom" in content.lower()
    assert "syft" in content.lower() or "cyclonedx" in content.lower()


def test_dockerfile_copies_sbom_to_runtime() -> None:
    """Builder-stage SBOM is copied into the runtime image."""
    content = _read("docker", "Dockerfile")
    assert "sbom.cyclonedx.json" in content


def test_build_job_has_trivy_image_scan() -> None:
    """Build job scans the Docker image with Trivy."""
    content = _read(".github", "workflows", "ci.yml")
    assert "Scan Docker image for vulnerabilities" in content
    assert "trivy" in content.lower()


def test_gitleaks_config_exists() -> None:
    """.gitleaks.toml exists for allowlist configuration."""
    gitleaks_path = _PROJECT_ROOT / ".gitleaks.toml"
    assert gitleaks_path.exists(), ".gitleaks.toml not found"
    content = gitleaks_path.read_text(encoding="utf-8")
    assert "allowlists" in content


def test_pip_audit_in_dev_deps() -> None:
    """pip-audit is listed in pyproject.toml dev dependencies."""
    content = _read("pyproject.toml")
    assert "pip-audit" in content
