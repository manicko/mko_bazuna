"""
Tests for LookupItem cache invalidation correctness (PERF-004).

Verifies that RESOLVED_* caches (``lookup:resolved_purposes``,
``lookup:resolved_features``, ``lookup:resolved_conditions``) are properly
invalidated when a LookupItem changes — including name-only and slug-only
updates that previously hit the ``is_active``-only gate and were silently
skipped. Also confirms that cache backend failures must never roll back the
originating DB save (best-effort invalidation).
"""

from unittest.mock import Mock

import pytest
from django.core.cache import cache
from django_redis.exceptions import ConnectionInterrupted

from apps.categories.models import CategoryListingPurpose
from apps.categories.services.lookup_resolution import (
    RESOLVED_PURPOSES_PREFIX,
    CategoryLookupResolver,
)
from apps.lookups.enums import LookupGroupCode
from apps.lookups.models import LookupGroup, LookupItem

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def purpose_binding(category):
    """Create a listing-purpose LookupItem bound to *category* via a
    CategoryListingPurpose through-row.

    Returns ``(category, lookup_item)`` with the RESOLVED_* cache already
    primed, so tests can assert invalidation directly.
    """
    group = LookupGroup.objects.create(
        code=LookupGroupCode.LISTING_PURPOSE,
        name_i18n={"ru": "Тип сделки", "bs": "Vrsta transakcije", "en": "Listing type"},
    )
    item = LookupItem.objects.create(
        group=group,
        slug="sell",
        name_i18n={"ru": "Продам", "bs": "Prodam", "en": "Sell"},
        is_active=True,
    )
    CategoryListingPurpose.objects.create(category=category, listing_purpose=item)

    # Prime the cache so we can assert it is cleared afterwards.
    CategoryLookupResolver.get_resolved_purposes(category)
    return category, item


def _cache_key_for_purpose(category_id: int) -> str:
    """Build the RESOLVED_* cache key for a single category."""
    return f"{RESOLVED_PURPOSES_PREFIX}:{category_id}"


class TestLookupItemCacheInvalidation:
    """RESOLVED_* cache invalidation on LookupItem changes."""

    def test_name_only_update_invalidates_resolved_caches(
        self, purpose_binding: tuple
    ) -> None:
        """A name_i18n-only save must clear the resolved-purpose cache."""
        category, item = purpose_binding
        cache_key = _cache_key_for_purpose(category.id)

        # Cache was primed by the fixture.
        assert cache.get(cache_key) is not None

        item.name_i18n = {"ru": "Продам", "bs": "Prodam", "en": "Sell — updated"}
        item.save(update_fields=["name_i18n"])

        assert cache.get(cache_key) is None

    def test_slug_only_update_invalidates_resolved_caches(
        self, purpose_binding: tuple
    ) -> None:
        """A slug-only save must clear the resolved-purpose cache."""
        category, item = purpose_binding
        cache_key = _cache_key_for_purpose(category.id)

        assert cache.get(cache_key) is not None

        item.slug = "sell-updated"
        item.save(update_fields=["slug"])

        assert cache.get(cache_key) is None

    def test_is_active_update_invalidates_resolved_caches(
        self, purpose_binding: tuple
    ) -> None:
        """Regression: toggling is_active must still clear the cache
        (preserves the previously-gated behaviour)."""
        category, item = purpose_binding
        cache_key = _cache_key_for_purpose(category.id)

        assert cache.get(cache_key) is not None

        item.is_active = False
        item.save(update_fields=["is_active"])

        assert cache.get(cache_key) is None

    def test_lookup_item_delete_invalidates_resolved_caches(
        self, purpose_binding: tuple
    ) -> None:
        """Deleting a LookupItem must clear the resolved-purpose cache.

        The CASCADE deletion of the CategoryListingPurpose through-row
        triggers ``invalidate_category`` via the through-model's
        ``post_delete`` signal, which clears the RESOLVED_* keys.
        """
        category, item = purpose_binding
        cache_key = _cache_key_for_purpose(category.id)

        assert cache.get(cache_key) is not None

        item.delete()

        assert cache.get(cache_key) is None

    def test_cache_failure_does_not_rollback_save(
        self,
        purpose_binding: tuple,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Cache-backend failure must not roll back the DB save.

        Simulates a Redis outage by making ``cache.delete_pattern`` raise
        ``ConnectionInterrupted``. Both the categories and lookups signal
        handlers catch this exception (best-effort), so the ``LookupItem``
        save must still commit.
        """
        _category, item = purpose_binding

        # Prime the cache so delete_pattern would have work to do.
        CategoryLookupResolver.get_resolved_purposes(_category)

        failing_delete_pattern = Mock(
            side_effect=ConnectionInterrupted("Simulated Redis outage")
        )
        monkeypatch.setattr(
            cache, "delete_pattern", failing_delete_pattern, raising=False
        )

        item.name_i18n = {
            "ru": "Продам",
            "bs": "Prodam",
            "en": "Updated despite cache failure",
        }
        item.save(update_fields=["name_i18n"])

        # The DB row was committed — cache failure did not roll back the save.
        refreshed = LookupItem.objects.get(id=item.id)
        assert refreshed.name_i18n == {
            "ru": "Продам",
            "bs": "Prodam",
            "en": "Updated despite cache failure",
        }
