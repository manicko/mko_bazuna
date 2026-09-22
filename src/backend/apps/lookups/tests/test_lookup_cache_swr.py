"""
Tests for lookup cache SWR + version-bump behavior (13-PERF-002 / 13-PERF-003).

Covers:
  - SWR state machine on lookup cache reads (fresh hit, stale serve,
    cold miss winner/loser, expiry)
  - Version-bump invalidation (version increments, key changes)
  - Integration: LookupItem/Category save triggers version-bump invalidation
    for both LookupCacheService and CategoryLookupResolver

LocMemCache is used in tests (settings/test.py). Under LocMemCache:
  - ``cache.add`` single-flight is intra-process only
  - ``cache.incr`` is thread-safe (Django acquires a per-key lock)
  - ``cache.delete_pattern`` does not exist (no-op)
Tests therefore assert version-bump and SWR behavior, never delete_pattern.
"""

from __future__ import annotations

import time

import pytest
from django.core.cache import cache

from apps.categories.services.lookup_resolution import (
    LOOKUP_RESOLVE_CACHE_LOCK_TTL,
    LOOKUP_RESOLVE_CACHE_STALE_TTL,
    LOOKUP_RESOLVE_CACHE_TTL,
    RESOLVED_CONDITIONS_SEGMENT,
    RESOLVED_FEATURES_SEGMENT,
    RESOLVED_PURPOSES_SEGMENT,
    CategoryLookupResolver,
    bump_lookup_resolve_version,
    get_lookup_resolve_version,
    resolved_lookup_key,
)
from apps.core.utils.swr_cache import (
    _CACHE_LOCK_SUFFIX,
    get_with_stale_revalidate,
)
from apps.lookups.enums import LookupGroupCode
from apps.lookups.models import LookupGroup, LookupItem
from apps.lookups.services.cache_service import (
    LOOKUP_CACHE_LOCK_TTL,
    LOOKUP_CACHE_STALE_TTL,
    LOOKUP_CACHE_TTL,
    LookupCacheKey,
    LookupCacheService,
    active_items_key,
    all_groups_key,
    bump_lookup_version,
    get_lookup_version,
)

# ---------------------------------------------------------------------------
# Cache-entry helpers (replicate the _CacheEntry dict format from swr_cache.py)
# ---------------------------------------------------------------------------


def _make_entry(value, age_seconds: float = 0.0) -> dict:
    """Build a _CacheEntry-compatible dict stored by get_with_stale_revalidate."""
    return {"value": value, "stored_at": time.time() - age_seconds}


# ---------------------------------------------------------------------------
# SWR unit tests for LookupCacheService (no database)
# ---------------------------------------------------------------------------


