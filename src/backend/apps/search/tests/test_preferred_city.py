"""
Tests for the preferred-city persistence endpoint.

Covers the hybrid preferred-city write side (cookie + DB for authenticated
buyers):
- a POST with a valid city slug sets the ``preferred_city`` cookie (1-year,
  HttpOnly, SameSite=Lax) for guests
- a POST with a valid slug for an authenticated user persists
  ``User.preferred_city``
- a POST with an unknown or missing slug returns 400
- a GET returns 405 (POST-only)
"""

import pytest
from apps.locations.models import City
from apps.users.models import User
from django.test import Client

from apps.core.middleware.preferred_city import PREFERRED_CITY_COOKIE_MAX_AGE

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


@pytest.fixture
def buyer() -> User:
    """Create an authenticated buyer."""
    return User.objects.create(
        telegram_id=930000501,
        chat_id=930000501,
        password="y",
    )


class TestPreferredCityView:
    """Preferred-city view contract."""

    def test_post_with_valid_slug_sets_cookie(self, city: City) -> None:
        """A consented visitor's selection is persisted as a cookie."""
        client = Client()
        client.cookies["consent_preferences"] = "true"
        response = client.post("/api/preferred-city/", {"slug": "podgorica"})
        assert response.status_code == 200
        assert response.json() == {"ok": True}
        cookie = response.cookies["preferred_city"]
        assert cookie.value == "podgorica"
        # 1-year max-age per Decision 018 (replaces the old 30-day cookie).
        assert int(cookie["max-age"]) == PREFERRED_CITY_COOKIE_MAX_AGE
        assert cookie["httponly"] is True
        assert cookie["samesite"] == "Lax"

    def test_post_without_preferences_consent_sets_no_cookie(self, city: City) -> None:
        """Without preferences consent the cookie is NOT set (T-06c / ePrivacy)."""
        client = Client()
        response = client.post("/api/preferred-city/", {"slug": "podgorica"})
        assert response.status_code == 200
        assert response.json() == {"ok": True}
        assert "preferred_city" not in response.cookies

    def test_post_with_valid_slug_persists_db_for_authenticated(
        self, city: City, buyer: User
    ) -> None:
        """Authenticated user selection persists ``User.preferred_city`` (R-11)."""
        client = Client()
        client.force_login(buyer)
        assert buyer.preferred_city_id is None

        response = client.post("/api/preferred-city/", {"slug": "podgorica"})
        assert response.status_code == 200
        assert response.json() == {"ok": True}

        buyer.refresh_from_db()
        assert buyer.preferred_city_id == city.id

    def test_post_with_valid_slug_cookie_only_for_anonymous(self, city: City) -> None:
        """A consented anonymous selection sets the cookie only (no DB write)."""
        client = Client()
        client.cookies["consent_preferences"] = "true"
        response = client.post("/api/preferred-city/", {"slug": "podgorica"})
        assert response.status_code == 200
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


class TestHeaderCityBadge:
    """Header city badge rendering (AC-8)."""

    def test_header_renders_badge_with_preferred_city(self, city: City) -> None:
        """A resolved preferred city renders in the header badge + dropdown."""
        client = Client()
        client.cookies["preferred_city"] = "podgorica"

        response = client.get("/")
        assert response.status_code == 200
        content = response.content.decode()
        # Badge shows the localized city name.
        assert "📍" in content
        assert "Подгорица" in content
        # Dropdown lists the city as a selectable option.
        assert 'data-city-option="podgorica"' in content

    def test_header_renders_country_wide_label_when_unset(self) -> None:
        """Without a preference the badge shows the country-wide label."""
        client = Client()
        response = client.get("/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "Вся страна" in content
