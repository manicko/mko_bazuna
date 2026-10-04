"""
Regression tests for the site-config cache-failure contract (09-API-001).

The defect this pins: ``apps.core.services.site_config.get_site_name`` and
``get_bot_username`` executed their cache read *before* the ``try`` block, so a
Redis cache outage raised out of the context processor and turned every
rendered page into a 500 — while ``/health/`` correctly reported
``cache: fail``. The fix routes the read through the shared
``cache_get_or_none`` helper (fail-open) and moves the cache write into its own
guard so a write-only fault still returns the database's answer.

These tests assert on the **HTTP response**, never on the helper's return
value, and keep two controls:

- ``/health/`` must still report ``cache: fail`` with a 503 — proving the fix
  degrades requests without silencing the outage signal.
- The cache getters are patched (not the whole cache object) so the rate-limit
  guards, which are a separate finding (BLOCK 2), do not manufacture the
  failure.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock, patch

import pytest
import redis
from django.test import Client
from django.urls import reverse
from django_redis.exceptions import ConnectionInterrupted

from apps.core.enums import AdStatus
from apps.core.models import SiteConfig
from apps.core.services.site_config import get_bot_username, get_site_name
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _cache_read_fault() -> Mock:
    """Return a mock whose call raises ``ConnectionInterrupted`` (Redis down)."""
    return Mock(side_effect=ConnectionInterrupted("Simulated Redis outage"))


def _patch_cache_reads() -> Any:
    """Patch both site-config cache getters and the readiness probe's cache.

    ``stack`` the getters (used on every rendered page) plus
    ``apps.core.views.cache`` (used by ``/health/``) so one failing backend is
    observed simultaneously by the request path and by the probe.
    """
    return (
        patch(
            "apps.core.utils.cache.get_cached_site_config",
            _cache_read_fault(),
        ),
        patch(
            "apps.core.utils.cache.get_cached_bot_username",
            _cache_read_fault(),
        ),
    )


# ---------------------------------------------------------------------------
# Test 1 — the outage: rendered pages keep their statuses (not 500)
# ---------------------------------------------------------------------------


def test_home_page_survives_cache_read_fault(seller, category, city) -> None:
    """GET / returns 200 when every site-config cache read raises."""
    create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
    config = SiteConfig.get_singleton()
    config.name = "FaultSite"
    config.bot_username = "fault_bot"
    config.save()

    with _patch_cache_reads()[0], _patch_cache_reads()[1]:
        response = Client().get("/")

    assert response.status_code == 200


def test_ad_detail_survives_cache_read_fault(seller, category, city) -> None:
    """An ad detail page returns 200 when every site-config cache read raises."""
    ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)

    with _patch_cache_reads()[0], _patch_cache_reads()[1]:
        response = Client().get(reverse("ads:detail", args=[ad.id]))

    assert response.status_code == 200


def test_login_issue_survives_cache_read_fault() -> None:
    """POST /login/issue/ returns its normal 200 when cache reads raise."""
    config = SiteConfig.get_singleton()
    config.bot_username = "fault_bot"
    config.save()

    with _patch_cache_reads()[0], _patch_cache_reads()[1]:
        response = Client().post("/login/issue/")

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Test 2 — the probe: /health/ still reports the outage
# ---------------------------------------------------------------------------


def test_health_probe_still_reports_cache_failure() -> None:
    """GET /health/ still returns 503 with checks.cache == 'fail'.

    This is the control proving the request-path fix did not simply swallow the
    outage: the probe reads ``apps.core.views.cache`` directly and must keep
    reporting the fault.
    """
    with patch("apps.core.views.cache") as mock_cache:
        mock_cache.get.side_effect = ConnectionInterrupted("Simulated Redis outage")
        response = Client().get(reverse("core:health"))

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "not_ready"
    assert payload["checks"]["cache"] == "fail"


# ---------------------------------------------------------------------------
# Test 3 — the fallback strings, byte-identical under cache and DB faults
# ---------------------------------------------------------------------------


def test_site_name_falls_back_under_cache_fault() -> None:
    """get_site_name() returns 'Bazuna' when the cache read raises."""
    with _patch_cache_reads()[0], _patch_cache_reads()[1]:
        assert get_site_name() == "Bazuna"


def test_bot_username_falls_back_under_cache_fault() -> None:
    """get_bot_username() returns 'bazuna_bot' when the cache read raises."""
    with _patch_cache_reads()[0], _patch_cache_reads()[1]:
        assert get_bot_username() == "bazuna_bot"


def test_site_name_falls_back_under_database_fault() -> None:
    """get_site_name() returns 'Bazuna' when the database read raises."""
    with patch.object(
        SiteConfig, "get_singleton", side_effect=RuntimeError("db down")
    ):
        assert get_site_name() == "Bazuna"


def test_bot_username_falls_back_under_database_fault() -> None:
    """get_bot_username() returns 'bazuna_bot' when the database read raises."""
    with patch.object(
        SiteConfig, "get_singleton", side_effect=RuntimeError("db down")
    ):
        assert get_bot_username() == "bazuna_bot"


def test_cache_getters_swallow_redis_error() -> None:
    """A bare redis.RedisError (not ConnectionInterrupted) also fails open."""
    with patch(
        "apps.core.utils.cache.get_cached_site_config",
        Mock(side_effect=redis.RedisError("redis down")),
    ):
        assert get_site_name() == "Bazuna"


# ---------------------------------------------------------------------------
# Test 5 — the cache-write half (Q12 option (b))
# ---------------------------------------------------------------------------


def test_write_fault_returns_database_value() -> None:
    """A read-OK / write-failing cache returns the database's name and username.

    Under option (b) the write lives in its own guard: a successful database
    read is returned verbatim even when ``set_cached_*`` raises, so the cache
    fault cannot mask a correct answer.
    """
    config = SiteConfig.get_singleton()
    config.name = "WriteFaultSite"
    config.bot_username = "write_fault_bot"
    config.save()

    cache = "apps.core.utils.cache"
    with (
        patch(f"{cache}.set_cached_site_config", _cache_read_fault()),
        patch(f"{cache}.set_cached_bot_username", _cache_read_fault()),
        patch(f"{cache}.get_cached_site_config", return_value=None),
        patch(f"{cache}.get_cached_bot_username", return_value=None),
    ):
        assert get_site_name() == "WriteFaultSite"
        assert get_bot_username() == "write_fault_bot"


def test_write_fault_does_not_log_site_config_unavailable(caplog) -> None:
    """A write-only fault logs at DEBUG, never the 'SiteConfig unavailable' warning.

    Option (b) exists precisely to make this diagnostic true: the warning is
    reserved for the database-unavailable half.
    """
    config = SiteConfig.get_singleton()
    config.bot_username = "write_fault_bot"
    config.save()

    cache = "apps.core.utils.cache"
    with (
        caplog.at_level("DEBUG"),
        patch(f"{cache}.get_cached_bot_username", return_value=None),
        patch(f"{cache}.set_cached_bot_username", _cache_read_fault()),
    ):
        assert get_bot_username() == "write_fault_bot"

    assert "SiteConfig unavailable" not in caplog.text
