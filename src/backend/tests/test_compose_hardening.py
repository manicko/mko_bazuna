"""
Container runtime hardening tests (OPS-001).

Asserts that docker-compose.yml and docker-compose.prod.yml contain the
CIS-Docker-Benchmark runtime hardening directives. Follows the same pattern
as test_docs_ci_parity.py: string-level YAML checks via Path.read_text(),
no PyYAML dependency.
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

_COMPOSE = _ROOT / "docker-compose.yml"
_PROD_COMPOSE = _ROOT / "docker-compose.prod.yml"

# Hardening keys required on every long-lived / hardened service.
_HARDENING_KEYS = [
    "read_only: true",
    "tmpfs:",
    "no-new-privileges:true",
    "mem_limit:",
    "cpus:",
]


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


# --- web ------------------------------------------------------------------


def test_web_service_has_hardening() -> None:
    """web: cap_drop, read_only, tmpfs, security_opt, limits, healthcheck."""
    block = _service_block(_COMPOSE, "web")
    assert 'cap_drop: ["ALL"]' in block, 'web must have cap_drop: ["ALL"]'
    for key in _HARDENING_KEYS:
        assert key in block, f"web must have {key}"
    assert "healthcheck:" in block, "web must have a healthcheck"


def test_web_healthcheck_in_compose() -> None:
    """web must have an explicit healthcheck key in compose (not just Dockerfile)."""
    block = _service_block(_COMPOSE, "web")
    assert "healthcheck:" in block, "web must have healthcheck in compose"
    assert "/health/" in block, "healthcheck must probe the /health/ endpoint"


# --- bot ------------------------------------------------------------------


def test_bot_service_has_hardening() -> None:
    """bot: cap_drop, read_only, tmpfs, security_opt, limits (keeps its own healthcheck)."""
    block = _service_block(_COMPOSE, "bot")
    assert 'cap_drop: ["ALL"]' in block, 'bot must have cap_drop: ["ALL"]'
    for key in _HARDENING_KEYS:
        assert key in block, f"bot must have {key}"


# --- nginx (exception: needs cap_add for 80/443) --------------------------


def test_nginx_has_cap_add() -> None:
    """nginx must have cap_add with NET_BIND_SERVICE (exception for ports 80/443)."""
    block = _service_block(_COMPOSE, "nginx")
    assert "cap_add:" in block, "nginx must have cap_add"
    assert 'cap_drop: ["ALL"]' in block, 'nginx must also have cap_drop: ["ALL"]'
    for cap in ("NET_BIND_SERVICE", "CHOWN", "SETGID", "SETUID", "DAC_OVERRIDE"):
        assert cap in block, f"nginx must have {cap} in cap_add"


# --- db (exception: NO cap_drop) ------------------------------------------


def test_db_has_no_cap_drop_all() -> None:
    """db must NOT have cap_drop — postgres entrypoint needs chown/chmod capabilities.

    Explicit verification of the nginx/db exception documented in OPS-001.
    """
    block = _service_block(_COMPOSE, "db")
    assert "cap_drop" not in block, (
        "db must NOT have cap_drop (postgres needs capabilities)"
    )
    # db must still have read_only + tmpfs + security_opt + limits
    for key in _HARDENING_KEYS:
        assert key in block, f"db must have {key}"


# --- redis ----------------------------------------------------------------


def test_redis_has_cap_drop_all() -> None:
    """redis must have cap_drop: [\"ALL\"]."""
    block = _service_block(_COMPOSE, "redis")
    assert 'cap_drop: ["ALL"]' in block, 'redis must have cap_drop: ["ALL"]'


# --- prod-only services ---------------------------------------------------


def test_scheduler_hardened_in_prod() -> None:
    """scheduler (prod-only) must have full hardening including cap_drop."""
    block = _service_block(_PROD_COMPOSE, "scheduler")
    assert 'cap_drop: ["ALL"]' in block, 'scheduler must have cap_drop: ["ALL"]'
    for key in _HARDENING_KEYS:
        assert key in block, f"scheduler must have {key}"


def test_backup_hardened_in_prod() -> None:
    """backup (prod-only) must have read_only + tmpfs + security_opt + limits."""
    block = _service_block(_PROD_COMPOSE, "backup")
    for key in _HARDENING_KEYS:
        assert key in block, f"backup must have {key}"
    # backup intentionally has NO cap_drop (runs pg_dump as postgres user)
    assert "cap_drop" not in block


def test_pgbouncer_hardened_in_prod() -> None:
    """pgbouncer (prod-only) must have read_only + tmpfs + security_opt + limits."""
    block = _service_block(_PROD_COMPOSE, "pgbouncer")
    for key in _HARDENING_KEYS:
        assert key in block, f"pgbouncer must have {key}"


# --- resource limits use env substitution ---------------------------------


def test_resource_limits_use_env_substitution() -> None:
    """mem_limit and cpus must use ${VAR:-default} env substitution pattern."""
    text = _COMPOSE.read_text() + _PROD_COMPOSE.read_text()
    assert re.search(r"mem_limit: \$\{[A-Z_]+:-", text), (
        "mem_limit must use ${VAR:-default} env substitution"
    )
    assert re.search(r"cpus: \$\{[A-Z_]+:-", text), (
        "cpus must use ${VAR:-default} env substitution"
    )
