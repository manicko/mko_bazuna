"""
Tests for the cached category fuzzy-match name list (SRH-005).

The search view's fuzzy category matcher previously loaded every active
category into Python memory (up to three times per fuzzy request). These tests
lock three guarantees of the fix:

1. **Equivalence** — ``_fuzzy_match_by_name`` returns the same category as the
   direct ``difflib.get_close_matches(query, all_names, n=1, cutoff=0.8)``
   result for a seeded set of active categories across locales (pass-by-
   construction, but pins the behavior).
2. **Invalidation** — renaming a category / toggling ``is_active`` bumps
   ``get_tree_version()`` and the next fuzzy call reflects the change via the
   versioned cache key.
3. **Query count** — the fuzzy path issues exactly one category SELECT on a
   cold cache (the cache-populating query) and zero on a warm cache.
"""

from __future__ import annotations

from difflib import get_close_matches

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.categories.cache import get_tree_version
from apps.categories.models import Category
from apps.core.enums import LanguageLocale
from apps.search.views.search import _fuzzy_category_match, _fuzzy_match_by_name

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def seeded_categories() -> list[Category]:
    """Seed active categories with localized names for ru/bs/en."""
    return [
        Category.objects.create(
            name="Велосипеды",
            slug="bicycles",
            name_i18n={"ru": "Велосипеды", "bs": "Bicikli", "en": "Bicycles"},
        ),
        Category.objects.create(
            name="Электроника",
            slug="electronics",
            name_i18n={"ru": "Электроника", "bs": "Elektronika", "en": "Electronics"},
        ),
        Category.objects.create(
            name="Одежда",
            slug="clothing",
            name_i18n={"ru": "Одежда", "bs": "Odjeća", "en": "Clothing"},
        ),
    ]


# (locale, query) pairs exercising exact name, near-miss typo, distant
# non-match, and empty inputs across all three supported locales.
_EQUIVALENCE_CASES: list[tuple[LanguageLocale, str]] = [
    (LanguageLocale.RUSSIAN, "Велосипеды"),  # exact
    (LanguageLocale.RUSSIAN, "Велосипед"),  # near-miss typo
    (LanguageLocale.RUSSIAN, "Абракадабра"),  # distant non-match
    (LanguageLocale.RUSSIAN, ""),  # empty
    (LanguageLocale.BOSNIAN, "Bicikli"),  # exact
    (LanguageLocale.BOSNIAN, "Bicikla"),  # near-miss typo
    (LanguageLocale.BOSNIAN, "Qwerty"),  # distant non-match
    (LanguageLocale.ENGLISH, "Bicycles"),  # exact
    (LanguageLocale.ENGLISH, "Bicycle"),  # near-miss typo
    (LanguageLocale.ENGLISH, "Zzzzz"),  # distant non-match
]


class TestFuzzyEquivalence:
    """Fuzzy matching stays byte-identical to direct difflib (SRH-005)."""

    @pytest.mark.parametrize("locale, query", _EQUIVALENCE_CASES)
    def test_fuzzy_match_by_name_equivalent_to_direct_difflib(
        self,
        seeded_categories: list[Category],
        locale: LanguageLocale,
        query: str,
    ) -> None:
        """``_fuzzy_match_by_name`` matches the direct difflib result exactly."""
        all_names = [c.get_name(locale.value) for c in seeded_categories]
        direct = get_close_matches(query, all_names, n=1, cutoff=0.8)

        result = _fuzzy_match_by_name(query, locale)

        if not direct:
            assert result is None
            return

        expected = next(
            c
            for c in seeded_categories
            if c.get_name(locale.value) == direct[0]
        )
        assert result is not None
        assert result.id == expected.id


class TestFuzzyInvalidation:
    """Category changes invalidate the cached name list via tree version."""

    def test_rename_bumps_tree_version_and_refreshes(
        self, seeded_categories: list[Category]
    ) -> None:
        """Renaming a localized name refreshes the cached list on next call."""
        locale = LanguageLocale.ENGLISH
        cat = seeded_categories[0]  # Bicycles

        assert _fuzzy_match_by_name("Bicycles", locale) is not None
        version_before = get_tree_version()

        # Rename to a value with no fuzzy affinity to the old localized name,
        # so the stale name reliably stops matching after invalidation.
        cat.name_i18n = {"ru": "Велосипеды", "bs": "Bicikli", "en": "Antiques"}
        cat.save(update_fields=["name_i18n"])

        assert get_tree_version() == version_before + 1
        assert _fuzzy_match_by_name("Bicycles", locale) is None
        assert _fuzzy_match_by_name("Antiques", locale) is not None

    def test_toggle_is_active_bumps_tree_version_and_refreshes(
        self, seeded_categories: list[Category]
    ) -> None:
        """Deactivating a category removes it from the refreshed name list."""
        locale = LanguageLocale.ENGLISH
        cat = seeded_categories[1]  # Electronics

        assert _fuzzy_match_by_name("Electronics", locale) is not None
        version_before = get_tree_version()

        cat.is_active = False
        cat.save(update_fields=["is_active"])

        assert get_tree_version() == version_before + 1
        assert _fuzzy_match_by_name("Electronics", locale) is None


class TestFuzzyQueryCount:
    """Fuzzy path avoids per-request full category loads (SRH-005)."""

    @staticmethod
    def _category_select_count(ctx: CaptureQueriesContext) -> int:
        return sum(
            1 for q in ctx.captured_queries if 'FROM "categories"' in q["sql"]
        )

    def test_cold_cache_issues_one_category_select(
        self, seeded_categories: list[Category]
    ) -> None:
        """A cold cache performs exactly one category SELECT (the populate)."""
        # A distant non-match so no category is resolved on the hit path.
        with CaptureQueriesContext(connection) as ctx:
            assert _fuzzy_match_by_name("Zzzznomatch", LanguageLocale.ENGLISH) is None
        assert self._category_select_count(ctx) == 1

    def test_warm_cache_issues_zero_category_selects(
        self, seeded_categories: list[Category]
    ) -> None:
        """A warm cache performs zero category SELECTs on the fuzzy path."""
        locale = LanguageLocale.ENGLISH
        # Warm the cache.
        _fuzzy_match_by_name("Zzzznomatch", locale)

        with CaptureQueriesContext(connection) as ctx:
            assert _fuzzy_match_by_name("Zzzznomatch", locale) is None
        assert self._category_select_count(ctx) == 0


class TestFuzzyCategoryMatch:
    """``_fuzzy_category_match`` preserves slug and exact-name behavior."""

    def test_slug_match(self, seeded_categories: list[Category]) -> None:
        """Slug exact match (case-insensitive) is unchanged."""
        result = _fuzzy_category_match("bicycles", LanguageLocale.ENGLISH)
        assert result is not None
        assert result.id == seeded_categories[0].id

    def test_exact_name_match_uses_cached_list(self) -> None:
        """Exact localized-name match resolves via the cached name list."""
        Category.objects.create(
            name="Книги",
            slug="books",
            name_i18n={"en": "Books for sale"},  # differs from the slug
        )
        # Not a slug, so this exercises the exact-name path over the cached list.
        result = _fuzzy_category_match("BOOKS FOR SALE", LanguageLocale.ENGLISH)
        assert result is not None
        assert result.name == "Книги"
