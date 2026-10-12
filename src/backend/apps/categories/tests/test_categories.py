"""
Tests for category-tree cache invalidation (CAT-005).

Covers the tree-version fragment cache in ``apps.categories.cache``:
- get_tree_version() starts at 0 in a clean cache
- bump_tree_version() increments monotonically (cache.incr with set fallback)
- Category post_save fires bump_tree_version (structural change invalidates)
- Category post_delete fires bump_tree_version
- CategoryPath post_save / post_delete fires bump_tree_version
- a cache outage during a structural change does not abort the save
  (best-effort bump, 08-SRCH-007)
- lookup-resolution signal receivers invalidate caches on binding/lookup changes
- Category.get_name() fallback chain: locale -> ru -> name
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest
import redis
from django_redis.exceptions import ConnectionInterrupted

from apps.categories.cache import bump_tree_version, get_tree_version
from apps.categories.models import (
    Category,
    CategoryListingCondition,
    CategoryListingFeature,
    CategoryListingPurpose,
    CategoryPath,
)
from apps.categories.services.lookup_resolution import CategoryLookupResolver
from apps.core.enums import LanguageLocale
from apps.lookups.enums import LookupGroupCode
from apps.lookups.models import LookupGroup, LookupItem

# ---------------------------------------------------------------------------
# Cache primitives — pure cache operations (no DB writes)
# ---------------------------------------------------------------------------


class TestCategoryTreeVersionCache:
    """Tree-version cache: initial zero, monotonic increment, first-call fallback."""

    pytestmark = pytest.mark.unit

    def test_tree_version_starts_at_zero(self) -> None:
        """In a clean cache the tree version is 0 (never bumped)."""
        assert get_tree_version() == 0

    def test_bump_tree_version_increments(self) -> None:
        """Successive bumps increment the version monotonically.

        First call hits the ``ValueError`` fallback (cache.incr on a missing
        key) → ``cache.set(1)``; subsequent calls use ``cache.incr``.
        """
        assert get_tree_version() == 0

        bump_tree_version()
        assert get_tree_version() == 1

        bump_tree_version()
        assert get_tree_version() == 2

        bump_tree_version()
        assert get_tree_version() == 3


# ---------------------------------------------------------------------------
# Signal wiring — structural Category / CategoryPath changes invalidate tree version
# ---------------------------------------------------------------------------


class TestCategoryStructureInvalidatesTreeVersion:
    """post_save / post_delete on Category and CategoryPath bump tree version (CAT-005)."""

    pytestmark = [pytest.mark.django_db, pytest.mark.integration]

    def test_category_save_bumps_tree_version(self) -> None:
        """Creating a Category fires post_save → bump_tree_version."""
        assert get_tree_version() == 0

        Category.objects.create(name="Тест", slug="test-cache")

        assert get_tree_version() == 1

    def test_category_delete_bumps_tree_version(self) -> None:
        """Deleting a Category fires post_delete → bump_tree_version."""
        category = Category.objects.create(name="Тест", slug="test-delete-cache")
        # The create above already bumped the version via post_save.
        assert get_tree_version() == 1

        category.delete()

        assert get_tree_version() == 2

    def test_category_path_save_bumps_tree_version(self) -> None:
        """Creating a CategoryPath fires post_save -> bump_tree_version."""
        root = Category.objects.create(name="Parent", slug="test-cp-parent")
        child = Category.objects.create(name="Child", slug="test-cp-child")
        version_before = get_tree_version()

        CategoryPath.objects.create(category=child, parent=root)

        assert get_tree_version() == version_before + 1

    def test_category_path_delete_bumps_tree_version(self) -> None:
        """Deleting a CategoryPath fires post_delete -> bump_tree_version."""
        root = Category.objects.create(name="Parent", slug="test-cp-del-parent")
        child = Category.objects.create(name="Child", slug="test-cp-del-child")
        path = CategoryPath.objects.create(category=child, parent=root)
        version_before = get_tree_version()

        path.delete()

        assert get_tree_version() == version_before + 1


# ---------------------------------------------------------------------------
# Cache-outage safety — a failed bump must not abort the DB write (08-SRCH-007)
# ---------------------------------------------------------------------------


class TestCacheOutageDoesNotAbortCategorySave:
    """The tree-version bump is best-effort (08-SRCH-007).

    The defect this pins: ``bump_tree_version_on_structure_change`` called
    ``bump_tree_version()`` unguarded, so a Redis outage raised out of the
    ``post_save`` receiver and aborted the Category save — turning a cache
    outage into a write failure. The three sibling receivers already catch
    ``ConnectionInterrupted`` / ``redis.RedisError``; this receiver now does
    the same.
    """

    pytestmark = [pytest.mark.django_db, pytest.mark.integration]

    def test_cache_outage_does_not_roll_back_save(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A Category save commits even when the version bump raises."""
        caplog.set_level(logging.WARNING)
        with patch(
            "apps.categories.cache.bump_tree_version",
            side_effect=ConnectionInterrupted("Simulated Redis outage"),
        ):
            category = Category.objects.create(
                name="Test-outage", slug="test-outage-cache"
            )

        # The save committed (the row is visible on a fresh query) and the
        # receiver did not re-raise out of post_save.
        assert Category.objects.filter(pk=category.pk).exists()
        assert "Cache backend unavailable" in caplog.text

    def test_bare_redis_error_does_not_roll_back_save(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A bare ``redis.RedisError`` from the bump also leaves the save intact."""
        caplog.set_level(logging.WARNING)
        with patch(
            "apps.categories.cache.bump_tree_version",
            side_effect=redis.RedisError("redis down"),
        ):
            category = Category.objects.create(
                name="Test-redis-error", slug="test-redis-error-cache"
            )

        assert Category.objects.filter(pk=category.pk).exists()
        assert "Cache backend unavailable" in caplog.text


# ---------------------------------------------------------------------------
# Lookup-resolution signal receivers — invalidation on binding/lookup changes
# ---------------------------------------------------------------------------


class TestLookupSignalInvalidation:
    """Signal receivers invalidate resolved-lookup caches.

    Covers ``invalidate_category_lookup_cache`` (fires on through-table
    save/delete for CategoryListingPurpose / Feature / Condition) and
    ``invalidate_on_lookup_item_change`` (fires on LookupItem post_save).
    Both carry their own ``ConnectionInterrupted`` / ``redis.RedisError``
    try/except — the same 08-SRCH-007 fail-open contract as the tree-version
    receiver.
    """

    pytestmark = [pytest.mark.django_db, pytest.mark.integration]

    @pytest.fixture
    def purpose_item(self) -> LookupItem:
        """Create a LookupItem in the listing_purpose group."""
        group, _ = LookupGroup.objects.get_or_create(
            code=LookupGroupCode.LISTING_PURPOSE,
        )
        return LookupItem.objects.create(
            slug="test-purpose-sigs",
            group=group,
            name_i18n={"ru": "Test purpose"},
        )

    @pytest.fixture
    def feature_item(self) -> LookupItem:
        """Create a LookupItem in the listing_feature group."""
        group, _ = LookupGroup.objects.get_or_create(
            code=LookupGroupCode.LISTING_FEATURE,
        )
        return LookupItem.objects.create(
            slug="test-feature-sigs",
            group=group,
            name_i18n={"ru": "Test feature"},
        )

    @pytest.fixture
    def condition_item(self) -> LookupItem:
        """Create a LookupItem in the listing_condition group."""
        group, _ = LookupGroup.objects.get_or_create(
            code=LookupGroupCode.LISTING_CONDITION,
        )
        return LookupItem.objects.create(
            slug="test-condition-sigs",
            group=group,
            name_i18n={"ru": "Test condition"},
        )

    def test_purpose_save_invalidates_lookup_cache(
        self, category: Category, purpose_item: LookupItem
    ) -> None:
        """CategoryListingPurpose post_save fires invalidate_category."""
        with patch.object(
            CategoryLookupResolver, "invalidate_category"
        ) as mock_invalidate:
            purpose = CategoryListingPurpose.objects.create(
                category=category,
                listing_purpose=purpose_item,
            )
        mock_invalidate.assert_called_once_with(purpose.category_id)

    def test_purpose_delete_invalidates_lookup_cache(
        self, category: Category, purpose_item: LookupItem
    ) -> None:
        """CategoryListingPurpose post_delete fires invalidate_category."""
        purpose = CategoryListingPurpose.objects.create(
            category=category,
            listing_purpose=purpose_item,
        )
        with patch.object(
            CategoryLookupResolver, "invalidate_category"
        ) as mock_invalidate:
            purpose.delete()
        mock_invalidate.assert_called_once_with(purpose.category_id)

    def test_feature_save_invalidates_lookup_cache(
        self, category: Category, feature_item: LookupItem
    ) -> None:
        """CategoryListingFeature post_save fires invalidate_category."""
        with patch.object(
            CategoryLookupResolver, "invalidate_category"
        ) as mock_invalidate:
            feature = CategoryListingFeature.objects.create(
                category=category,
                feature=feature_item,
            )
        mock_invalidate.assert_called_once_with(feature.category_id)

    def test_condition_save_invalidates_lookup_cache(
        self, category: Category, condition_item: LookupItem
    ) -> None:
        """CategoryListingCondition post_save fires invalidate_category."""
        with patch.object(
            CategoryLookupResolver, "invalidate_category"
        ) as mock_invalidate:
            condition = CategoryListingCondition.objects.create(
                category=category,
                listing_condition=condition_item,
            )
        mock_invalidate.assert_called_once_with(condition.category_id)

    def test_lookup_item_save_invalidates_lookup_cache(
        self, purpose_item: LookupItem
    ) -> None:
        """LookupItem post_save fires invalidate_lookup_item."""
        with patch.object(
            CategoryLookupResolver, "invalidate_lookup_item"
        ) as mock_invalidate:
            purpose_item.name_i18n = {"ru": "Updated"}
            purpose_item.save()
        mock_invalidate.assert_called_once_with(purpose_item.id)

    def test_lookup_item_save_outage_does_not_roll_back(self) -> None:
        """A cache error during lookup-item invalidation does not abort the save (08-SRCH-007)."""
        group, _ = LookupGroup.objects.get_or_create(
            code=LookupGroupCode.LISTING_PURPOSE,
        )
        item = LookupItem.objects.create(
            slug="test-outage-item-sigs",
            group=group,
            name_i18n={"ru": "Test"},
        )
        with patch.object(
            CategoryLookupResolver,
            "invalidate_lookup_item",
            side_effect=ConnectionInterrupted("Simulated Redis outage"),
        ):
            item.name_i18n = {"ru": "Updated"}
            item.save()
        assert LookupItem.objects.filter(pk=item.pk).exists()


# ---------------------------------------------------------------------------
# Category.get_name fallback chain (models.py:54) — locale -> ru -> name
# ---------------------------------------------------------------------------


class TestCategoryGetNameFallback:
    """get_name fallback ordering: locale -> ru -> name."""

    pytestmark = pytest.mark.unit

    def test_fallback_chain_en_to_name_when_no_ru_or_en(self) -> None:
        """name_i18n={"bs":"X"} with locale en falls through ru to name."""
        cat = Category(
            name="BaseName",
            slug="test-fn-bs-sigs",
            name_i18n={"bs": "BSName"},
        )
        assert cat.get_name(LanguageLocale.ENGLISH) == "BaseName"

    def test_fallback_chain_en_to_ru_when_ru_present(self) -> None:
        """name_i18n={"ru":"RU"} with locale en falls back to ru."""
        cat = Category(
            name="BaseName",
            slug="test-fn-ru-sigs",
            name_i18n={"ru": "RUName"},
        )
        assert cat.get_name(LanguageLocale.ENGLISH) == "RUName"

    def test_fallback_chain_en_to_ru_skips_bs(self) -> None:
        """name_i18n={"bs":"BS","ru":"RU"} with locale en returns ru, not bs."""
        cat = Category(
            name="BaseName",
            slug="test-fn-full-sigs",
            name_i18n={"bs": "BSName", "ru": "RUName"},
        )
        assert cat.get_name(LanguageLocale.ENGLISH) == "RUName"
