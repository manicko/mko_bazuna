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


# ---------------------------------------------------------------------------
# SAST scanning (bandit) — finding 12-OPS-001
# ---------------------------------------------------------------------------
# The security job runs bandit SAST. The step previously ran with
# ``working-directory: src/backend`` and repo-relative scan roots, so bandit
# resolved ``src/backend/src/backend`` and ``src/backend/pyproject.toml`` — both
# absent — and aborted with exit 2, scanning zero files. The guard below is a
# contract, not a substring check: it parses the SAST step, proves the configured
# config path and scan roots exist from the step's working directory, and runs
# bandit to assert a non-zero scanned-file count. Test trees are excluded via
# the [tool.bandit] ``exclude_dirs`` config.

# The step's name in ci.yml, used to locate it in the parsed document.
_SAST_STEP_NAME = "Run SAST (bandit)"

# Minimum number of source files a correct scan must touch. The repository has
# ~357 production Python files; a path-relativity regression collapses this to
# zero, so any non-zero floor catches it. The floor is deliberately well below
# the real count so ordinary file churn never trips it.
_MIN_SCANNED_FILES = 250


def _sast_step() -> dict:
    """Return the parsed SAST step mapping from ci.yml, proving it was found."""
    from ruamel.yaml import YAML

    content = _read(".github", "workflows", "ci.yml")
    document = YAML(typ="safe").load(content)
    assert isinstance(document, dict), "ci.yml must parse to a mapping"
    jobs = document.get("jobs")
    assert isinstance(jobs, dict), "ci.yml 'jobs' must be a mapping"
    security = jobs.get("security")
    assert isinstance(security, dict), "ci.yml has no 'security' job"
    steps = security.get("steps")
    assert isinstance(steps, list), "ci.yml 'security.steps' must be a list"
    for step in steps:
        if isinstance(step, dict) and step.get("name") == _SAST_STEP_NAME:
            return step
    raise AssertionError(f"ci.yml security job has no step named {_SAST_STEP_NAME!r}")


def _scan_roots_and_config(run: str) -> tuple[list[str], str]:
    """Parse ``-r <roots> -c <config>`` out of a bandit ``run`` command."""
    tokens = run.split()
    assert "-r" in tokens, f"bandit run must pass -r; got: {run!r}"
    assert "-c" in tokens, f"bandit run must pass -c; got: {run!r}"
    r_idx = tokens.index("-r")
    c_idx = tokens.index("-c")
    roots = tokens[r_idx + 1 : c_idx]
    config = tokens[c_idx + 1]
    return roots, config


def test_ci_yml_has_sast_job() -> None:
    """ci.yml defines a bandit SAST step with resolvable roots and config.

    This replaced a bare ``assert "bandit" in content``, which could not tell a
    working step from one that scanned nothing (project rule 2: production code
    is king — the old assertion let a permanently-red, no-op gate ship).
    """
    step = _sast_step()
    run = str(step.get("run", ""))
    assert "bandit" in run, f"SAST step must invoke bandit; got: {run!r}"
    working_dir = str(step.get("working-directory", "."))
    roots, config = _scan_roots_and_config(run)

    base = _PROJECT_ROOT if working_dir in (".", "./") else _PROJECT_ROOT / working_dir
    # The config path must resolve from the step's working directory — this is
    # exactly what broke: src/backend/pyproject.toml does not exist.
    config_path = base / config
    assert config_path.is_file(), (
        f"bandit config {config!r} does not resolve to {config_path} from "
        f"working-directory {working_dir!r}; bandit aborts with exit 2"
    )
    # Every scan root must resolve from the step's working directory.
    for root in roots:
        root_path = base / root
        assert root_path.is_dir(), (
            f"bandit scan root {root!r} does not resolve to {root_path} from "
            f"working-directory {working_dir!r}; bandit aborts with exit 2"
        )


def test_sast_step_actually_scans_files() -> None:
    """Run bandit as configured and assert a non-zero scanned-file count.

    A guard that only checks paths can still pass a step that scans nothing. This
    executes the configured command and reads bandit's own file metric, so a
    future path-relativity regression (or an over-broad ``exclude_dirs``) fails
    here instead of silently passing.
    """
    import json
    import shutil
    import subprocess
    import tempfile

    step = _sast_step()
    run = str(step.get("run", ""))
    working_dir = str(step.get("working-directory", "."))
    roots, config = _scan_roots_and_config(run)
    base = _PROJECT_ROOT if working_dir in (".", "./") else _PROJECT_ROOT / working_dir

    bandit = shutil.which("bandit")
    if bandit is None:
        # `uv run bandit` is the CI form; resolve it through uv if present.
        uv = shutil.which("uv")
        assert uv is not None, (
            "neither bandit nor uv is on PATH; the SAST contract cannot be checked"
        )
        argv = [uv, "run", "bandit"]
    else:
        argv = [bandit]

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as fh:
        report_path = fh.name
    try:
        argv += ["-r", *roots, "-c", config, "-f", "json", "-o", report_path]
        result = subprocess.run(
            argv,
            cwd=base,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        assert result.returncode in (0, 1), (
            f"bandit must exit 0 (clean) or 1 (findings), never 2 (abort): "
            f"got {result.returncode}\n{result.stderr[-2000:]}"
        )
        with open(report_path, encoding="utf-8") as report:
            payload = json.load(report)
    finally:
        import os

        os.unlink(report_path)

    metrics = payload.get("metrics", {})
    scanned = len([key for key in metrics if key != "_totals"])
    assert scanned >= _MIN_SCANNED_FILES, (
        f"bandit scanned only {scanned} files (expected >= {_MIN_SCANNED_FILES}); "
        f"the scan roots or exclude_dirs no longer cover the repository"
    )


def test_bandit_in_dev_deps() -> None:
    """pyproject.toml lists a SAST tool (bandit or semgrep) in dev dependencies."""
    content = _read("pyproject.toml")
    assert "bandit" in content or "semgrep" in content


def test_bandit_has_config_section() -> None:
    """pyproject.toml contains a [tool.bandit] configuration section."""
    content = _read("pyproject.toml")
    assert "[tool.bandit]" in content
