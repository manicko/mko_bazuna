"""
Tests for category-tree cache invalidation (CAT-005).

Covers the tree-version fragment cache in ``apps.categories.cache``:
- get_tree_version() starts at 0 in a clean cache
- bump_tree_version() increments monotonically (cache.incr with set fallback)
- Category post_save fires bump_tree_version (structural change invalidates)
- Category post_delete fires bump_tree_version
"""

from __future__ import annotations

import pytest

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
