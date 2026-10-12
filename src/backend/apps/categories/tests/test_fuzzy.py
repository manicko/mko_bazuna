"""Component-interaction tests for the shared category fuzzy ladder (10-CQ-011)."""

from __future__ import annotations

import pytest

from apps.ads.views.listings import _suggest_category
from apps.categories.models import Category
from apps.core.enums import LanguageLocale
from apps.search.views.search import _fuzzy_match_by_name

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestSharedCategoryFuzzyLadder:
    """Both category-fuzzy call sites resolve the same 0.8 cutoff."""

    @pytest.fixture
    def electronics(self) -> Category:
        return Category.objects.create(
            name="Electronics",
            slug="electronics",
            name_i18n={"ru": "Электроника", "bs": "Elektronika", "en": "Electronics"},
        )

    def test_between_cutoff_query_rejected_by_both_call_sites(
        self, electronics: Category
    ) -> None:
        """A ~0.78-ratio query is rejected: above the retired 0.6, below 0.8."""
        assert _suggest_category("electro") is None
        assert _fuzzy_match_by_name("electro", LanguageLocale.ENGLISH) is None

    def test_above_cutoff_query_matches_same_category_on_both_call_sites(
        self, electronics: Category
    ) -> None:
        """A ~0.95-ratio query matches on both sites (slug <-> same category)."""
        assert _suggest_category("electronic") == "electronics"
        result = _fuzzy_match_by_name("electronic", LanguageLocale.ENGLISH)
        assert result is not None
        assert result.id == electronics.id

    def test_name_ladder_accepts_above_cutoff_match_with_case_variance(
        self, electronics: Category
    ) -> None:
        """The name ladder accepts a match above the 0.8 cutoff despite case variance.

        ``get_close_matches`` is case-sensitive, so the slug ladder
        ("electro" vs "electronics" = 0.778) and the name ladder
        ("electro" vs "Electronics" = 0.667) diverge at the knife-edge
        ``electro`` query. This test asserts the name ladder does accept
        a clearly above-cutoff match ("Electronix" vs "Electronics" = 0.857)
        so the accept-path of the name ladder is covered beyond the
        all-lowercase "electronic" sample.
        """
        result = _fuzzy_match_by_name("Electronix", LanguageLocale.ENGLISH)
        assert result is not None
        assert result.id == electronics.id
