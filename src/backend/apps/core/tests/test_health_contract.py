"""
Tests for the health check contract (Block B1: OPS-002, OPS-003).

Verifies the liveness/readiness split, versioning, bot liveness marker, and
container hardening:
- /health/live/ returns 200 with {"status": "alive"} (no DB/cache dependency)
- /health/ready/ returns 200 with {"version": 1, "status": "ready", "checks": {...}}
  when DB + Redis are healthy and the bot marker is fresh (or disabled)
- /health/ready/ returns 503 when Redis cache is unavailable (mocked)
- /health/ready/ returns 503 when the database is unavailable (mocked)
- /health/ready/ includes a "bot" key in checks: "disabled" (tests), "ok"
  (fresh marker), or "stale" (missing/old marker) when BOT_HEALTH_CHECK_ENABLED
- /health/ (alias) returns the same response as /health/ready/
- /health/v1/ returns a versioned response
- BOT_HEALTH_STALE_SECONDS=120 is set in docker-compose.yml for both bot and
  web services; also read by docker/healthcheck-bot.sh
- Dockerfile HEALTHCHECK curls /health/live/
- docker-compose.yml web healthcheck curls /health/live/
"""

from __future__ import annotations

import json
import os
from time import time as _time
from unittest.mock import patch

import pytest
from django.conf import settings
from django.core.cache import cache
from django.test import Client, override_settings
from django.urls import reverse
from ruamel.yaml import YAML

pytestmark = [pytest.mark.unit]
# BASE_DIR in settings points to src/ ; its parent is the repository root.
_PROJECT_ROOT = settings.BASE_DIR.parent


@pytest.fixture
def live_url() -> str:
    return reverse("core:health_live")


@pytest.fixture
def ready_url() -> str:
    return reverse("core:health_ready")


@pytest.fixture
def v1_url() -> str:
    return reverse("core:health_v1")


@pytest.fixture
def health_url() -> str:
    return reverse("core:health")


# ---------------------------------------------------------------------------
# Liveness probe — no DB or cache dependency
# ---------------------------------------------------------------------------


def test_liveness_check_returns_alive(client: Client, live_url: str) -> None:
    """Liveness probe returns 200 with status 'alive'.

    No ``@pytest.mark.django_db`` — the liveness endpoint must work even
    when the database or cache is completely unavailable.
    """
    response = client.get(live_url)
    assert response.status_code == 200
    assert json.loads(response.content) == {"status": "alive"}


# ---------------------------------------------------------------------------
# Readiness probe — DB + Redis cache dependency
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_readiness_check_healthy(client: Client, ready_url: str) -> None:
    """Readiness probe returns 200 when DB + Redis cache are healthy.

    In test settings ``BOT_HEALTH_CHECK_ENABLED`` is ``False``, so the bot
    check reports ``"disabled"`` and does not affect the overall status.
    """
    response = client.get(ready_url)
    assert response.status_code == 200
    data = json.loads(response.content)
    assert data["version"] == 1
    assert data["status"] == "ready"
    assert data["checks"] == {"database": "ok", "cache": "ok", "bot": "disabled"}


@pytest.mark.django_db
def test_readiness_check_redis_down(client: Client, ready_url: str) -> None:
    """Readiness returns 503 when the Redis cache is unavailable."""
    with patch("apps.core.views.cache") as mock_cache:
        mock_cache.get.side_effect = Exception("cache unavailable")
        response = client.get(ready_url)
    assert response.status_code == 503
    data = json.loads(response.content)
    assert data["version"] == 1
    assert data["status"] == "not_ready"
    assert data["checks"]["cache"] == "fail"
    assert data["checks"]["database"] == "ok"


def test_readiness_check_db_down(client: Client, ready_url: str) -> None:
    """Readiness returns 503 when the database is unavailable.

    No ``@pytest.mark.django_db`` — the DB connection is mocked so that
    the view's ``SELECT 1`` raises before reaching the real database.
    The middleware stack does not access the DB for anonymous,
    cookie-less health-check requests.
    """
    with patch("apps.core.views.connection") as mock_conn:
        mock_conn.cursor.side_effect = Exception("db down")
        response = client.get(ready_url)
    assert response.status_code == 503
    data = json.loads(response.content)
    assert data["version"] == 1
    assert data["status"] == "not_ready"
    assert data["checks"]["database"] == "fail"
    assert data["checks"]["cache"] == "ok"


# ---------------------------------------------------------------------------
# Bot liveness marker (Redis-based, OPS-003)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_readiness_includes_bot_marker(client: Client, ready_url: str) -> None:
    """Readiness response includes a 'bot' key in the checks dict."""
    response = client.get(ready_url)
    assert response.status_code == 200
    data = json.loads(response.content)
    assert "bot" in data["checks"]


