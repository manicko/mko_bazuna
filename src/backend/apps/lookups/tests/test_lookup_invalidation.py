"""
Tests for LookupItem cache invalidation correctness (13-PERF-002/003/006).

Verifies that RESOLVED_* caches (``lookup:v1:resolve:{version}:purposes``,
``lookup:v1:resolve:{version}:features``, ``lookup:v1:resolve:{version}:conditions``)
are properly invalidated when a LookupItem changes — including name-only and
slug-only updates that previously hit the ``is_active``-only gate and were
silently skipped.

With the version-bump invalidation strategy, "invalidation" means the content
version is incremented (via signal handler → ``bump_lookup_resolve_version``),
making old cache entries unreachable. Old entries expire via TTL; no global
prefix wipe is used.

Also confirms that cache backend failures must never roll back the
originating DB save (best-effort invalidation).
"""

from unittest.mock import Mock

import pytest
from django.core.cache import cache
from django_redis.exceptions import ConnectionInterrupted

from apps.categories.models import CategoryListingPurpose
from apps.categories.services.lookup_resolution import (
    CategoryLookupResolver,
    get_lookup_resolve_version,
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

    # Prime the cache so we can assert it is invalidated afterwards.
    CategoryLookupResolver.get_resolved_purposes(category)
    return category, item


class TestLookupItemCacheInvalidation:
    """RESOLVED_* cache invalidation on LookupItem changes.

    With version-bump, invalidation is verified by checking that
    ``get_lookup_resolve_version()`` increased after the data change.
    """

    def test_name_only_update_bumps_resolve_version(
        self, purpose_binding: tuple
    ) -> None:
        """A name_i18n-only save must bump the resolve version."""
        category, item = purpose_binding
        version_before = get_lookup_resolve_version()

        item.name_i18n = {"ru": "Продам", "bs": "Prodam", "en": "Sell — updated"}
        item.save(update_fields=["name_i18n"])

        version_after = get_lookup_resolve_version()
        assert version_after > version_before

    def test_slug_only_update_bumps_resolve_version(
        self, purpose_binding: tuple
    ) -> None:
        """A slug-only save must bump the resolve version."""
        category, item = purpose_binding
        version_before = get_lookup_resolve_version()

        item.slug = "sell-updated"
        item.save(update_fields=["slug"])

        version_after = get_lookup_resolve_version()
        assert version_after > version_before

    def test_is_active_update_bumps_resolve_version(
        self, purpose_binding: tuple
    ) -> None:
        """Regression: toggling is_active must still bump the version."""
        category, item = purpose_binding
        version_before = get_lookup_resolve_version()

        item.is_active = False
        item.save(update_fields=["is_active"])

        version_after = get_lookup_resolve_version()
        assert version_after > version_before

    def test_lookup_item_delete_bumps_resolve_version(
        self, purpose_binding: tuple
    ) -> None:
        """Deleting a LookupItem must bump the resolve version.

        The CASCADE deletion of the CategoryListingPurpose through-row
        triggers ``invalidate_category_lookup_cache`` via the through-model's
        ``post_delete`` signal, which bumps the resolve version.
        """
        category, item = purpose_binding
        version_before = get_lookup_resolve_version()

        item.delete()

        version_after = get_lookup_resolve_version()
        assert version_after > version_before

    def test_name_only_update_serves_fresh_data(
        self, purpose_binding: tuple
    ) -> None:
        """After a name-only update, the next read returns the fresh data."""
        category, item = purpose_binding

        # Prime cache — returns the item with original name
        purposes = CategoryLookupResolver.get_resolved_purposes(category)
        assert len(purposes) == 1
        assert purposes[0].name_i18n["en"] == "Sell"

        # Update the name
        item.name_i18n = {"ru": "Продам", "bs": "Prodam", "en": "Sell Updated"}
        item.save(update_fields=["name_i18n"])

        # Next read — version bumped, cold miss, recomputes with fresh data
        purposes_after = CategoryLookupResolver.get_resolved_purposes(category)
        assert len(purposes_after) == 1
        assert purposes_after[0].name_i18n["en"] == "Sell Updated"

    def test_cache_failure_does_not_rollback_save(
        self,
        purpose_binding: tuple,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Cache-backend failure must not roll back the DB save.

        Simulates a Redis outage by making ``cache.incr`` raise
        ``ConnectionInterrupted``. The signal handler catches this exception
        (best-effort), so the ``LookupItem`` save must still commit.
        """
        category, item = purpose_binding

        # Prime the cache so the version key exists.
        CategoryLookupResolver.get_resolved_purposes(category)

        failing_incr = Mock(
            side_effect=ConnectionInterrupted("Simulated Redis outage")
        )
        monkeypatch.setattr(cache, "incr", failing_incr, raising=False)

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
