"""
Tests for the JSON cities endpoint (``GET /api/v1/cities/``).

Covers the S1.6 contract: city list shape (slug/name/localized name/region/
country_code), stable ``name`` ordering matching the header context processor's
city query, anonymous access (PUB read), and the RFC 9457 ``rate_limited`` 429
problem on budget exhaustion.
"""

from __future__ import annotations

import pytest
from django.test import Client

from apps.core.utils.problem import (
    PROBLEM_CONTENT_TYPE,
    RETRY_AFTER_HEADER,
    TYPE_RATE_LIMITED,
)
from apps.locations.models import City

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

ENDPOINT = "/api/v1/cities/"


@pytest.fixture
def cities() -> None:
    """Create a deterministic city set with names ordered differently by locale."""
    City.objects.create(
        country_code="ME",
        name="Budva",
        region="Coast",
        slug="budva",
        name_i18n={"ru": "Будва"},
    )
    City.objects.create(
        country_code="ME",
        name="Podgorica",
        region="Central",
        slug="podgorica",
        name_i18n={"ru": "Подгорица"},
    )
    City.objects.create(
        country_code="ME",
        name="Tivat",
        region="Coast",
        slug="tivat",
    )


class TestCitiesShape:
    """The JSON city list exposes the header city payload."""

    def test_anonymous_access_allowed(self, cities: None) -> None:
        response = Client().get(ENDPOINT)
        assert response.status_code == 200
        assert response.headers.get("Content-Type") == "application/json"

    def test_cities_ordered_by_name(self, cities: None) -> None:
        payload = Client().get(ENDPOINT).json()
        # Ordering is by the base ``name`` column (``order_by("name")``), the
        # exact ordering the header context processor applies.
        assert [city["slug"] for city in payload["cities"]] == [
            "budva",
            "podgorica",
            "tivat",
        ]

    def test_city_fields(self, cities: None) -> None:
        payload = Client().get(ENDPOINT).json()
        # ``tivat`` has no ``name_i18n``, so ``name`` falls back to the base
        # column regardless of the request locale.
        tivat = next(c for c in payload["cities"] if c["slug"] == "tivat")
        assert tivat == {
            "slug": "tivat",
            "name": "Tivat",
            "region": "Coast",
            "country_code": "ME",
        }

    def test_per_locale_name_resolution(self, cities: None) -> None:
        payload = Client().get(f"{ENDPOINT}?lang=ru").json()
        budva = next(c for c in payload["cities"] if c["slug"] == "budva")
        assert budva["name"] == "Будва"

    def test_matches_header_context_city_query(self, cities: None) -> None:
        """JSON cities equal the header's ``cities`` list (same set + order)."""
        from django.test import RequestFactory

        from apps.core.context_processors import header_context

        request = RequestFactory().get("/")
        request.LANGUAGE_CODE = "ru"
        html_cities = header_context(request)["cities"]

        payload = Client().get(f"{ENDPOINT}?lang=ru").json()
        assert [c["slug"] for c in payload["cities"]] == [
            city.slug for city in html_cities
        ]
        assert [c["name"] for c in payload["cities"]] == [
            city.get_name("ru") for city in html_cities
        ]


class TestRateLimitProblem:
    """Exhausting ``API_PUBLIC_READ`` yields an RFC 9457 429 problem."""

    def test_over_budget_returns_rate_limited_problem(
        self, cities: None, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            "apps.locations.api_cities.rate_limit_check",
            lambda *a, **k: False,
        )
        response = Client().get(ENDPOINT)

        assert response.status_code == 429
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        assert response.headers.get(RETRY_AFTER_HEADER) == "60"
        payload = response.json()
        assert payload["type"] == TYPE_RATE_LIMITED
        assert payload["status"] == 429
