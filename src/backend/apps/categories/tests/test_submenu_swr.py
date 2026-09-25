"""
Tests for the category submenu fragment cache SWR (stale-while-revalidate)
behavior, added after PERF-007 wrapped category_submenu() in
get_with_stale_revalidate.

Covers:
  - SWR state machine on submenu cache reads (fresh hit, stale serve,
    cold miss winner/loser, expiry, lock-held default fallback)
  - Single-flight: producer invoked exactly once under concurrent access
  - Version-bump invalidation (old key unreachable after bump_tree_version)

LocMemCache is used in tests (settings/test.py). Under LocMemCache:
  - cache.add single-flight is intra-process only
  - cache.incr is thread-safe (Django acquires a per-key lock)
  - cache.delete_pattern does not exist (no-op)
Tests assert version-bump and SWR behavior, never delete_pattern.
"""

from __future__ import annotations

import threading
import time

import pytest
from django.core.cache import cache
from django.test import Client

from apps.categories.cache import (
    SUBMENU_CACHE_LOCK_TTL,
    SUBMENU_CACHE_STALE_TTL,
    SUBMENU_CACHE_TTL,
    bump_tree_version,
    get_tree_version,
)
from apps.core.utils.swr_cache import (
    _CACHE_LOCK_SUFFIX,
    get_with_stale_revalidate,
)


def _make_entry(value, age_seconds: float = 0.0) -> dict:
    """Build a _CacheEntry-compatible dict stored by get_with_stale_revalidate."""
    return {"value": value, "stored_at": time.time() - age_seconds}


SUBMENU_KEY = "test:submenu_swr"


class TestSubmenuSwr:
    """SWR state machine for the submenu fragment."""

    pytestmark = pytest.mark.unit

    def test_submenu_fresh_hit_returns_cached_without_producer(self):
        cache.set(
            SUBMENU_KEY,
            _make_entry("fragment_html", age_seconds=1.0),
            timeout=SUBMENU_CACHE_TTL + SUBMENU_CACHE_STALE_TTL + 60,
        )

        call_count = 0

        def producer():
            nonlocal call_count
            call_count += 1
            return "recomputed_html"

        val = get_with_stale_revalidate(
            SUBMENU_KEY,
            producer,
            ttl=SUBMENU_CACHE_TTL,
            stale_ttl=SUBMENU_CACHE_STALE_TTL,
            lock_ttl=SUBMENU_CACHE_LOCK_TTL,
            default="",
        )

        assert val == "fragment_html"
        assert call_count == 0

    def test_submenu_stale_hit_serves_stale_value(self):
        cache.set(
            SUBMENU_KEY,
            _make_entry("stale_html", age_seconds=SUBMENU_CACHE_TTL + 30),
            timeout=SUBMENU_CACHE_TTL + SUBMENU_CACHE_STALE_TTL + 60,
        )

        call_count = 0

        def producer():
            nonlocal call_count
            call_count += 1
            return "fresh_html"

        val = get_with_stale_revalidate(
            SUBMENU_KEY,
            producer,
            ttl=SUBMENU_CACHE_TTL,
            stale_ttl=SUBMENU_CACHE_STALE_TTL,
            lock_ttl=SUBMENU_CACHE_LOCK_TTL,
            default="",
        )

        assert val == "stale_html"
        assert call_count == 1

    def test_submenu_cold_miss_recomputes_and_caches(self):
        assert cache.get(SUBMENU_KEY) is None

        def producer():
            return "computed_fragment"

        val = get_with_stale_revalidate(
            SUBMENU_KEY,
            producer,
            ttl=SUBMENU_CACHE_TTL,
            stale_ttl=SUBMENU_CACHE_STALE_TTL,
            lock_ttl=SUBMENU_CACHE_LOCK_TTL,
            default="",
        )

        assert val == "computed_fragment"

        cached = cache.get(SUBMENU_KEY)
        assert cached is not None
        assert cached["value"] == "computed_fragment"

    def test_submenu_cold_miss_lock_held_returns_default(self):
        lock_key = f"{SUBMENU_KEY}{_CACHE_LOCK_SUFFIX}"
        cache.add(lock_key, "1", SUBMENU_CACHE_LOCK_TTL)

        call_count = 0

        def producer():
            nonlocal call_count
            call_count += 1
            return "should_not_run"

        val = get_with_stale_revalidate(
            SUBMENU_KEY,
            producer,
            ttl=SUBMENU_CACHE_TTL,
            stale_ttl=SUBMENU_CACHE_STALE_TTL,
            lock_ttl=SUBMENU_CACHE_LOCK_TTL,
            default="",
        )

        assert val == ""
        assert call_count == 0

    def test_submenu_expired_entry_triggers_recompute(self):
        cache.set(
            SUBMENU_KEY,
            _make_entry(
                "expired_html",
                age_seconds=SUBMENU_CACHE_TTL + SUBMENU_CACHE_STALE_TTL + 10,
            ),
            timeout=SUBMENU_CACHE_TTL + SUBMENU_CACHE_STALE_TTL + 120,
        )

        def producer():
            return "new_html"

        val = get_with_stale_revalidate(
            SUBMENU_KEY,
            producer,
            ttl=SUBMENU_CACHE_TTL,
            stale_ttl=SUBMENU_CACHE_STALE_TTL,
            lock_ttl=SUBMENU_CACHE_LOCK_TTL,
            default="",
        )

        assert val == "new_html"

    def test_submenu_version_bump_makes_old_cache_key_unreachable(self):
        key_before = f"category:submenu:{get_tree_version()}:transport:ru"
        cache.set(
            key_before,
            _make_entry("old_html", age_seconds=1.0),
            timeout=SUBMENU_CACHE_TTL + SUBMENU_CACHE_STALE_TTL + 60,
        )
        assert cache.get(key_before) is not None

        version_before = get_tree_version()
        bump_tree_version()
        version_after = get_tree_version()
        key_after = f"category:submenu:{version_after}:transport:ru"

        assert version_after == version_before + 1
        assert key_after != key_before
        assert cache.get(key_before) is not None
        assert cache.get(key_after) is None

    def test_submenu_single_flight_producer_called_once_under_concurrent_access(self):
        key = "test:submenu_swr:single_flight"
        lock_key = f"{key}{_CACHE_LOCK_SUFFIX}"
        cache.delete(key)
        cache.delete(lock_key)

        call_count = 0
        counter_lock = threading.Lock()
        barrier = threading.Barrier(5)
        results: list = []
        result_lock = threading.Lock()

        def producer():
            nonlocal call_count
            with counter_lock:
                call_count += 1
            time.sleep(0.2)
            return "computed_html"

        def worker():
            barrier.wait()
            val = get_with_stale_revalidate(
                key,
                producer,
                ttl=SUBMENU_CACHE_TTL,
                stale_ttl=SUBMENU_CACHE_STALE_TTL,
                lock_ttl=SUBMENU_CACHE_LOCK_TTL,
                default="",
            )
            with result_lock:
                results.append(val)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert call_count == 1
        assert "computed_html" in results
        assert results.count("") >= 1


