"""
Container runtime hardening tests (OPS-001).

Asserts that docker-compose.yml and docker-compose.prod.yml contain the
CIS-Docker-Benchmark runtime hardening directives. Follows the same pattern
as test_docs_ci_parity.py: string-level YAML checks via Path.read_text(),
no PyYAML dependency.
"""

from __future__ import annotations

import os
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
_DEV_OVERRIDE_COMPOSE = _ROOT / "docker-compose.dev.override.yml"

# One-shot bootstrap services. In dev they run against prod settings with
# dev placeholder secrets (see DJANGO_ONESHOT handling in prod.py).
_ONE_SHOT_SERVICES = ["migrate", "load_cities", "load_catalog", "create_admin"]

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
    assert "/health/live/" in block, "healthcheck must probe the /health/live/ endpoint"


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


# --- scheduler deploy parity (OPS-009) ---------------------------------------


def test_scheduler_has_scheduler_profile() -> None:
    """scheduler must be gated by profiles: ["scheduler"] in prod compose."""
    block = _service_block(_PROD_COMPOSE, "scheduler")
    assert "profiles:" in block, "scheduler must define profiles:"
    assert "- scheduler" in block, "scheduler must be listed under profiles"


def test_scheduler_uses_image_not_build() -> None:
    """scheduler must use a pre-built image, never a local build directive."""
    block = _service_block(_PROD_COMPOSE, "scheduler")
    assert "image:" in block, "scheduler must use image: in production"
    assert "build:" not in block, "scheduler must NOT use build: in production"


def test_scheduler_entrypoint_is_executable() -> None:
    """docker/entrypoint-scheduler.sh must exist and be marked executable."""
    path = _ROOT / "docker" / "entrypoint-scheduler.sh"
    assert path.exists(), f"entrypoint not found at {path}"
    assert os.access(path, os.X_OK), f"{path} must be executable (chmod +x)"


def test_backup_hardened_in_prod() -> None:
    """backup (prod-only) must have full hardening including cap_drop."""
    block = _service_block(_PROD_COMPOSE, "backup")
    assert 'cap_drop: ["ALL"]' in block, 'backup must have cap_drop: ["ALL"]'
    for key in _HARDENING_KEYS:
        assert key in block, f"backup must have {key}"


def test_pgbouncer_hardened_in_prod() -> None:
    """pgbouncer (prod-only) must have full hardening including cap_drop."""
    block = _service_block(_PROD_COMPOSE, "pgbouncer")
    assert 'cap_drop: ["ALL"]' in block, 'pgbouncer must have cap_drop: ["ALL"]'
    for key in _HARDENING_KEYS:
        assert key in block, f"pgbouncer must have {key}"


# --- one-shot services (hardening gap in OPS-001) -------------------------


def test_migrate_has_hardening() -> None:
    """migrate (one-shot) must have full CIS hardening with cap_drop."""
    block = _service_block(_COMPOSE, "migrate")
    assert 'cap_drop: ["ALL"]' in block, 'migrate must have cap_drop: ["ALL"]'
    for key in _HARDENING_KEYS:
        assert key in block, f"migrate must have {key}"


def test_load_cities_has_hardening() -> None:
    """load_cities (one-shot) must have full CIS hardening with cap_drop."""
    block = _service_block(_COMPOSE, "load_cities")
    assert 'cap_drop: ["ALL"]' in block, 'load_cities must have cap_drop: ["ALL"]'
    for key in _HARDENING_KEYS:
        assert key in block, f"load_cities must have {key}"


def test_load_catalog_has_hardening() -> None:
    """load_catalog (one-shot) must have full CIS hardening with cap_drop."""
    block = _service_block(_COMPOSE, "load_catalog")
    assert 'cap_drop: ["ALL"]' in block, 'load_catalog must have cap_drop: ["ALL"]'
    for key in _HARDENING_KEYS:
        assert key in block, f"load_catalog must have {key}"


def test_create_admin_has_hardening() -> None:
    """create_admin (one-shot) must have full CIS hardening with cap_drop."""
    block = _service_block(_COMPOSE, "create_admin")
    assert 'cap_drop: ["ALL"]' in block, 'create_admin must have cap_drop: ["ALL"]'
    for key in _HARDENING_KEYS:
        assert key in block, f"create_admin must have {key}"


def test_seed_has_hardening() -> None:
    """seed (one-shot) must have full CIS hardening with cap_drop and higher limits."""
    block = _service_block(_COMPOSE, "seed")
    assert 'cap_drop: ["ALL"]' in block, 'seed must have cap_drop: ["ALL"]'
    for key in _HARDENING_KEYS:
        assert key in block, f"seed must have {key}"
    # seed generates demo data — should use higher defaults than other one-shots
    assert "SEED_MEM_LIMIT:-512m" in block, "seed must default to 512m mem_limit"
    assert "SEED_CPUS:-1.0" in block, "seed must default to 1.0 cpus"


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


# --- DJANGO_BUILD / DJANGO_ONESHOT split (CFG-001) -------------------------


def test_compose_oneshot_flags() -> None:
    """One-shot services carry DJANGO_ONESHOT=1 in dev but never in prod.

    One-shot bootstrap services (migrate, load_cities, load_catalog,
    create_admin) use prod settings. In development they need DJANGO_ONESHOT=1
    so the prod.py secret-validation guards bypass dev placeholder secrets. In
    production neither DJANGO_BUILD nor DJANGO_ONESHOT may appear — full secret
    validation runs against the real .env.prod values. seed is exempt: it uses
    config.settings.dev in the dev override.
    """
    # Prod: no one-shot service block may carry either bypass flag.
    for service in _ONE_SHOT_SERVICES:
        block = _service_block(_PROD_COMPOSE, service)
        assert "DJANGO_BUILD" not in block, (
            f"{service} in prod compose must not set DJANGO_BUILD"
        )
        assert "DJANGO_ONESHOT" not in block, (
            f"{service} in prod compose must not set DJANGO_ONESHOT"
        )

    # Dev: every one-shot service must carry DJANGO_ONESHOT=1.
    for service in _ONE_SHOT_SERVICES:
        block = _service_block(_DEV_OVERRIDE_COMPOSE, service)
        assert "DJANGO_ONESHOT=1" in block, (
            f"{service} in dev override must set DJANGO_ONESHOT=1"
        )

    # Dev seed is exempt (uses config.settings.dev) — must NOT set DJANGO_ONESHOT.
    seed_block = _service_block(_DEV_OVERRIDE_COMPOSE, "seed")
    assert "DJANGO_ONESHOT" not in seed_block, (
        "seed in dev override must not set DJANGO_ONESHOT (uses config.settings.dev)"
    )
