"""
Structural tests for CI/CD security scanning and deploy-check hardening.

Covers security scanning tooling (pip-audit, trivy, gitleaks) and the
dedicated `deploy-check` CI job (Block B2 / finding 12-OPS-001) that runs
``manage.py check --deploy`` against production settings. These are
non-execution tests — they assert on the structure of config files,
not on running security tools.
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


# ---------------------------------------------------------------------------
# Block B2 — CI deploy-check hardening (finding 12-OPS-001)
# ---------------------------------------------------------------------------
# The previous CI "Django deploy checks" step ran ``manage.py check --deploy``
# against ``config.settings.test``, producing 6 false-positive warnings. It is
# replaced by a dedicated, blocking ``deploy-check`` job that targets
# ``config.settings.prod`` with ``--fail-level WARNING`` and all required
# production env vars set to valid placeholders.


def _deploy_check_section() -> str:
    """Return the YAML block of the dedicated ``deploy-check`` CI job.

    The job is the last definition in ``ci.yml``, so slicing from its header to
    end-of-file isolates exactly its contents.
    """
    content = _read(".github", "workflows", "ci.yml")
    marker = "  deploy-check:"
    idx = content.index(marker)
    return content[idx:]


def test_ci_deploy_check_uses_prod_settings() -> None:
    """The deploy-check job runs check --deploy against config.settings.prod (not test)."""
    section = _deploy_check_section()
    assert "config.settings.prod" in section
    assert "config.settings.test" not in section


def test_ci_deploy_check_fails_on_warnings() -> None:
    """The deploy-check step uses --fail-level WARNING and is not continue-on-error."""
    section = _deploy_check_section()
    assert "check --deploy --fail-level WARNING" in section
    assert "continue-on-error" not in section


def test_ci_deploy_check_sets_valid_secret_key() -> None:
    """The deploy-check job sets DJANGO_SECRET_KEY to a 50+ char non-secret literal."""
    section = _deploy_check_section()
    secret_key_value: str | None = None
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith("DJANGO_SECRET_KEY:"):
            raw = stripped.split(":", 1)[1].strip()
            if (raw.startswith('"') and raw.endswith('"')) or (
                raw.startswith("'") and raw.endswith("'")
            ):
                raw = raw[1:-1]
            secret_key_value = raw
            break
    assert secret_key_value is not None, "DJANGO_SECRET_KEY not set in deploy-check job"
    assert len(secret_key_value) >= 50, (
        f"DJANGO_SECRET_KEY is {len(secret_key_value)} chars; deploy-check requires >=50"
    )
