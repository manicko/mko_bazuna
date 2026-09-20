"""
Tests for search result cache (PERF-003): SWR + single-flight stampede guard.

Covers:
  - SWR state machine (fresh hit, stale serve, cold miss winner/loser, expiry)
  - Cache entry size limit (prevents memory bloat)
  - Cache key generation (all parameters produce unique keys)
  - Cache invalidation on ad status change (PUBLISHED / ARCHIVED / DELETED)
  - Search view integration (cache miss → populate, cache hit → reuse)
  - Fallback to direct FTS when cache is cold with a held lock
"""

from __future__ import annotations

import time

import pytest
from django.core.cache import cache
from django.test import Client

from apps.ads.services.listings_query import ListingsQueryParams
from apps.core.enums import AdSort, AdStatus, LanguageLocale
from apps.core.utils.swr_cache import (
    _CACHE_LOCK_SUFFIX,
    get_with_stale_revalidate,
)
from apps.search.services.cache import (
    SearchCacheKey,
    build_search_cache_key,
    bump_search_cache_version,
    bump_search_version,
    get_cached_search_ids,
    get_search_version,
    invalidate_search_cache,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _get_backend() -> object:
    """Return the actual LocMemCache backend instance from the ConnectionProxy.

    ``django.core.cache.cache`` is a ``ConnectionProxy`` that delegates
    attribute access to the underlying backend via ``__getattr__``. We
    access the backend through ``_connections`` to get the real instance
    for direct ``_cache`` dict access.
    """
    # ConnectionProxy delegates to the backend; _connections holds the handler
    conn_proxy = cache  # type: ignore[assignment]
    try:
        backend = conn_proxy._connections[conn_proxy._alias]  # type: ignore[attr-defined]
    except AttributeError, KeyError:
        backend = cache
    return backend


def _get_cache_keys(prefix: str) -> list[str]:
    """Return all cache keys visible to the application that start with *prefix*.

    LocMemCache stores keys internally with a version prefix (":1:<key>");
    this helper strips it so tests can assert on the user-facing key names.
    """
    backend = _get_backend()
    internal = getattr(backend, "_cache", {})
    keys: list[str] = []
    for internal_key in internal:
        key_str = str(internal_key)
        # Strip LocMemCache version prefix: ":1:search:v1:..." -> "search:v1:..."
        parts = key_str.split(":", 2)
        if len(parts) >= 3 and parts[0] == "":
            user_key = parts[2]
        else:
            user_key = key_str
        if user_key.startswith(prefix):
            keys.append(user_key)
    return keys


# ---------------------------------------------------------------------------
# SWR utility unit tests (no database)
# ---------------------------------------------------------------------------


class TestSwrFreshHit:
    """Fresh cache entry (age < ttl) is served immediately."""

    pytestmark = pytest.mark.unit

    def test_fresh_hit_returns_cached_value(self):
        key = "test:swr:fresh"
        cache.set(
            key,
            {"value": [1, 2, 3], "stored_at": time.time() - 1.0},
            timeout=400,
        )

        result = get_with_stale_revalidate(
            key,
            lambda: [9, 9, 9],
            ttl=300,
            stale_ttl=60,
            lock_ttl=30,
            default=None,
        )

        assert result == [1, 2, 3]

    def test_fresh_hit_does_not_call_producer(self):
        key = "test:swr:fresh_no_call"
        cache.set(
            key,
            {"value": [1, 2], "stored_at": time.time() - 1.0},
            timeout=400,
        )

        call_count = 0

        def producer():
            nonlocal call_count
            call_count += 1
            return [9, 9]

        get_with_stale_revalidate(
            key,
            producer,
            ttl=300,
            stale_ttl=60,
            lock_ttl=30,
            default=None,
        )

        assert call_count == 0

    def test_fresh_hit_does_not_acquire_lock(self):
        key = "test:swr:fresh_lock"
        cache.set(
            key,
            {"value": [1], "stored_at": time.time() - 1.0},
            timeout=400,
        )

        get_with_stale_revalidate(
            key,
            lambda: [42],
            ttl=300,
            stale_ttl=60,
            lock_ttl=30,
            default=None,
        )

        lock_key = f"{key}{_CACHE_LOCK_SUFFIX}"
        assert cache.get(lock_key) is None


class TestSwrStaleServe:
    """Stale entry (ttl <= age < ttl + stale_ttl) is served immediately;
    winner recomputes in the background."""

    pytestmark = pytest.mark.unit

    def test_stale_hit_serves_stale_value(self):
        key = "test:swr:stale"
        # age = 350s → stale (ttl=300) but within stale window (ttl+stale=360)
        cache.set(
            key,
            {"value": [1, 2, 3], "stored_at": time.time() - 350.0},
            timeout=400,
        )

        call_count = 0

        def producer():
            nonlocal call_count
            call_count += 1
            return [4, 5, 6]

        result = get_with_stale_revalidate(
            key,
            producer,
            ttl=300,
            stale_ttl=60,
            lock_ttl=30,
            default=None,
        )

        assert result == [1, 2, 3]  # stale value served
        assert call_count == 1  # winner recomputed

    def test_stale_hit_winner_replaces_cache(self):
        key = "test:swr:stale_replace"
        cache.set(
            key,
            {"value": [1, 2], "stored_at": time.time() - 350.0},
            timeout=400,
        )

        def producer():
            return [7, 8]

        result = get_with_stale_revalidate(
            key,
            producer,
            ttl=300,
            stale_ttl=60,
            lock_ttl=30,
            default=None,
        )

        assert result == [1, 2]  # stale served to caller

        # Cache now holds the fresh value
        cached = cache.get(key)
        assert cached is not None
        assert cached["value"] == [7, 8]

    def test_stale_hit_lock_held_returns_stale_no_recompute(self):
        """When the lock is already held by another worker, the stale value
        is served without the current worker recomputing."""
        key = "test:swr:stale_lock_held"
        cache.set(
            key,
            {"value": [1, 2], "stored_at": time.time() - 350.0},
            timeout=400,
        )
        lock_key = f"{key}:lock"
        cache.add(lock_key, "1", 30)

        call_count = 0

        def producer():
            nonlocal call_count
            call_count += 1
            return [9, 9]

        result = get_with_stale_revalidate(
            key,
            producer,
            ttl=300,
            stale_ttl=60,
            lock_ttl=30,
            default=None,
        )

        assert result == [1, 2]  # stale value served
        assert call_count == 0  # no recompute (lock held)


class TestSwrColdMiss:
    """Cold miss: no cache entry exists."""

    pytestmark = pytest.mark.unit

    def test_cold_miss_winner_recomputes_and_caches(self):
        key = "test:swr:cold_winner"

        call_count = 0

        def producer():
            nonlocal call_count
            call_count += 1
            return [1, 2, 3]

        result = get_with_stale_revalidate(
            key,
            producer,
            ttl=300,
            stale_ttl=60,
            lock_ttl=30,
            default=None,
        )

        assert result == [1, 2, 3]
        assert call_count == 1

        cached = cache.get(key)
        assert cached is not None
        assert cached["value"] == [1, 2, 3]

    def test_cold_miss_loser_returns_default(self):
        """When the lock is held and no stale value exists, ``default`` is
        returned instead of running the producer."""
        key = "test:swr:cold_loser"
        lock_key = f"{key}{_CACHE_LOCK_SUFFIX}"
        cache.add(lock_key, "1", 30)

        call_count = 0

        def producer():
            nonlocal call_count
            call_count += 1
            return [1, 2]

        result = get_with_stale_revalidate(
            key,
            producer,
            ttl=300,
            stale_ttl=60,
            lock_ttl=30,
            default="fallback",
        )

        assert result == "fallback"
        assert call_count == 0

    def test_cold_miss_producer_exception_propagates(self):
        """Producer exception on a cold miss (winner) propagates."""

        def failing_producer():
            raise RuntimeError("FTS query failed")

        with pytest.raises(RuntimeError, match="FTS query failed"):
            get_with_stale_revalidate(
                "test:swr:cold_exc",
                failing_producer,
                ttl=300,
                stale_ttl=60,
                lock_ttl=30,
                default=None,
            )

    def test_stale_recompute_exception_does_not_propagate(self):
        """Producer exception on the stale-hit winner is caught — the stale
        value is still returned to the caller."""
        key = "test:swr:stale_exc"
        cache.set(
            key,
            {"value": [1, 2], "stored_at": time.time() - 350.0},
            timeout=400,
        )

        def failing_producer():
            raise RuntimeError("recompute failed")

        result = get_with_stale_revalidate(
            key,
            failing_producer,
            ttl=300,
            stale_ttl=60,
            lock_ttl=30,
            default="fallback",
        )

        assert result == [1, 2]  # stale value still served


class TestSwrExpiredEntry:
    """Entry past ttl + stale_ttl is treated as a cold miss."""

    pytestmark = pytest.mark.unit

    def test_expired_entry_triggers_recompute(self):
        key = "test:swr:expired"
        # age = 400s > ttl + stale_ttl (360) → past the stale window
        cache.set(
            key,
            {"value": [1, 2], "stored_at": time.time() - 400.0},
            timeout=500,
        )

        def producer():
            return [3, 4]

        result = get_with_stale_revalidate(
            key,
            producer,
            ttl=300,
            stale_ttl=60,
            lock_ttl=30,
            default=None,
        )

        assert result == [3, 4]


class TestSwrMaxSizeGuard:
    """Entries exceeding max_size_bytes are returned but not cached."""

    pytestmark = pytest.mark.unit

    def test_oversized_value_not_cached(self):
        key = "test:swr:max_size"

        large_value = [0] * 100_000  # ~800 KB when pickled

        result = get_with_stale_revalidate(
            key,
            lambda: large_value,
            ttl=300,
            stale_ttl=60,
            lock_ttl=30,
            default=None,
            max_size_bytes=1024,
        )

        assert result == large_value
        assert cache.get(key) is None  # not cached (too large)

    def test_small_value_is_cached(self):
        key = "test:swr:small_ok"

        result = get_with_stale_revalidate(
            key,
            lambda: [1, 2, 3],
            ttl=300,
            stale_ttl=60,
            lock_ttl=30,
            default=None,
            max_size_bytes=1024,
        )

        assert result == [1, 2, 3]
        assert cache.get(key) is not None


# ---------------------------------------------------------------------------
# Cache service unit tests (no database)
# ---------------------------------------------------------------------------


class TestSearchCacheKey:
    """Cache key encoding includes all search-varying parameters."""

    pytestmark = pytest.mark.unit

    @staticmethod
    def _params(**overrides: object) -> ListingsQueryParams:
        return ListingsQueryParams(**overrides)  # type: ignore[arg-type]

    def test_key_differs_by_query(self):
        base = self._params()
        locale = LanguageLocale.RUSSIAN
        key_a = build_search_cache_key(base, "велосипед", locale)
        key_b = build_search_cache_key(base, "самокат", locale)
        assert key_a != key_b

    def test_key_differs_by_empty_vs_nonempty_query(self):
        base = self._params()
        locale = LanguageLocale.RUSSIAN
        key_empty = build_search_cache_key(base, "", locale)
        key_term = build_search_cache_key(base, "велосипед", locale)
        assert key_empty != key_term

    def test_key_differs_by_locale(self):
        base = self._params()
        key_ru = build_search_cache_key(base, "велосипед", LanguageLocale.RUSSIAN)
        key_bs = build_search_cache_key(base, "велосипед", LanguageLocale.BOSNIAN)
        key_en = build_search_cache_key(base, "велосипед", LanguageLocale.ENGLISH)
        assert key_ru != key_bs
        assert key_ru != key_en

    def test_key_differs_by_category(self):
        locale = LanguageLocale.RUSSIAN
        key_a = build_search_cache_key(
            self._params(category_slug="transport"), "q", locale
        )
        key_b = build_search_cache_key(
            self._params(category_slug="electronics"), "q", locale
        )
        assert key_a != key_b

    def test_key_differs_by_city(self):
        locale = LanguageLocale.RUSSIAN
        key_a = build_search_cache_key(self._params(city_slug="moscow"), "q", locale)
        key_b = build_search_cache_key(self._params(city_slug="spb"), "q", locale)
        assert key_a != key_b

    def test_key_differs_by_min_price(self):
        locale = LanguageLocale.RUSSIAN
        key_a = build_search_cache_key(self._params(min_price=100), "q", locale)
        key_b = build_search_cache_key(self._params(min_price=500), "q", locale)
        assert key_a != key_b

    def test_key_differs_by_max_price(self):
        locale = LanguageLocale.RUSSIAN
        key_a = build_search_cache_key(self._params(max_price=1000), "q", locale)
        key_b = build_search_cache_key(self._params(max_price=2000), "q", locale)
        assert key_a != key_b

    def test_key_differs_by_purpose(self):
        locale = LanguageLocale.RUSSIAN
        key_a = build_search_cache_key(self._params(purpose_slug="sell"), "q", locale)
        key_b = build_search_cache_key(self._params(purpose_slug="buy"), "q", locale)
        assert key_a != key_b

    def test_key_differs_by_condition(self):
        locale = LanguageLocale.RUSSIAN
        key_a = build_search_cache_key(self._params(condition_slug="new"), "q", locale)
        key_b = build_search_cache_key(self._params(condition_slug="used"), "q", locale)
        assert key_a != key_b

    def test_key_differs_by_sort(self):
        locale = LanguageLocale.RUSSIAN
        key_date_new = build_search_cache_key(
            self._params(sort=AdSort.DATE_NEW), "q", locale
        )
        key_price_low = build_search_cache_key(
            self._params(sort=AdSort.PRICE_LOW), "q", locale
        )
        assert key_date_new != key_price_low

    def test_key_differs_by_per_page(self):
        locale = LanguageLocale.RUSSIAN
        key_24 = build_search_cache_key(self._params(per_page=24), "q", locale)
        key_12 = build_search_cache_key(self._params(per_page=12), "q", locale)
        assert key_24 != key_12

    def test_feature_slugs_are_order_independent(self):
        """Same features in different order → same key (order-independent)."""
        locale = LanguageLocale.RUSSIAN
        key_a = build_search_cache_key(
            self._params(feature_slugs=["gps", "abs"]), "q", locale
        )
        key_b = build_search_cache_key(
            self._params(feature_slugs=["abs", "gps"]), "q", locale
        )
        assert key_a == key_b

    def test_different_features_produce_different_keys(self):
        locale = LanguageLocale.RUSSIAN
        key_a = build_search_cache_key(self._params(feature_slugs=["gps"]), "q", locale)
        key_b = build_search_cache_key(self._params(feature_slugs=["abs"]), "q", locale)
        assert key_a != key_b

    def test_key_is_deterministic(self):
        """Same parameters always produce the same key."""
        params = self._params(
            category_slug="transport",
            city_slug="moscow",
            min_price=100,
            max_price=500,
            purpose_slug="sell",
            condition_slug="new",
            feature_slugs=["gps", "abs"],
            sort=AdSort.PRICE_HIGH,
            per_page=24,
        )
        locale = LanguageLocale.RUSSIAN
        key_a = build_search_cache_key(params, "велосипед", locale)
        key_b = build_search_cache_key(params, "велосипед", locale)
        assert key_a == key_b

    def test_key_has_versioned_prefix(self):
        key = build_search_cache_key(self._params(), "test", LanguageLocale.RUSSIAN)
        assert key.startswith(f"{SearchCacheKey.V1}:")

    def test_key_embeds_content_version(self):
        """The content version is embedded as the segment after ``search:v1``."""
        version = get_search_version()
        key = build_search_cache_key(self._params(), "test", LanguageLocale.RUSSIAN)
        assert f"{SearchCacheKey.V1}:{version}:" in key

    def test_key_changes_when_version_bumps(self):
        """Bumping the version produces a different cache key."""
        params = self._params()
        locale = LanguageLocale.RUSSIAN
        key_before = build_search_cache_key(params, "test", locale)

        bump_search_version()

        key_after = build_search_cache_key(params, "test", locale)
        assert key_after != key_before
        assert key_after.startswith(f"{SearchCacheKey.V1}:1:")


class TestGetCachedSearchIds:
    """Unit tests for the search cache service wrapper."""

    pytestmark = pytest.mark.unit

    def test_cold_miss_calls_producer(self):
        key = "test:get_cached:miss"

        def producer():
            return [1, 2, 3]

        result = get_cached_search_ids(key, producer)
        assert result == [1, 2, 3]

    def test_fresh_hit_returns_cached_without_producer(self):
        key = "test:get_cached:fresh"
        cache.set(
            key,
            {"value": [1, 2], "stored_at": time.time() - 1.0},
            timeout=400,
        )
        call_count = 0

        def producer():
            nonlocal call_count
            call_count += 1
            return [9, 9]

        result = get_cached_search_ids(key, producer)
        assert result == [1, 2]
        assert call_count == 0

    def test_none_on_cold_miss_lock_held(self):
        key = "test:get_cached:lock"
        cache.add(f"{key}:lock", "1", 30)

        result = get_cached_search_ids(key, lambda: [1, 2])
        assert result is None


class TestSearchCacheVersionBump:
    """Content-freshness version bumping replaces global prefix wipe."""

    pytestmark = pytest.mark.unit

    def test_get_search_version_defaults_to_zero(self):
        assert get_search_version() == 0

    def test_bump_search_version_increments(self):
        assert get_search_version() == 0
        bump_search_version()
        assert get_search_version() == 1
        bump_search_version()
        assert get_search_version() == 2

    def test_bump_search_cache_version_delegates_to_bump(self):
        bump_search_cache_version()
        assert get_search_version() == 1

    def test_invalidate_search_cache_alias_bumps_version(self):
        invalidate_search_cache()
        assert get_search_version() == 1


# ---------------------------------------------------------------------------
# Search view integration tests (with database)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.integration
class TestSearchViewCaching:
    """Integration: search view caching behavior with real FTS."""

    def test_first_search_populates_cache(self, seller, category, city):
        """After a search, the cache contains a search:v1: entry."""
        from conftest import create_test_ad

        create_test_ad(
            seller,
            category,
            city,
            title="Красный товар",
            status=AdStatus.PUBLISHED,
        )

        search_keys_before = _get_cache_keys("search:v1")
        assert len(search_keys_before) == 0

        client = Client()
        response = client.get("/search/?q=товар&lang=ru")

        assert response.status_code == 200
        assert len(list(response.context["page_obj"])) == 1

        search_keys_after = _get_cache_keys("search:v1")
        assert len(search_keys_after) >= 1

    def test_second_search_returns_same_results(self, seller, category, city):
        """Second identical search returns the same ads from cache."""
        from conftest import create_test_ad

        create_test_ad(
            seller,
            category,
            city,
            title="Синий товар",
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        resp1 = client.get("/search/?q=товар&lang=ru")
        ads1 = list(resp1.context["page_obj"])
        assert len(ads1) == 1

        resp2 = client.get("/search/?q=товар&lang=ru")
        ads2 = list(resp2.context["page_obj"])
        assert len(ads2) == 1
        assert ads1[0].id == ads2[0].id

    def test_cache_hit_does_not_reexecute_producer(
        self, seller, category, city, monkeypatch
    ):
        """Second search hits the cache — producer runs only once."""
        from conftest import create_test_ad

        create_test_ad(
            seller,
            category,
            city,
            title="Товар для кэша",
            status=AdStatus.PUBLISHED,
        )

        producer_call_count = 0
        original = get_cached_search_ids

        def counting_wrapper(cache_key, producer):
            nonlocal producer_call_count
            original_producer = producer

            def counting_producer():
                nonlocal producer_call_count
                producer_call_count += 1
                return original_producer()

            return original(cache_key, counting_producer)

        monkeypatch.setattr(
            "apps.search.views.search.get_cached_search_ids", counting_wrapper
        )

        client = Client()
        client.get("/search/?q=кэш&lang=ru")  # cache miss → producer runs
        assert producer_call_count == 1

        client.get("/search/?q=кэш&lang=ru")  # cache hit → producer skipped
        assert producer_call_count == 1  # still 1

    def test_empty_result_is_cached(self, seller, category, city):
        """Empty searches are cached (not re-executed on each request)."""
        from conftest import create_test_ad

        create_test_ad(
            seller,
            category,
            city,
            title="Совсем другой товар",
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get("/search/?q=несуществующий&lang=ru")
        assert response.status_code == 200
        assert len(list(response.context["page_obj"])) == 0

        # Cache should contain a search:v1: entry (empty result cached)
        search_keys = _get_cache_keys("search:v1")
        assert len(search_keys) >= 1

    def test_no_query_search_not_cached(self, seller, category, city):
        """Searches without a query parameter are not cached (listing path)."""
        from conftest import create_test_ad

        create_test_ad(
            seller,
            category,
            city,
            title="Товар",
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        client.get("/search/")

        # No cache entries from an empty query
        search_keys = _get_cache_keys("search:v1")
        assert len(search_keys) == 0

    def test_cold_miss_fallback_returns_results(
        self, seller, category, city, monkeypatch
    ):
        """When the cache returns None (lock held), the view falls back
        to a direct FTS query and still returns results."""
        from conftest import create_test_ad

        create_test_ad(
            seller,
            category,
            city,
            title="Фоллбэк товар",
            status=AdStatus.PUBLISHED,
        )

        # Force the cache service to return None (simulating cold miss + lock held)
        monkeypatch.setattr(
            "apps.search.views.search.get_cached_search_ids",
            lambda key, producer: None,
        )

        client = Client()
        response = client.get("/search/?q=товар&lang=ru")

        assert response.status_code == 200
        ads = list(response.context["page_obj"])
        assert len(ads) == 1


# ---------------------------------------------------------------------------
# Cache invalidation integration tests (with database)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.integration
class TestSearchCacheInvalidationOnPublish:
    """Cache invalidation via version bump when an ad's status changes."""

    def test_publish_ad_invalidates_cache(self, seller, category, city):
        """Publishing a new ad bumps the version so the next search re-executes
        and includes the new ad."""
        from conftest import create_test_ad

        create_test_ad(
            seller,
            category,
            city,
            title="Красный товар",
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        resp1 = client.get("/search/?q=товар&lang=ru")
        ads1 = list(resp1.context["page_obj"])
        assert len(ads1) == 1

        # Publishing a second ad bumps the content version
        version_before = get_search_version()
        create_test_ad(
            seller,
            category,
            city,
            title="Синий товар",
            status=AdStatus.PUBLISHED,
        )
        version_after = get_search_version()
        assert version_after > version_before

        # Cache key now embeds the new version → cache miss → 2 ads
        resp2 = client.get("/search/?q=товар&lang=ru")
        ads2 = list(resp2.context["page_obj"])
        assert len(ads2) == 2

    def test_transition_to_published_invalidates_cache(self, seller, category, city):
        """Ad.transition_to(PUBLISHED) bumps the content version."""
        from conftest import create_test_ad

        ad = create_test_ad(
            seller,
            category,
            city,
            title="Очередной товар",
            status=AdStatus.ON_MODERATION,
        )

        version_before = get_search_version()
        ad.transition_to(AdStatus.PUBLISHED)
        version_after = get_search_version()

        assert version_after > version_before

    def test_content_edit_bumps_version(self, seller, category, city):
        """Saving a visible ad's content field (title) bumps the version."""
        from conftest import create_test_ad

        ad = create_test_ad(
            seller,
            category,
            city,
            title="Товар",
            status=AdStatus.PUBLISHED,
        )

        version_before = get_search_version()
        ad.title = "Обновленный заголовок"
        ad.save(update_fields=["title"])
        version_after = get_search_version()

        assert version_after > version_before

    def test_draft_status_does_not_invalidate(self, seller, category, city):
        """Creating an ad with DRAFT status does not bump the version."""
        from conftest import create_test_ad

        version_before = get_search_version()

        create_test_ad(
            seller,
            category,
            city,
            title="Черновик товар",
            status=AdStatus.DRAFT,
        )

        version_after = get_search_version()
        assert version_after == version_before

    def test_archive_invalates_cache(self, seller, category, city):
        """Transitioning an ad to ARCHIVED bumps the content version."""
        from conftest import create_test_ad

        ad = create_test_ad(
            seller,
            category,
            city,
            title="Архивный товар",
            status=AdStatus.PUBLISHED,
        )

        version_before = get_search_version()
        ad.transition_to(AdStatus.ARCHIVED)
        version_after = get_search_version()

        assert version_after > version_before