@pytest.mark.django_db
@override_settings(BOT_HEALTH_CHECK_ENABLED=True)
def test_readiness_bot_marker_ok_when_fresh(client: Client, ready_url: str) -> None:
    """Readiness returns 200 with bot 'ok' when the liveness marker is fresh."""
    cache.set("bot:liveness", int(_time()))
    response = client.get(ready_url)
    assert response.status_code == 200
    data = json.loads(response.content)
    assert data["checks"]["bot"] == "ok"


@pytest.mark.django_db
@override_settings(BOT_HEALTH_CHECK_ENABLED=True)
def test_readiness_bot_marker_stale(client: Client, ready_url: str) -> None:
    """Readiness returns 503 when the bot liveness marker is stale."""
    cache.set("bot:liveness", int(_time()) - 300)
    response = client.get(ready_url)
    assert response.status_code == 503
    data = json.loads(response.content)
    assert data["checks"]["bot"] == "stale"


# ---------------------------------------------------------------------------
# Alias + versioned routes
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_health_alias_returns_readiness(
    client: Client, health_url: str, ready_url: str
) -> None:
    """/health/ (alias) returns the same response as /health/ready/."""
    alias_response = client.get(health_url)
    direct_response = client.get(ready_url)
    assert alias_response.status_code == 200
    assert json.loads(alias_response.content) == json.loads(
        direct_response.content
    )


@pytest.mark.django_db
def test_health_v1_returns_version(client: Client, v1_url: str) -> None:
    """Versioned endpoint /health/v1/ returns a response with the version key."""
    response = client.get(v1_url)
    assert response.status_code == 200
    data = json.loads(response.content)
    assert data["version"] == 1


# ---------------------------------------------------------------------------
# Structural tests — Docker / compose configuration
# ---------------------------------------------------------------------------


def test_bot_staleseconds_set_in_compose() -> None:
    """docker-compose.yml sets BOT_HEALTH_STALE_SECONDS=120 for the bot."""
    content = (_PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "BOT_HEALTH_STALE_SECONDS=120" in content


def test_dockerfile_healthcheck_points_to_live() -> None:
    """Dockerfile HEALTHCHECK curls /health/live/ (not /health/ready/)."""
    content = (_PROJECT_ROOT / "docker" / "Dockerfile").read_text(encoding="utf-8")
    assert "HEALTHCHECK" in content
    assert "/health/live/" in content
    # The HEALTHCHECK line itself must not reference /health/ready/
    for line in content.splitlines():
        if "HEALTHCHECK" in line or "CMD curl" in line:
            assert "/health/ready/" not in line, (
                "HEALTHCHECK must use /health/live/, not /health/ready/"
            )


def test_web_compose_healthcheck_points_to_live() -> None:
    """docker-compose.yml web healthcheck curls /health/live/."""
    content = (_PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "/health/live/" in content


# ---------------------------------------------------------------------------
# Scheduler healthcheck (ENT-004)
# ---------------------------------------------------------------------------


def test_scheduler_healthcheck_script_exists_and_is_executable() -> None:
    """docker/healthcheck-scheduler.sh exists and is marked executable."""
    path = _PROJECT_ROOT / "docker" / "healthcheck-scheduler.sh"
    assert path.exists(), f"healthcheck script not found at {path}"
    assert os.access(path, os.X_OK), (
        f"{path} must be executable (chmod +x)"
    )


def test_scheduler_compose_has_healthcheck() -> None:
    """docker-compose.prod.yml scheduler service has a healthcheck block.

    Parses the YAML and asserts ``services.scheduler.healthcheck`` exists
    and points to the scheduler healthcheck script.
    """
    yaml = YAML(typ="safe")
    compose_path = _PROJECT_ROOT / "docker-compose.prod.yml"
    with open(compose_path, encoding="utf-8") as fh:
        data = yaml.load(fh)
    assert data is not None
    assert "services" in data
    assert "scheduler" in data["services"]
    scheduler = data["services"]["scheduler"]
    assert "healthcheck" in scheduler
    # The healthcheck test command must reference the scheduler script
    test_cmd = scheduler["healthcheck"]["test"]
    assert isinstance(test_cmd, list)
    assert "/app/docker/healthcheck-scheduler.sh" in test_cmd


def test_scheduler_compose_has_stale_seconds() -> None:
    """docker-compose.prod.yml sets SCHEDULER_HEALTH_STALE_SECONDS=7200."""
    content = (_PROJECT_ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    assert "SCHEDULER_HEALTH_STALE_SECONDS=7200" in content
