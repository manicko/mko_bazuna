"""
Tests for the shared city slug suggestion service.

Covers the ``suggest_city`` function used by the search and listings views
for the "Did you mean:" banner when an invalid ``?city=`` slug is passed.
"""

import pytest

from apps.locations.models import City
from apps.locations.services.city_suggestions import suggest_city

pytestmark = [pytest.mark.django_db, pytest.mark.unit]


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
