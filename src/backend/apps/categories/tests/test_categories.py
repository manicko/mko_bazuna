"""
Tests for category-tree cache invalidation (CAT-005).

Covers the tree-version fragment cache in ``apps.categories.cache``:
- get_tree_version() starts at 0 in a clean cache
- bump_tree_version() increments monotonically (cache.incr with set fallback)
- Category post_save fires bump_tree_version (structural change invalidates)
- Category post_delete fires bump_tree_version
- a cache outage during a structural change does not abort the save
  (best-effort bump, 08-SRCH-007)
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
import redis
from django_redis.exceptions import ConnectionInterrupted

from apps.categories.cache import bump_tree_version, get_tree_version
from apps.categories.models import Category

pytestmark = [pytest.mark.django_db]


# ---------------------------------------------------------------------------
# Cache primitives — pure cache operations (no DB writes)
# ---------------------------------------------------------------------------


class TestCategoryTreeVersionCache:
    """Tree-version cache: initial zero, monotonic increment, first-call fallback."""

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
# Signal wiring — structural Category changes invalidate the tree version
# ---------------------------------------------------------------------------


class TestCategoryStructureInvalidatesTreeVersion:
    """post_save / post_delete on Category bump the tree version (CAT-005)."""

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

    def test_cache_outage_does_not_roll_back_save(self) -> None:
        """A Category save commits even when the version bump raises."""
        with patch(
            "apps.categories.cache.bump_tree_version",
            side_effect=ConnectionInterrupted("Simulated Redis outage"),
        ):
            category = Category.objects.create(
                name="Тест-аутэйдж", slug="test-outage-cache"
            )

        # The save committed (the row is visible on a fresh query) and the
        # receiver did not re-raise out of post_save.
        assert Category.objects.filter(pk=category.pk).exists()

    def test_bare_redis_error_does_not_roll_back_save(self) -> None:
        """A bare ``redis.RedisError`` from the bump also leaves the save intact."""
        with patch(
            "apps.categories.cache.bump_tree_version",
            side_effect=redis.RedisError("redis down"),
        ):
            category = Category.objects.create(
                name="Тест-ошибка", slug="test-redis-error-cache"
            )

        assert Category.objects.filter(pk=category.pk).exists()