class TestLookupCacheServiceSwr:
    """SWR state machine for LookupCacheService reads."""

    pytestmark = pytest.mark.unit

    def test_fresh_hit_returns_cached_without_producer(self):
        """A fresh cache entry (age < ttl) is served immediately."""
        key = all_groups_key()
        cache.set(
            key,
            _make_entry(["group_a"], age_seconds=1.0),
            timeout=LOOKUP_CACHE_TTL + LOOKUP_CACHE_STALE_TTL + 60,
        )

        call_count = 0

        def producer():
            nonlocal call_count
            call_count += 1
            return ["group_b"]

        # Call the internal SWR path directly to test the producer contract
        val = get_with_stale_revalidate(
            key,
            producer,
            ttl=LOOKUP_CACHE_TTL,
            stale_ttl=LOOKUP_CACHE_STALE_TTL,
            lock_ttl=LOOKUP_CACHE_LOCK_TTL,
            default=[],
        )

        assert list(val) == ["group_a"]
        assert call_count == 0

    def test_stale_hit_serves_stale_value(self):
        """A stale entry (ttl <= age < ttl + stale_ttl) is served while the
        winner recomputes in the background."""
        key = all_groups_key()
        cache.set(
            key,
            _make_entry(["stale_data"], age_seconds=LOOKUP_CACHE_TTL + 30),
            timeout=LOOKUP_CACHE_TTL + LOOKUP_CACHE_STALE_TTL + 60,
        )

        call_count = 0

        def producer():
            nonlocal call_count
            call_count += 1
            return ["fresh_data"]

        val = get_with_stale_revalidate(
            key,
            producer,
            ttl=LOOKUP_CACHE_TTL,
            stale_ttl=LOOKUP_CACHE_STALE_TTL,
            lock_ttl=LOOKUP_CACHE_LOCK_TTL,
            default=[],
        )

        # Stale value is served to the caller
        assert list(val) == ["stale_data"]
        # Winner recombined once
        assert call_count == 1

    def test_cold_miss_recomputes_and_caches(self):
        """A cold miss (no cache entry) triggers a single recompute."""
        key = all_groups_key()  # version 0 by default

        call_count = 0

        def producer():
            nonlocal call_count
            call_count += 1
            return ["computed"]

        val = get_with_stale_revalidate(
            key,
            producer,
            ttl=LOOKUP_CACHE_TTL,
            stale_ttl=LOOKUP_CACHE_STALE_TTL,
            lock_ttl=LOOKUP_CACHE_LOCK_TTL,
            default=[],
        )

        assert list(val) == ["computed"]
        assert call_count == 1

        cached = cache.get(key)
        assert cached is not None
        assert cached["value"] == ["computed"]

    def test_cold_miss_lock_held_returns_default(self):
        """Cold miss with lock held by another worker returns default."""
        key = all_groups_key()
        lock_key = f"{key}{_CACHE_LOCK_SUFFIX}"
        cache.add(lock_key, "1", LOOKUP_CACHE_LOCK_TTL)

        call_count = 0

        def producer():
            nonlocal call_count
            call_count += 1
            return ["should_not_run"]

        val = get_with_stale_revalidate(
            key,
            producer,
            ttl=LOOKUP_CACHE_TTL,
            stale_ttl=LOOKUP_CACHE_STALE_TTL,
            lock_ttl=LOOKUP_CACHE_LOCK_TTL,
            default=[],
        )

        assert list(val) == []
        assert call_count == 0

    def test_expired_entry_triggers_recompute(self):
        """Entry past ttl + stale_ttl is treated as a cold miss."""
        key = all_groups_key()
        cache.set(
            key,
            _make_entry(["expired_data"], age_seconds=LOOKUP_CACHE_TTL + LOOKUP_CACHE_STALE_TTL + 10),
            timeout=LOOKUP_CACHE_TTL + LOOKUP_CACHE_STALE_TTL + 120,
        )

        def producer():
            return ["new_data"]

        val = get_with_stale_revalidate(
            key,
            producer,
            ttl=LOOKUP_CACHE_TTL,
            stale_ttl=LOOKUP_CACHE_STALE_TTL,
            lock_ttl=LOOKUP_CACHE_LOCK_TTL,
            default=[],
        )

        assert list(val) == ["new_data"]


# ---------------------------------------------------------------------------
# Version-bump unit tests for LookupCacheService
# ---------------------------------------------------------------------------


class TestLookupVersionBump:
    """Version-bump invalidation replaces prefix-wipe delete_pattern."""

    pytestmark = pytest.mark.unit

    def test_get_lookup_version_defaults_to_zero(self):
        assert get_lookup_version() == 0

    def test_bump_lookup_version_increments(self):
        assert get_lookup_version() == 0
        bump_lookup_version()
        assert get_lookup_version() == 1
        bump_lookup_version()
        assert get_lookup_version() == 2

    def test_all_groups_key_includes_version(self):
        version = get_lookup_version()
        key = all_groups_key()
        assert key == f"{LookupCacheKey.V1}:{version}:all_groups"
        assert key.startswith("lookup:v1:")

    def test_all_groups_key_changes_when_version_bumps(self):
        key_before = all_groups_key()
        bump_lookup_version()
        key_after = all_groups_key()
        assert key_after != key_before
        assert key_after.startswith(f"{LookupCacheKey.V1}:1:")

    def test_active_items_key_includes_version(self):
        version = get_lookup_version()
        key = active_items_key("listing_purpose")
        assert key == f"{LookupCacheKey.V1}:{version}:items:listing_purpose"

    def test_active_items_key_changes_when_version_bumps(self):
        key_before = active_items_key("listing_purpose")
        bump_lookup_version()
        key_after = active_items_key("listing_purpose")
        assert key_after != key_before


