"""
Deployment workflow structural tests (B4 / finding 12-OPS-005).

Asserts that the deploy workflow exists and contains the required
deploy-safety mechanisms: SSH-based deployment, pre-deploy backup,
health-check gating on /health/ready/, rollback documentation
reference, and the connection-draining stop_grace_period on the
production web service.

Follows the same pattern as test_compose_hardening.py and
test_docs_ci_parity.py: string-level checks via Path.read_text(),
no PyYAML dependency, repo-root resolution by searching upward
for pyproject.toml.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

# Resolve repository root by searching upward for pyproject.toml.
# Robust to varying CWD in Docker (WORKDIR=/app or /app/src/backend) and
# local development (from repo root).
_ROOT = Path(__file__).resolve().parent
while not (_ROOT / "pyproject.toml").exists():
    _ROOT = _ROOT.parent

_DEPLOY_YML = _ROOT / ".github" / "workflows" / "deploy.yml"
_PROD_COMPOSE = _ROOT / "docker-compose.prod.yml"


def _service_block(compose_path: Path, service_name: str) -> str:
    """Extract a service's YAML block from a compose file.

    Services are 2-space-indented keys under ``services:``.  The block
    extends until the next 2-space service definition or a 0-indent
    top-level key (e.g. ``volumes:``).
    """
    text = compose_path.read_text()
    pattern = rf"^  {re.escape(service_name)}:\s*$"
    lines = text.split("\n")
    start = None
    for i, line in enumerate(lines):
        if re.match(pattern, line):
            start = i
            break
    if start is None:
        return ""
    block: list[str] = [lines[start]]
    for line in lines[start + 1 :]:
        # Stop at a 0-indented top-level key (not a comment or empty line).
        if line and not line.startswith(" "):
            break
        # Stop at the next sibling service (exactly 2-space indent).
        if re.match(r"^  [A-Za-z_][A-Za-z0-9_]*:\s*$", line):
            break
        block.append(line)
    return "\n".join(block)


# --- deploy.yml structural tests -------------------------------------------


def test_deploy_workflow_exists() -> None:
    """deploy.yml must exist at .github/workflows/deploy.yml."""
    assert _DEPLOY_YML.exists(), (
        "deploy.yml must exist at .github/workflows/deploy.yml (B4 / 12-OPS-005)"
    )


def test_deploy_workflow_uses_ssh_action() -> None:
    """deploy.yml must use appleboy/ssh-action for remote deployment."""
    text = _DEPLOY_YML.read_text()
    assert "appleboy/ssh-action" in text, (
        "deploy.yml must use appleboy/ssh-action@v1.2.0 for SSH-based deployment"
    )


def test_deploy_workflow_has_health_check() -> None:
    """deploy.yml must gate deployment on /health/ready/ (readiness endpoint)."""
    text = _DEPLOY_YML.read_text()
    assert "/health/ready/" in text, (
        "deploy.yml must reference /health/ready/ in the health-check gate"
    )
    # Verify it's in a health-check context (not just a stray comment).
    assert re.search(r"health.?check", text, re.IGNORECASE), (
        "deploy.yml must contain a health-check step that uses /health/ready/"
    )


def test_deploy_workflow_has_backup_step() -> None:
    """deploy.yml must create a pre-deploy database backup via pg_dump."""
    text = _DEPLOY_YML.read_text()
    assert "pg_dump" in text, (
        "deploy.yml must run pg_dump for a pre-deploy database backup"
    )
    assert "backup" in text.lower(), (
        "deploy.yml must reference backup in a backup step"
    )


def test_deploy_workflow_has_rollback_reference() -> None:
    """deploy.yml must reference the rollback runbook (docs/ops/rollback.md)."""
    text = _DEPLOY_YML.read_text()
    assert "rollback" in text.lower(), (
        "deploy.yml must reference rollback on failure"
    )
    assert "rollback.md" in text, (
        "deploy.yml must reference docs/ops/rollback.md on failure"
    )


# --- docker-compose.prod.yml structural test -------------------------------


def test_deploy_health_check_uses_docker_exec() -> None:
    """deploy.yml health-check must use ``docker compose exec`` not bare ``curl localhost:8000``.

    Port 8000 is NOT published in production (docker-compose.yml:262 comment;
    docker-compose.prod.yml web service has no ``ports:`` section). The SSH
    script runs on the host, so ``curl http://localhost:8000`` would hit the
    host's port 8000 (Connection refused). The health-check must run curl inside
    the web container via ``docker compose exec -T web curl ...``.
    """
    text = _DEPLOY_YML.read_text()
    assert "docker compose exec" in text, (
        "deploy.yml health-check must use `docker compose exec` to reach the web "
        "container (port 8000 is not published on the host in production)"
    )
    assert "docker compose exec -T web curl" in text, (
        "deploy.yml health-check must use `docker compose exec -T web curl` "
        "(the -T flag disables pseudo-TTY allocation, required for piped output in scripts)"
    )
    # Ensure the broken pattern (bare curl without docker compose exec prefix) is NOT present.
    # The fixed line is: `while ! docker compose exec -T web curl -sf http://...`
    # so checking for the standalone `while ! curl -sf http://localhost:8000` catches the
    # old broken form without false-matching the corrected one.
    assert "while ! curl -sf http://localhost:8000" not in text, (
        "deploy.yml must NOT use bare `curl http://localhost:8000` — port 8000 is "
        "unpublished in production; use `docker compose exec -T web curl ...` instead"
    )


def test_web_service_has_stop_grace_period() -> None:
    """prod web service must have stop_grace_period >= 30s for gunicorn graceful shutdown.

    gunicorn.conf.py sets graceful_timeout = 30 and timeout = 60. Docker's
    default stop_grace_period is 10s, which truncates the graceful shutdown.
    """
    block = _service_block(_PROD_COMPOSE, "web")
    assert "stop_grace_period:" in block, (
        "web service in docker-compose.prod.yml must define stop_grace_period"
    )
    # Extract the value and verify it is >= 30s
    match = re.search(r"stop_grace_period:\s*(\d+)(s|m)?", block)
    assert match, "stop_grace_period must have a numeric value with optional s/m unit"
    value = int(match.group(1))
    unit = match.group(2) or "s"
    if unit == "m":
        value_seconds = value * 60
    else:
        value_seconds = value
    assert value_seconds >= 30, (
        f"stop_grace_period must be >= 30s to avoid truncating gunicorn graceful_timeout (30s), "
        f"got {value}{unit}"
    )
