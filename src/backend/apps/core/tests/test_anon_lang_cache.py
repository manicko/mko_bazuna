"""
Tests for the anonymous-language temporary cache store (Block B7).

Covers the round-trip, invalidation, and TTL of:
- ``get_cached_anon_language``
- ``set_cached_anon_language``
- ``invalidate_anon_language_cache``
"""

from __future__ import annotations

import time

import pytest
from django.core.cache import cache

from apps.core.utils.cache import (
    get_cached_anon_language,
    invalidate_anon_language_cache,
    set_cached_anon_language,
)

pytestmark = [pytest.mark.unit]


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear the LocMemCache before and after each test."""
    cache.clear()
    yield
    cache.clear()


def test_set_and_get_round_trip() -> None:
    """A language set for a telegram_id is returned by the getter."""
    set_cached_anon_language(123456, "ru")
    assert get_cached_anon_language(123456) == "ru"


def test_get_returns_none_when_not_cached() -> None:
    """The getter returns None for a telegram_id with no cached language."""
    assert get_cached_anon_language(999999) is None


def test_key_is_per_telegram_id() -> None:
    """Languages are keyed per telegram_id and do not leak across users."""
    set_cached_anon_language(111, "ru")
    assert get_cached_anon_language(222) is None


def test_invalidate_removes_entry() -> None:
    """Invalidating removes the cached language for the given telegram_id."""
    set_cached_anon_language(123456, "ru")
    invalidate_anon_language_cache(123456)
    assert get_cached_anon_language(123456) is None


def test_invalidate_does_not_affect_other_users() -> None:
    """Invalidating one user's entry leaves other users' entries intact."""
    set_cached_anon_language(111, "ru")
    set_cached_anon_language(222, "bs")
    invalidate_anon_language_cache(111)
    assert get_cached_anon_language(222) == "bs"


def test_entry_expires_after_ttl() -> None:
    """A cached language expires after the configured TTL elapses."""
    set_cached_anon_language(123456, "ru", ttl=1)
    assert get_cached_anon_language(123456) == "ru"
    time.sleep(1.1)
    assert get_cached_anon_language(123456) is None
