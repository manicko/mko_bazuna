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
from django.utils import timezone

from apps.ads.models import Ad
from apps.categories.models import Category
from apps.core.enums import AdStatus
from apps.locations.models import City
from apps.users.models import User

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


@pytest.fixture
def seller() -> User:
    """A seller user who owns published ads."""
    return User.objects.create(
        telegram_id=940000600,
        chat_id=940000600,
        password="x",
    )


@pytest.fixture
def buyer() -> User:
    """A registered buyer (for AC-1 DB-wins scenario)."""
    return User.objects.create(
        telegram_id=940000601,
        chat_id=940000601,
        password="y",
    )


@pytest.fixture
def category() -> Category:
    return Category.objects.create(name="Транспорт", slug="transport")


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


def _published_ad(seller: User, category: Category, city: City, **kwargs) -> Ad:
    defaults = {
        "user": seller,
        "title": "Велосипед",
        "category": category,
        "city": city,
        "category_name": category.name,
        "status": AdStatus.PUBLISHED,
        "published_at": timezone.now(),
    }
    defaults.update(kwargs)
    return Ad.objects.create(**defaults)


@pytest.fixture
def podgorica_ad(seller: User, category: Category, podgorica: City) -> Ad:
    return _published_ad(seller, category, podgorica)


@pytest.fixture
def budva_ad(seller: User, category: Category, budva: City) -> Ad:
    return _published_ad(seller, category, budva)


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

    def test_explicit_query_param_prevents_preferred_default(
        self, client: Client, podgorica_ad: Ad, budva_ad: Ad
    ) -> None:
        """A ?city= param in listings disables the preferred default (did-you-mean only)."""
        client.cookies["preferred_city"] = "podgorica"
        response = client.get("/?city=budva")
        assert response.status_code == 200
        # ?city= drives did-you-mean only (no filter); the preferred default is
        # NOT applied, so both ads appear.
        assert set(_result_ids(response)) == {podgorica_ad.id, budva_ad.id}
        assert response.context["suggested_city"] == "budva"
        assert response.context["current_city"] is None
