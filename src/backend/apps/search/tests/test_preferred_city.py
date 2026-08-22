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
from apps.categories.models import Category
from apps.core.enums import AdStatus
from apps.locations.models import City
from apps.users.models import User
from django.test import Client

from apps.core.middleware.preferred_city import PREFERRED_CITY_COOKIE_MAX_AGE

from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


@pytest.fixture
def buyer() -> User:
    """Create an authenticated buyer."""
    return User.objects.create(
        telegram_id=930000501,
        chat_id=930000501,
        password="y",
    )


@pytest.fixture
def budva() -> City:
    return City.objects.create(
        country_code="ME",
        name="Будва",
        region="Coastal",
        slug="budva",
    )


@pytest.fixture
def podgorica() -> City:
    return City.objects.create(
        country_code="ME",
        name="Подгорица",
        region="Central",
        slug="podgorica",
    )


class TestPreferredCityView:
    """Preferred-city view contract."""

    def test_post_with_valid_slug_sets_cookie(self, podgorica: City) -> None:
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

    def test_post_without_preferences_consent_sets_no_cookie(self, podgorica: City) -> None:
        """Without preferences consent the cookie is NOT set (T-06c / ePrivacy)."""
        client = Client()
        response = client.post("/api/preferred-city/", {"slug": "podgorica"})
        assert response.status_code == 200
        assert response.json() == {"ok": True}
        assert "preferred_city" not in response.cookies

    def test_post_with_valid_slug_persists_db_for_authenticated(
        self, podgorica: City, buyer: User
    ) -> None:
        """Authenticated user selection persists ``User.preferred_city`` (R-11)."""
        client = Client()
        client.force_login(buyer)
        assert buyer.preferred_city_id is None

        response = client.post("/api/preferred-city/", {"slug": "podgorica"})
        assert response.status_code == 200
        assert response.json() == {"ok": True}

        buyer.refresh_from_db()
        assert buyer.preferred_city_id == podgorica.id

    def test_post_with_valid_slug_cookie_only_for_anonymous(self, podgorica: City) -> None:
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

    def test_header_renders_badge_with_preferred_city(self, podgorica: City) -> None:
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
        # Dropdown exposes the "whole country" reset head-item (F-3 / T-02).
        assert "data-city-clear" in content
        assert "Вся страна" in content

    def test_header_renders_country_wide_label_when_unset(self) -> None:
        """Without a preference the badge shows the country-wide label."""
        client = Client()
        response = client.get("/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "Вся страна" in content


class TestReset:
    """Preferred-city reset (clear) contract (Spec_23 T5 / AC-5*, AC-8, AC-NEW-1)."""

    def test_clear_deletes_cookie_and_returns_all_cities_anonymous(
        self, seller: User, category: Category, city: City, budva: City
    ) -> None:
        """A clear for an anonymous buyer deletes the cookie; / then returns all-cities."""
        podgorica_ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        budva_ad = create_test_ad(seller, category, budva, status=AdStatus.PUBLISHED)

        # Establish a preference via the cookie, then clear it.
        client = Client()
        client.cookies["preferred_city"] = "budva"

        response = client.post("/api/preferred-city/", {"action": "clear"})
        assert response.status_code == 200
        assert response.json() == {"ok": True}
        # delete_cookie schedules the cookie for deletion (R-3 observable here).
        assert response.cookies["preferred_city"].value == ""

        # A fresh request sees no preference -> all-cities results + country badge.
        # (The browser no longer sends the cleared preferred_city cookie.)
        fresh = Client()
        list_response = fresh.get("/")
        assert list_response.status_code == 200
        assert {ad.id for ad in list_response.context["page_obj"].object_list} == {
            podgorica_ad.id,
            budva_ad.id,
        }
        content = list_response.content.decode()
        assert "Вся страна" in content

    def test_clear_nulls_fk_and_returns_all_cities_authenticated(
        self,
        client: Client,
        buyer: User,
        seller: User,
        category: Category,
        city: City,
        budva: City,
    ) -> None:
        """A clear for an authenticated buyer NULLs User.preferred_city (F-1/F-4)."""
        podgorica_ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        budva_ad = create_test_ad(seller, category, budva, status=AdStatus.PUBLISHED)

        buyer.preferred_city = city
        buyer.save(update_fields=["preferred_city"])
        client.force_login(buyer)
        client.cookies["preferred_city"] = "budva"

        response = client.post("/api/preferred-city/", {"action": "clear"})
        assert response.status_code == 200
        assert response.json() == {"ok": True}

        buyer.refresh_from_db()
        assert buyer.preferred_city_id is None

        # A fresh request falls back to all-cities (no cookie, no DB preference).
        fresh = Client()
        fresh.force_login(buyer)
        list_response = fresh.get("/")
        assert list_response.status_code == 200
        assert {ad.id for ad in list_response.context["page_obj"].object_list} == {
            podgorica_ad.id,
            budva_ad.id,
        }

    def test_clear_with_empty_slug_equivalent_to_action_clear(self) -> None:
        """A present-but-empty slug signals clear intent (D-P1)."""
        client = Client()
        response = client.post("/api/preferred-city/", {"slug": ""})
        assert response.status_code == 200
        assert response.json() == {"ok": True}
        assert response.cookies["preferred_city"].value == ""