# ---------------------------------------------------------------------------
# SWR unit tests for CategoryLookupResolver (no database)
# ---------------------------------------------------------------------------


class TestLookupResolverSwr:
    """SWR state machine for resolved-lookup cache reads."""

    pytestmark = pytest.mark.unit

    def test_fresh_hit_resolved_returns_cached(self):
        segment = RESOLVED_PURPOSES_SEGMENT
        category_id = 42
        key = resolved_lookup_key(segment, category_id)
        cache.set(
            key,
            _make_entry(["item1"], age_seconds=1.0),
            timeout=LOOKUP_RESOLVE_CACHE_TTL + LOOKUP_RESOLVE_CACHE_STALE_TTL + 60,
        )

        call_count = 0

        def producer():
            nonlocal call_count
            call_count += 1
            return ["item2"]

        val = get_with_stale_revalidate(
            key,
            producer,
            ttl=LOOKUP_RESOLVE_CACHE_TTL,
            stale_ttl=LOOKUP_RESOLVE_CACHE_STALE_TTL,
            lock_ttl=LOOKUP_RESOLVE_CACHE_LOCK_TTL,
            default=[],
        )

        assert list(val) == ["item1"]
        assert call_count == 0

    def test_stale_hit_resolved_serves_stale(self):
        segment = RESOLVED_FEATURES_SEGMENT
        category_id = 7
        key = resolved_lookup_key(segment, category_id)
        cache.set(
            key,
            _make_entry(["stale_feat"], age_seconds=LOOKUP_RESOLVE_CACHE_TTL + 30),
            timeout=LOOKUP_RESOLVE_CACHE_TTL + LOOKUP_RESOLVE_CACHE_STALE_TTL + 60,
        )

        call_count = 0

        def producer():
            nonlocal call_count
            call_count += 1
            return ["fresh_feat"]

        val = get_with_stale_revalidate(
            key,
            producer,
            ttl=LOOKUP_RESOLVE_CACHE_TTL,
            stale_ttl=LOOKUP_RESOLVE_CACHE_STALE_TTL,
            lock_ttl=LOOKUP_RESOLVE_CACHE_LOCK_TTL,
            default=[],
        )

        assert list(val) == ["stale_feat"]
        assert call_count == 1

    def test_cold_miss_resolved_recomputes(self):
        segment = RESOLVED_CONDITIONS_SEGMENT
        category_id = 99
        key = resolved_lookup_key(segment, category_id)

        def producer():
            return ["computed_cond"]

        val = get_with_stale_revalidate(
            key,
            producer,
            ttl=LOOKUP_RESOLVE_CACHE_TTL,
            stale_ttl=LOOKUP_RESOLVE_CACHE_STALE_TTL,
            lock_ttl=LOOKUP_RESOLVE_CACHE_LOCK_TTL,
            default=[],
        )

        assert list(val) == ["computed_cond"]

    def test_cold_miss_lock_held_resolved_returns_default(self):
        segment = RESOLVED_PURPOSES_SEGMENT
        category_id = 55
        key = resolved_lookup_key(segment, category_id)
        lock_key = f"{key}{_CACHE_LOCK_SUFFIX}"
        cache.add(lock_key, "1", LOOKUP_RESOLVE_CACHE_LOCK_TTL)

        call_count = 0

        def producer():
            nonlocal call_count
            call_count += 1
            return ["should_not_run"]

        val = get_with_stale_revalidate(
            key,
            producer,
            ttl=LOOKUP_RESOLVE_CACHE_TTL,
            stale_ttl=LOOKUP_RESOLVE_CACHE_STALE_TTL,
            lock_ttl=LOOKUP_RESOLVE_CACHE_LOCK_TTL,
            default=[],
        )

        assert list(val) == []
        assert call_count == 0


