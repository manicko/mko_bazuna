"""
Integration tests for preferred-city read-back in search() and listings().

Verifies the hybrid-persistence *default* city filter (Spec_018):

search() (T-04):
- cookie-default for anonymous (AC-2)
- explicit ``?city=`` override (AC-3)
- DB wins over cookie for authenticated (AC-1)
- stale cookie fallthrough + cleanup (AC-4)

listings() (T-05):
- URL path ``/city/<slug>/`` overrides the preferred city (AC-3)
- default fallback to the preferred city (AC-2)
- explicit ``?city=`` prevents the preferred default (did-you-mean only)
"""

import pytest
from django.test import Client

from apps.ads.models import Ad
from apps.categories.models import Category
from apps.core.enums import AdStatus
from apps.locations.models import City
from apps.users.models import User

from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


@pytest.fixture
def buyer() -> User:
    """A registered buyer (for AC-1 DB-wins scenario)."""
    return User.objects.create(
        telegram_id=940000601,
        chat_id=940000601,
        password="y",
    )


@pytest.fixture
def podgorica() -> City:
    return City.objects.create(
        country_code="ME",
        name="Подгорица",
        region="Central",
        slug="podgorica",
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
def podgorica_ad(seller: User, category: Category, podgorica: City) -> Ad:
    return create_test_ad(seller, category, podgorica, status=AdStatus.PUBLISHED)


@pytest.fixture
def budva_ad(seller: User, category: Category, budva: City) -> Ad:
    return create_test_ad(seller, category, budva, status=AdStatus.PUBLISHED)


def _result_ids(response) -> list[int]:
    """Return the ids of ads rendered on the page."""
    return [ad.id for ad in response.context["page_obj"].object_list]


class TestSearchPreferredCityReadback:
    """search() applies the preferred city as a default filter (T-04)."""

    def test_cookie_default_filters_to_city(
        self, client: Client, podgorica_ad: Ad, budva_ad: Ad, podgorica: City
    ) -> None:
        """Anonymous cookie `podgorica` -> only Podgorica ads (AC-2)."""
        client.cookies["preferred_city"] = "podgorica"
        response = client.get("/search/?q=Велосипед")
        assert response.status_code == 200
        assert _result_ids(response) == [podgorica_ad.id]
        assert response.context["current_city"] == "podgorica"

    def test_explicit_city_override(
        self, client: Client, podgorica_ad: Ad, budva_ad: Ad
    ) -> None:
        """Explicit ?city=budva wins over the preferred default (AC-3)."""
        client.cookies["preferred_city"] = "podgorica"
        response = client.get("/search/?q=Велосипед&city=budva")
        assert response.status_code == 200
        assert _result_ids(response) == [budva_ad.id]
        assert response.context["current_city"] == "budva"

    def test_db_wins_over_cookie(
        self,
        client: Client,
        buyer: User,
        podgorica: City,
        podgorica_ad: Ad,
        budva_ad: Ad,
    ) -> None:
        """Authenticated DB preference wins over a conflicting cookie (AC-1)."""
        buyer.preferred_city = podgorica
        buyer.save(update_fields=["preferred_city"])
        client.force_login(buyer)
        client.cookies["preferred_city"] = "budva"

        response = client.get("/search/?q=Велосипед")
        assert response.status_code == 200
        assert _result_ids(response) == [podgorica_ad.id]

    def test_stale_cookie_fallthrough_and_cleared(
        self, client: Client, podgorica_ad: Ad, budva_ad: Ad
    ) -> None:
        """Stale cookie -> no city filter + cookie deleted (AC-4)."""
        client.cookies["preferred_city"] = "deleted-city"
        response = client.get("/search/?q=Велосипед")
        assert response.status_code == 200
        assert set(_result_ids(response)) == {podgorica_ad.id, budva_ad.id}
        # Stale cookie cleared in the response.
        assert response.cookies["preferred_city"].value == ""


class TestListingsPreferredCityReadback:
    """listings() applies the preferred city as a default filter (T-05)."""

    def test_path_city_overrides_preferred(
        self, client: Client, podgorica_ad: Ad, budva_ad: Ad
    ) -> None:
        """URL path /city/budva/ overrides the preferred default (AC-3)."""
        client.cookies["preferred_city"] = "podgorica"
        response = client.get("/city/budva/")
        assert response.status_code == 200
        assert _result_ids(response) == [budva_ad.id]
        assert response.context["current_city"] == "budva"

    def test_default_fallback_to_preferred_city(
        self, client: Client, podgorica_ad: Ad, budva_ad: Ad
    ) -> None:
        """Root catalog defaults to the preferred city (AC-2)."""
        client.cookies["preferred_city"] = "podgorica"
        response = client.get("/")
        assert response.status_code == 200
        assert _result_ids(response) == [podgorica_ad.id]
        assert response.context["current_city"] == "podgorica"

    def test_explicit_query_param_filters_to_city(
        self, client: Client, podgorica_ad: Ad, budva_ad: Ad
    ) -> None:
        """A valid ?city= param in listings is a real filter (F-5)."""
        client.cookies["preferred_city"] = "podgorica"
        response = client.get("/?city=budva")
        assert response.status_code == 200
        # ?city=budva filters to Budva, mirroring search() (no did-you-mean).
        assert _result_ids(response) == [budva_ad.id]
        assert response.context["current_city"] == "budva"
        assert response.context["suggested_city"] is None

    def test_invalid_query_param_suggests_only(
        self, client: Client, podgorica_ad: Ad, budva_ad: Ad
    ) -> None:
        """An invalid ?city= slug yields a did-you-mean banner and no filter (F-6)."""
        client.cookies["preferred_city"] = "podgorica"
        response = client.get("/?city=budv")
        assert response.status_code == 200
        # Invalid slug -> no filter (all ads shown, no city restriction) but a
        # did-you-mean suggestion is offered.
        assert set(_result_ids(response)) == {podgorica_ad.id, budva_ad.id}
        assert response.context["suggested_city"] is not None

    def test_pagination_with_explicit_city_matches_page_one(
        self,
        client: Client,
        seller: User,
        category: Category,
        podgorica: City,
        budva: City,
    ) -> None:
        """Page 2 with ?city=<preferred> keeps the same city filter (no divergence, AC-NEW-2)."""
        # Fill page 1 with Budva ads (plus a competing city) so page 2 is
        # non-empty and the city filter — not the all-ads fallthrough — decides
        # what page 2 shows. PER_PAGE is the view's constant 24.
        budva_ids: list[int] = []
        for _ in range(30):
            budva_ids.append(create_test_ad(seller, category, budva, status=AdStatus.PUBLISHED).id)
        for _ in range(30):
            create_test_ad(seller, category, podgorica, status=AdStatus.PUBLISHED)

        client.cookies["preferred_city"] = "budva"

        # Page 2 with an explicit ?city= stays Budva-filtered (no divergence).
        response = client.get("/?page=2&city=budva")
        assert response.status_code == 200
        assert response.context["current_city"] == "budva"
        results = _result_ids(response)
        assert results, "expected a non-empty page 2"
        assert all(ad_id in budva_ids for ad_id in results)

        # Page 2 with no ?city= falls back to the preferred city (Budva).
        response = client.get("/?page=2")
        assert response.status_code == 200
        assert response.context["current_city"] == "budva"
        results = _result_ids(response)
        assert results
        assert all(ad_id in budva_ids for ad_id in results)
