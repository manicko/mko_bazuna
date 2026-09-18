"""
Tests for the bot_username migration on SiteConfig (Spec 18, Task 1).

Covers:
- get_bot_username() returns the admin-configured value from the DB
- get_bot_username() returns the cached value on second call (no DB hit)
- get_bot_username() falls back to 'bazuna_bot' when DB raises
- SiteConfig save invalidates the bot_username cache
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from asgiref.sync import async_to_sync
from django.core.cache import cache

from apps.core.models import SiteConfig
from apps.core.services.site_config import get_bot_username, get_bot_username_async
from apps.core.utils.cache import (
    BOT_USERNAME_CACHE_KEY,
    get_cached_bot_username,
)

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
# get_bot_username() service tests
# ---------------------------------------------------------------------------


def test_get_bot_username_returns_configured_value() -> None:
    """get_bot_username() returns the admin-configured value from the DB."""
    config = SiteConfig.get_singleton()
    config.bot_username = "my_test_bot"
    config.save()
    assert get_bot_username() == "my_test_bot"


def test_get_bot_username_reads_from_cache() -> None:
    """Second call to get_bot_username() hits the cache without touching the DB."""
    config = SiteConfig.get_singleton()
    config.bot_username = "cached_bot"
    config.save()

    # Prime the cache
    assert get_bot_username() == "cached_bot"

    # Second call should NOT call SiteConfig.get_singleton() (cache hit)
    with patch.object(SiteConfig, "get_singleton") as mock_get_singleton:
        result = get_bot_username()
    mock_get_singleton.assert_not_called()
    assert result == "cached_bot"


def test_get_bot_username_falls_back_on_db_error() -> None:
    """get_bot_username() returns 'bazuna_bot' when the DB layer raises."""
    with patch.object(SiteConfig, "get_singleton", side_effect=RuntimeError("db down")):
        result = get_bot_username()
    assert result == "bazuna_bot"


def test_save_invalidates_bot_username_cache() -> None:
    """Saving a new bot username invalidates the cache so the next read sees it."""
    config = SiteConfig.get_singleton()
    config.bot_username = "first_bot"
    config.save()

    # Prime the cache with the first username
    assert get_bot_username() == "first_bot"
    assert get_cached_bot_username() == "first_bot"

    # Change and save — the post_save signal should invalidate the cache
    config.bot_username = "second_bot"
    config.save()

    # The cache entry must be gone (key deleted), not stale
    assert get_cached_bot_username() is None

    # Next read should reflect the updated username, not the stale cache
    assert get_bot_username() == "second_bot"


# ---------------------------------------------------------------------------
# get_bot_username_async() service tests
# ---------------------------------------------------------------------------


def test_get_bot_username_async_returns_configured_username() -> None:
    """get_bot_username_async() returns the configured username via async wrapper."""
    config = SiteConfig.get_singleton()
    config.bot_username = "async_test_bot"
    config.save()

    result = async_to_sync(get_bot_username_async)()
    assert result == "async_test_bot"


def test_get_bot_username_async_falls_back_on_db_error() -> None:
    """get_bot_username_async() returns 'bazuna_bot' when the DB layer raises."""
    with patch.object(SiteConfig, "get_singleton", side_effect=RuntimeError("db down")):
        result = async_to_sync(get_bot_username_async)()
    assert result == "bazuna_bot"


def test_get_bot_username_async_reads_from_cache() -> None:
    """get_bot_username_async() returns the cached value without hitting the DB."""
    config = SiteConfig.get_singleton()
    config.bot_username = "async_cached_bot"
    config.save()

    # Prime the cache
    assert async_to_sync(get_bot_username_async)() == "async_cached_bot"

    # Second call should hit the cache, not the DB
    with patch.object(SiteConfig, "get_singleton") as mock_get_singleton:
        result = async_to_sync(get_bot_username_async)()
    mock_get_singleton.assert_not_called()
    assert result == "async_cached_bot"


def test_cache_key_is_distinct_from_site_name() -> None:
    """The bot_username cache key is separate from the site-name cache key."""
    from apps.core.utils.cache import SITE_CONFIG_CACHE_KEY

    assert BOT_USERNAME_CACHE_KEY != SITE_CONFIG_CACHE_KEY
    assert BOT_USERNAME_CACHE_KEY == "site_config:bot_username:v1"
