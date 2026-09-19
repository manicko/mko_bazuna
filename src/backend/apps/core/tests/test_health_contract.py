"""
Tests for the health check contract (Block 5: OPS-005, OPS-011, OPS-013).

Verifies the liveness/readiness split, versioning, and bot staleness configuration:
- /health/live/ returns 200 with {"status": "alive"} (no DB/cache dependency)
- /health/ready/ returns 200 with {"version": 1, "status": "ready", "checks": {...}}
  when DB + Redis are healthy
- /health/ready/ returns 503 when Redis cache is unavailable (mocked)
- /health/ready/ returns 503 when the database is unavailable (mocked)
- /health/ (alias) returns the same response as /health/ready/
- /health/v1/ returns a versioned response
- BOT_HEALTH_STALE_SECONDS=120 is set in docker-compose.yml bot environment
  and read by docker/healthcheck-bot.sh (env var is the single source of truth;
  the Django settings mirror was removed as dead config)
- BOT_HEALTH_STALE_SECONDS=120 is set in docker-compose.yml bot environment
- Dockerfile HEALTHCHECK curls /health/ready/
- docker-compose.yml web healthcheck curls /health/ready/
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse

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
    """Readiness probe returns 200 when DB + Redis cache are healthy."""
    response = client.get(ready_url)
    assert response.status_code == 200
    data = json.loads(response.content)
    assert data["version"] == 1
    assert data["status"] == "ready"
    assert data["checks"] == {"database": "ok", "cache": "ok"}


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


def test_dockerfile_healthcheck_points_to_ready() -> None:
    """Dockerfile HEALTHCHECK curls /health/ready/."""
    content = (_PROJECT_ROOT / "docker" / "Dockerfile").read_text(encoding="utf-8")
    assert "HEALTHCHECK" in content
    assert "/health/ready/" in content


def test_web_compose_healthcheck_points_to_ready() -> None:
    """docker-compose.yml web healthcheck curls /health/ready/."""
    content = (_PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "/health/ready/" in content
