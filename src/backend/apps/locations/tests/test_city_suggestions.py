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
def other_city() -> City:
    """Create a second city to test multi-city matching."""
    return City.objects.create(
        country_code="RU",
        name="Москва",
        region="Central",
        slug="moscow",
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
    """Unit tests for ``suggest_city``."""

    def test_returns_close_match_for_typo(self, real_city: City) -> None:
        """A typo of a real slug returns the correct city slug."""
        result = suggest_city("budav")
        assert result == "budva"

    def test_returns_none_for_no_match(self, real_city: City, other_city: City) -> None:
        """A completely unrelated slug returns None."""
        result = suggest_city("xyznonexistent")
        assert result is None

    def test_returns_none_for_empty_slug(self, real_city: City) -> None:
        """An empty/blank slug returns None (no match)."""
        assert suggest_city("") is None
        assert suggest_city("   ") is None

    def test_prefers_closer_match(self, real_city: City, other_city: City) -> None:
        """When multiple close matches exist, the closest one wins."""
        # "budav" is closer to "budva" than to "moscow"
        result = suggest_city("budav")
        assert result == "budva"

    def test_returns_none_when_no_cities_exist(self) -> None:
        """With zero cities in the DB, any slug returns None."""
        assert suggest_city("anything") is None

    def test_below_cutoff_query_is_rejected(self, podgorica_city: City) -> None:
        """A query below the fuzzy cutoff does not resolve to a suggestion."""
        # SequenceMatcher("xyznotacity", "podgorica") == 0.2000 -- well below.
        assert suggest_city("xyznotacity") is None

    def test_in_band_query_resolves(self, podgorica_city: City) -> None:
        """A query whose ratio lies in-band (0.6 < ratio < 0.8) resolves."""
        # SequenceMatcher("podgo", "podgorica") == 0.7143 -- in (0.6, 0.8).
        assert suggest_city("podgo") == "podgorica"

    def test_above_cutoff_query_resolves(self, podgorica_city: City) -> None:
        """A query above the cutoff resolves to the closest slug."""
        # SequenceMatcher("Podgoric", "Podgorica") == 0.9412 -- above.
        assert suggest_city("Podgoric") == "podgorica"
