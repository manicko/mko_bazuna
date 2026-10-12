"""
Tests for the shared city slug suggestion service.

Covers the ``suggest_city`` function used by the search and listings views
for the "Did you mean:" banner when an invalid ``?city=`` slug is passed.
"""

import pytest

from apps.locations.models import City
from apps.locations.services.city_suggestions import suggest_city

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def real_city() -> City:
    """Create a city with a slug resembling a known Montenegrin city."""
    return City.objects.create(
        country_code="ME",
        name="Будва",
        region="Balkans",
        slug="budva",
    )


@pytest.fixture
def podgorica_city() -> City:
    """Create Podgorica so an in-band typo resolves against it."""
    return City.objects.create(
        country_code="ME",
        name="Подгорица",
        region="Balkans",
        slug="podgorica",
    )


class TestSuggestCity:
    """Integration tests for ``suggest_city``."""

    def test_returns_close_match_for_typo(self, real_city: City) -> None:
        """A typo of a real slug returns the correct city slug."""
        result = suggest_city("budav")
        assert result == "budva"

    def test_returns_none_for_empty_slug(self, real_city: City) -> None:
        """An empty/blank slug returns None (no match)."""
        assert suggest_city("") is None
        assert suggest_city("   ") is None

    def test_returns_none_when_no_cities_exist(self) -> None:
        """With zero cities in the DB, any slug returns None."""
        assert suggest_city("anything") is None

    def test_below_cutoff_query_is_rejected(self, podgorica_city: City) -> None:
        """A query below the fuzzy cutoff does not resolve to a suggestion."""
        # "xyznotacity" is well below the CITY_FUZZY_CUTOFF (0.6) threshold.
        assert suggest_city("xyznotacity") is None

    def test_in_band_query_resolves(self, podgorica_city: City) -> None:
        """A partial query above the cutoff resolves to the closest slug."""
        # "podgo" is above the CITY_FUZZY_CUTOFF (0.6) threshold.
        assert suggest_city("podgo") == "podgorica"

    def test_above_cutoff_query_resolves(self, podgorica_city: City) -> None:
        """A near-miss query above the cutoff resolves to the closest slug."""
        # "Podgoric" is above the CITY_FUZZY_CUTOFF (0.6) threshold. The actual
        # comparison is against the lowercase slug "podgorica" (ratio ≈ 0.8235),
        # not the capitalized "Podgorica" (ratio 0.9412) that get_close_matches
        # does not see.
        assert suggest_city("Podgoric") == "podgorica"

    def test_tier1_exact_case_insensitive_match(self, podgorica_city: City) -> None:
        """An exact slug match ignoring case returns immediately via Tier 1.

        "PODGORICA" casefolds to "podgorica", matching the stored slug exactly,
        so ``match_city`` returns before ``get_close_matches`` (Tier 2) is
        invoked.
        """
        assert suggest_city("PODGORICA") == "podgorica"