# ---------------------------------------------------------------------------
# Version-bump tests for CategoryLookupResolver
# ---------------------------------------------------------------------------


class TestLookupResolveVersionBump:
    """Version-bump invalidation for resolved-lookup caches."""

    pytestmark = pytest.mark.unit

    def test_get_lookup_resolve_version_defaults_to_zero(self):
        assert get_lookup_resolve_version() == 0

    def test_bump_lookup_resolve_version_increments(self):
        assert get_lookup_resolve_version() == 0
        bump_lookup_resolve_version()
        assert get_lookup_resolve_version() == 1
        bump_lookup_resolve_version()
        assert get_lookup_resolve_version() == 2

    def test_resolved_lookup_key_includes_version(self):
        version = get_lookup_resolve_version()
        key = resolved_lookup_key(RESOLVED_PURPOSES_SEGMENT, 1)
        assert key == f"lookup:v1:resolve:{version}:purposes:1"

    def test_resolved_lookup_key_changes_when_version_bumps(self):
        key_before = resolved_lookup_key(RESOLVED_FEATURES_SEGMENT, 2)
        bump_lookup_resolve_version()
        key_after = resolved_lookup_key(RESOLVED_FEATURES_SEGMENT, 2)
        assert key_after != key_before
        assert ":1:" in key_after  # version segment changed to 1


# ---------------------------------------------------------------------------
# Integration tests (with database)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.integration
class TestLookupCacheIntegration:
    """Integration: cache priming, version-bump invalidation, and recomputation."""

    def test_get_all_groups_primes_cache_then_version_bump_misses(
        self, category
    ) -> None:
        """After priming and version-bump, the next read is a cold miss."""
        LookupGroup.objects.create(
            code=LookupGroupCode.LISTING_PURPOSE,
            name_i18n={"ru": "Тип", "bs": "Tip", "en": "Type"},
        )

        version_before = get_lookup_version()
        key_before = all_groups_key()

        # Prime
        result = LookupCacheService.get_all_groups()
        assert len(result) == 1
        assert result[0].code == LookupGroupCode.LISTING_PURPOSE

        # Cache is primed
        cached = cache.get(key_before)
        assert cached is not None

        # Bump version — simulates invalidation signal
        bump_lookup_version()

        version_after = get_lookup_version()
        key_after = all_groups_key()
        assert version_after > version_before
        assert key_after != key_before

        # Old key still has data (not deleted) but is unreachable
        assert cache.get(key_before) is not None

        # New key is a cold miss — recomputes
        cache.delete(key_after)  # ensure cold miss
        result2 = LookupCacheService.get_all_groups()
        assert len(result2) == 1
        assert result2[0].code == LookupGroupCode.LISTING_PURPOSE

    def test_get_active_items_primes_and_invalidates(self, category) -> None:
        """Active items cache is primed then invalidated via version bump."""
        group = LookupGroup.objects.create(
            code=LookupGroupCode.LISTING_PURPOSE,
            name_i18n={"ru": "Тип", "bs": "Tip", "en": "Type"},
        )
        LookupItem.objects.create(
            group=group,
            slug="sell",
            name_i18n={"ru": "Продам", "bs": "Prodam", "en": "Sell"},
            is_active=True,
        )

        key_before = active_items_key(group.code)

        # Prime
        items = LookupCacheService.get_active_items(group.code)
        assert len(items) == 1
        assert items[0].slug == "sell"
        cached = cache.get(key_before)
        assert cached is not None

        # Bump version
        bump_lookup_version()
        key_after = active_items_key(group.code)
        assert key_after != key_before

        # New key is cold miss
        cache.delete(key_after)
        items2 = LookupCacheService.get_active_items(group.code)
        assert len(items2) == 1
        assert items2[0].slug == "sell"