@pytest.fixture
def tree():
    """Create a root category with active and inactive children."""
    from apps.categories.models import Category

    root = Category.objects.create(name="Транспорт", slug="transport")
    Category.objects.create(name="Велосипеды", slug="bicycles", parent=root)
    Category.objects.create(name="Автомобили", slug="cars", parent=root)
    Category.objects.create(name="Устаревшее", slug="old", parent=root, is_active=False)
    return root


@pytest.mark.django_db
@pytest.mark.integration
class TestSubmenuCacheIntegration:
    """Priming, version-bump invalidation, and rendering via the real endpoint."""

    def test_submenu_endpoint_primes_cache(self, tree):
        version = get_tree_version()
        cache_key = f"category:submenu:{version}:transport:ru"
        cache.delete(cache_key)
        cache.delete(f"{cache_key}:lock")

        client = Client()
        # Language is driven via ?lang=ru so the cache key locale segment matches
        # the assertion above (test settings default LANGUAGE_CODE to "en").
        response_1 = client.get("/categories/transport/submenu/?lang=ru")
        assert response_1.status_code == 200
        content_1 = response_1.content.decode("utf-8")
        assert cache.get(cache_key) is not None

        response_2 = client.get("/categories/transport/submenu/?lang=ru")
        assert response_2.status_code == 200
        content_2 = response_2.content.decode("utf-8")
        assert content_2 == content_1

    def test_submenu_cache_invalidates_on_tree_version_bump(self, tree):
        version_before = get_tree_version()
        key_before = f"category:submenu:{version_before}:transport:ru"

        client = Client()
        # ?lang=ru so the cached key uses locale "ru" (matches the assertion).
        client.get("/categories/transport/submenu/?lang=ru")
        assert cache.get(key_before) is not None

        tree.name = "Транспорт Updated"
        tree.save(update_fields=["name"])

        version_after = get_tree_version()
        key_after = f"category:submenu:{version_after}:transport:ru"

        assert version_after > version_before
        assert key_after != key_before
        assert cache.get(key_before) is not None
        assert cache.get(key_after) is None

        response = client.get("/categories/transport/submenu/?lang=ru")
        assert response.status_code == 200
        assert cache.get(key_after) is not None

    def test_submenu_endpoint_returns_correct_content(self, tree):
        client = Client()
        response = client.get("/categories/transport/submenu/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "Велосипеды" in content
        assert "Автомобили" in content
        assert "Устаревшее" not in content
