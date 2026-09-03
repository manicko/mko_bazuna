"""
Tests for SiteConfig singleton model, get_site_name() service, cache wiring,
and privacy page rendering.

Covers:
- Singleton get-or-create behavior (pk=1, default name "Bazuna")
- get_site_name() reads from DB and caches
- get_site_name() returns cached value on second call (no DB hit)
- get_site_name() falls back to "Bazuna" when DB raises
- post_save signal invalidates cache on save
- Privacy page renders the site name in content
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from apps.core.models import SiteConfig
from apps.core.services.site_config import get_site_name
from django.core.cache import cache
from django.test import Client
from django.urls import reverse

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear the LocMemCache before and after each test."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def site_config() -> SiteConfig:
    """Return the singleton SiteConfig instance (creating if needed)."""
    return SiteConfig.get_singleton()


# ---------------------------------------------------------------------------
# Singleton model tests
# ---------------------------------------------------------------------------


def test_get_singleton_creates_default_row() -> None:
    """SiteConfig.get_singleton() creates pk=1 with default name 'Bazuna'."""
    obj = SiteConfig.get_singleton()
    assert obj.pk == 1
    assert obj.name == "Bazuna"


def test_get_singleton_is_idempotent() -> None:
    """get_singleton() returns the same row on repeated calls (count stays 1)."""
    first = SiteConfig.get_singleton()
    second = SiteConfig.get_singleton()
    assert first.pk == second.pk == 1
    assert SiteConfig.objects.count() == 1


# ---------------------------------------------------------------------------
# get_site_name() service tests
# ---------------------------------------------------------------------------


def test_get_site_name_returns_configured_name() -> None:
    """get_site_name() returns the admin-configured name from the DB."""
    config = SiteConfig.get_singleton()
    config.name = "CustomSiteName"
    config.save()
    assert get_site_name() == "CustomSiteName"


def test_get_site_name_reads_from_cache() -> None:
    """Second call to get_site_name() hits the cache without touching the DB."""
    config = SiteConfig.get_singleton()
    config.name = "CachedSiteName"
    config.save()

    # Prime the cache
    assert get_site_name() == "CachedSiteName"

    # Second call should NOT call SiteConfig.get_singleton() (cache hit)
    with patch.object(SiteConfig, "get_singleton") as mock_get_singleton:
        result = get_site_name()
    mock_get_singleton.assert_not_called()
    assert result == "CachedSiteName"


def test_get_site_name_falls_back_on_db_error() -> None:
    """get_site_name() returns 'Bazuna' when the DB layer raises."""
    with patch.object(SiteConfig, "get_singleton", side_effect=RuntimeError("db down")):
        result = get_site_name()
    assert result == "Bazuna"


def test_save_invalidates_site_name_cache() -> None:
    """Saving a new name invalidates the cache so the next read sees it."""
    config = SiteConfig.get_singleton()
    config.name = "First Name"
    config.save()

    # Prime the cache with the first name
    assert get_site_name() == "First Name"

    # Change and save — the post_save signal should invalidate the cache
    config.name = "Second Name"
    config.save()

    # Next read should reflect the updated name, not the stale cache
    assert get_site_name() == "Second Name"


# ---------------------------------------------------------------------------
# Template render test
# ---------------------------------------------------------------------------


def test_privacy_page_renders_site_name_in_title() -> None:
    """The privacy page renders the configured site name in its content."""
    config = SiteConfig.get_singleton()
    config.name = "TestBrandXYZ"
    config.save()

    response = Client().get(reverse("core:privacy"))
    assert response.status_code == 200
    assert "TestBrandXYZ" in response.content.decode()
