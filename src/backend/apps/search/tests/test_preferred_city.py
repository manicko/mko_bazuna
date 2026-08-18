"""
Tests for the preferred-city cookie endpoint (plan 15, T-700).

Covers the cookie-only preferred-city persistence (Decision 018):
- a POST with a valid city slug sets the ``preferred_city`` cookie (30-day)
- a POST with an unknown or missing slug returns 400
- a GET returns 405 (POST-only)
"""

import pytest
from apps.locations.models import City
from django.test import Client

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


@pytest.fixture
def city() -> City:
    """Create a city for preferred-city persistence tests."""
    return City.objects.create(
        country_code="ME",
        name="Подгорица",
        region="Central",
        slug="podgorica",
    )


class TestPreferredCityView:
    """Preferred-city cookie view contract."""

    def test_post_with_valid_slug_sets_cookie(self, city: City) -> None:
        client = Client()
        response = client.post("/api/preferred-city/", {"slug": "podgorica"})
        assert response.status_code == 200
        assert response.json() == {"ok": True}
        assert response.cookies["preferred_city"].value == "podgorica"

    def test_post_with_unknown_slug_returns_400(self) -> None:
        client = Client()
        response = client.post("/api/preferred-city/", {"slug": "nowhere"})
        assert response.status_code == 400

    def test_post_with_missing_slug_returns_400(self) -> None:
        client = Client()
        response = client.post("/api/preferred-city/", {})
        assert response.status_code == 400

    def test_get_returns_405(self) -> None:
        client = Client()
        assert client.get("/api/preferred-city/").status_code == 405