@pytest.mark.django_db
@pytest.mark.integration
class TestLookupInvalidationOnSave:
    """Integration: model save/delete triggers version-bump invalidation."""

    def test_lookup_item_save_bumps_version(
        self, category
    ) -> None:
        """Saving a LookupItem triggers signals that bump the resolve version."""
        from apps.categories.models import CategoryListingPurpose

        group = LookupGroup.objects.create(
            code=LookupGroupCode.LISTING_PURPOSE,
            name_i18n={"ru": "Тип", "bs": "Tip", "en": "Type"},
        )
        item = LookupItem.objects.create(
            group=group,
            slug="sell",
            name_i18n={"ru": "Продам", "bs": "Prodam", "en": "Sell"},
            is_active=True,
        )
        CategoryListingPurpose.objects.create(category=category, listing_purpose=item)

        version_before = get_lookup_resolve_version()

        # Prime the resolved-lookup cache
        CategoryLookupResolver.get_resolved_purposes(category)
        assert get_lookup_resolve_version() == version_before

        # Save the item (name change) — triggers invalidate_on_lookup_item_change
        item.name_i18n = {
            "ru": "Продам", "bs": "Prodam", "en": "Sell Updated"
        }
        item.save(update_fields=["name_i18n"])

        version_after = get_lookup_resolve_version()
        assert version_after > version_before

    def test_category_save_bumps_resolve_version(
        self, category
    ) -> None:
        """Saving a Category triggers bump_tree_version (categories.cache),
        and a through-model change triggers resolve version bump."""
        from apps.categories.models import CategoryListingPurpose

        group = LookupGroup.objects.create(
            code=LookupGroupCode.LISTING_PURPOSE,
            name_i18n={"ru": "Тип", "bs": "Tip", "en": "Type"},
        )
        item = LookupItem.objects.create(
            group=group,
            slug="sell",
            name_i18n={"ru": "Продам", "bs": "Prodam", "en": "Sell"},
            is_active=True,
        )

        version_before = get_lookup_resolve_version()

        # Create a through-row — triggers invalidate_category_lookup_cache
        CategoryListingPurpose.objects.create(
            category=category, listing_purpose=item
        )

        version_after = get_lookup_resolve_version()
        assert version_after > version_before

    def test_resolved_cache_serves_fresh_after_invalidation(
        self, category
    ) -> None:
        """After a LookupItem change, the resolved cache returns fresh data."""
        from apps.categories.models import CategoryListingPurpose

        group = LookupGroup.objects.create(
            code=LookupGroupCode.LISTING_PURPOSE,
            name_i18n={"ru": "Тип", "bs": "Tip", "en": "Type"},
        )
        item = LookupItem.objects.create(
            group=group,
            slug="sell",
            name_i18n={"ru": "Продам", "bs": "Prodam", "en": "Sell"},
            is_active=True,
        )
        CategoryListingPurpose.objects.create(category=category, listing_purpose=item)

        # Prime cache — should return the item
        purposes_before = CategoryLookupResolver.get_resolved_purposes(category)
        assert len(purposes_before) == 1
        assert purposes_before[0].slug == "sell"

        # Change the item name — should bump version
        item.name_i18n = {
            "ru": "Продам", "bs": "Prodam", "en": "Sell Renamed"
        }
        item.save(update_fields=["name_i18n"])

        # Next read — cold miss (new key) → recompute → fresh name
        purposes_after = CategoryLookupResolver.get_resolved_purposes(category)
        assert len(purposes_after) == 1
        assert purposes_after[0].name_i18n["en"] == "Sell Renamed"
