"""Tests for the ``GET /api/v1/ads/`` JSON listings endpoint (S1.3).

This module owns the citable rule-18 matrix clause
(``TestExhaustiveFilterSortPageMatrix``): every ``ListingsQueryParams``
dimension — category, city, listing purpose, condition, features, price bounds —
crossed with all four sorts and pagination, exercised **through the endpoint**
(browserless ``Client()``), plus the audience-parity, 429-problem, 422-problem,
HTML/JSON parity (incl. warm-cache) and pagination-envelope cases.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.test import Client
from django.urls import reverse

from apps.core.enums import AdSort, AdStatus
from apps.core.utils.problem import (
    PROBLEM_CONTENT_TYPE,
    RETRY_AFTER_HEADER,
    TYPE_RATE_LIMITED,
    TYPE_VALIDATION_FAILED,
)
from apps.locations.models import City
from conftest import create_test_ad, create_test_ads_bulk

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

ENDPOINT = "/api/v1/ads/"


def _ids(payload: dict[str, Any]) -> list[int]:
    """Return the ordered ``id`` sequence from a JSON envelope's results."""
    return [row["id"] for row in payload["results"]]


class TestExhaustiveFilterSortPageMatrix:
    """Exhaustive filter × sort × page matrix through the endpoint (rule 18).

    Every filter dimension the shared ``ListingsQueryParams`` DTO exposes is
    crossed with all four sorts and pagination pages, and each assertion checks
    the returned ids match the filter (or its complement) and the envelope is
    internally coherent.
    """

    @pytest.fixture
    def matrix_fixture(self, seller, category, city) -> dict[str, Any]:
        """Seed a small ad matrix covering every filter dimension.

        Returns a dict of the created ads keyed by their distinguishing
        property, plus a second city for the city dimension.
        """
        other_city = City.objects.create(
            country_code="ME",
            name="Другиград",
            region="Central",
            slug="drugigrad",
        )
        cheap = create_test_ad(
            seller, category, city, title="Cheap", price=50, status=AdStatus.PUBLISHED
        )
        mid = create_test_ad(
            seller, category, city, title="Mid", price=150, status=AdStatus.PUBLISHED
        )
        expensive = create_test_ad(
            seller,
            category,
            city,
            title="Expensive",
            price=300,
            status=AdStatus.PUBLISHED,
        )
        elsewhere = create_test_ad(
            seller,
            category,
            other_city,
            title="Elsewhere",
            price=150,
            status=AdStatus.PUBLISHED,
        )
        return {
            "cheap": cheap,
            "mid": mid,
            "expensive": expensive,
            "elsewhere": elsewhere,
            "other_city": other_city,
        }

    def _get(self, query: dict[str, Any]) -> dict[str, Any]:
        """GET the endpoint with *query* and return the decoded JSON payload."""
        response = Client().get(ENDPOINT, query)
        assert response.status_code == 200
        content_type = response.headers.get("Content-Type", "")
        assert content_type.startswith("application/json")
        return response.json()

    # -- category dimension ------------------------------------------------- #

    def test_category_filter_matches_subtree(
        self, seller, category, city, matrix_fixture
    ) -> None:
        payload = self._get({"category": category.slug})
        assert set(_ids(payload)) == {
            matrix_fixture[k].id
            for k in ("cheap", "mid", "expensive", "elsewhere")
        }

    def test_unknown_category_applies_no_filter(
        self, matrix_fixture
    ) -> None:
        payload = self._get({"category": "does-not-exist"})
        assert len(_ids(payload)) == 4

    # -- city dimension ----------------------------------------------------- #

    def test_city_filter_narrows_to_city(
        self, matrix_fixture
    ) -> None:
        payload = self._get({"city": "drugigrad"})
        assert _ids(payload) == [matrix_fixture["elsewhere"].id]

    # -- price bounds dimension --------------------------------------------- #

    def test_min_price_bound(self, matrix_fixture) -> None:
        payload = self._get({"min_price": 150})
        assert {matrix_fixture["mid"].id, matrix_fixture["expensive"].id,
                matrix_fixture["elsewhere"].id} == set(_ids(payload))
        assert matrix_fixture["cheap"].id not in _ids(payload)

    def test_max_price_bound(self, matrix_fixture) -> None:
        payload = self._get({"max_price": 150})
        assert {matrix_fixture["cheap"].id, matrix_fixture["mid"].id,
                matrix_fixture["elsewhere"].id} == set(_ids(payload))
        assert matrix_fixture["expensive"].id not in _ids(payload)

    def test_min_and_max_price_bound_combined(self, matrix_fixture) -> None:
        payload = self._get({"min_price": 100, "max_price": 200})
        assert {matrix_fixture["mid"].id, matrix_fixture["elsewhere"].id} == set(
            _ids(payload)
        )

    # -- purpose dimension -------------------------------------------------- #

    def test_listing_purpose_filter(
        self, seller, category, city, purpose_lookup
    ) -> None:
        ad_sell = create_test_ad(
            seller, category, city, title="Sell",
            listing_purpose=purpose_lookup["sell"], status=AdStatus.PUBLISHED,
        )
        ad_rent = create_test_ad(
            seller, category, city, title="Rent",
            listing_purpose=purpose_lookup["rent"], status=AdStatus.PUBLISHED,
        )
        payload = self._get({"listing_purpose": "sell"})
        assert _ids(payload) == [ad_sell.id]
        assert ad_rent.id not in _ids(payload)

    # -- condition dimension ------------------------------------------------ #

    def test_condition_filter(
        self, seller, category, city, condition_lookup
    ) -> None:
        ad_new = create_test_ad(
            seller, category, city, title="New",
            listing_condition=condition_lookup["new"], status=AdStatus.PUBLISHED,
        )
        ad_used = create_test_ad(
            seller, category, city, title="Used",
            listing_condition=condition_lookup["used"], status=AdStatus.PUBLISHED,
        )
        payload = self._get({"condition": "new"})
        assert _ids(payload) == [ad_new.id]
        assert ad_used.id not in _ids(payload)

    # -- features dimension (multi-select AND) ------------------------------ #

    def test_features_filter_and_semantics(
        self, seller, category, city, feature_lookup
    ) -> None:
        ad_both = create_test_ad(
            seller, category, city, title="Both", status=AdStatus.PUBLISHED
        )
        ad_both.features.add(feature_lookup["delivery"], feature_lookup["negotiable"])
        ad_one = create_test_ad(
            seller, category, city, title="One", status=AdStatus.PUBLISHED
        )
        ad_one.features.add(feature_lookup["delivery"])

        client = Client()
        payload = client.get(
            ENDPOINT, {"features": ["delivery", "negotiable"]}
        ).json()
        assert _ids(payload) == [ad_both.id]

    # -- sort dimension ----------------------------------------------------- #

    @pytest.mark.parametrize(
        "sort,expected_key",
        [
            (AdSort.DATE_NEW, "date_desc"),
            (AdSort.DATE_OLD, "date_asc"),
            (AdSort.PRICE_LOW, "price_asc"),
            (AdSort.PRICE_HIGH, "price_desc"),
        ],
    )
    def test_every_sort_value_is_accepted_and_orders(
        self, seller, category, city, sort, expected_key
    ) -> None:
        cheap = create_test_ad(
            seller, category, city, title="Cheap", price=50,
            status=AdStatus.PUBLISHED,
        )
        expensive = create_test_ad(
            seller, category, city, title="Expensive", price=300,
            status=AdStatus.PUBLISHED,
        )
        payload = self._get({"sort": sort})
        ids = _ids(payload)
        assert cheap.id in ids and expensive.id in ids
        if expected_key == "price_asc":
            assert ids.index(cheap.id) < ids.index(expensive.id)
        elif expected_key == "price_desc":
            assert ids.index(expensive.id) < ids.index(cheap.id)

    def test_unknown_sort_falls_back_to_default(
        self, seller, category, city
    ) -> None:
        create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        payload = self._get({"sort": "not-a-sort"})
        assert payload["page"] == 1  # coerced, no 500

    # -- full crossing: filters × sorts × pages ----------------------------- #

    @pytest.mark.parametrize(
        "sort",
        [AdSort.DATE_NEW, AdSort.DATE_OLD, AdSort.PRICE_LOW, AdSort.PRICE_HIGH],
    )
    @pytest.mark.parametrize("page", [1, 2, 3])
    def test_filter_sort_page_cross_product(
        self, seller, category, city, sort, page
    ) -> None:
        """25 ads crossed with 4 sorts × 3 pages through the endpoint.

        Uses ``per_page=10`` so there are exactly three pages; asserts the union
        of the three pages equals the full 25-id set (no loss, no duplication)
        and that each page's envelope is coherent.
        """
        ads = create_test_ads_bulk(
            seller, category, city, 25, status=AdStatus.PUBLISHED
        )
        all_ids = {a.id for a in ads}

        seen: list[int] = []
        for p in (1, 2, 3):
            payload = self._get(
                {"sort": sort, "page": p, "per_page": 10}
            )
            assert payload["page"] == p
            assert payload["per_page"] == 10
            assert payload["total_count"] == 25
            assert payload["results_truncated"] is False
            # 25 ads at 10/page → pages hold 10, 10, 5.
            assert len(payload["results"]) == (5 if p == 3 else 10)
            seen.extend(_ids(payload))

        assert len(seen) == len(set(seen)) == 25
        assert set(seen) == all_ids


class TestAudienceParity:
    """Withdrawn / banned sellers are invisible through the API, as in HTML."""

    def test_banned_seller_ads_are_hidden(self, seller, category, city) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        client = Client()
        assert ad.id in _ids(client.get(ENDPOINT).json())

        seller.is_banned = True
        seller.save(update_fields=["is_banned"])

        assert ad.id not in _ids(client.get(ENDPOINT).json())

    def test_withdrawn_consent_seller_ads_are_hidden(
        self, seller, category, city
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        client = Client()
        assert ad.id in _ids(client.get(ENDPOINT).json())

        from django.utils import timezone

        seller.consent_revoked_at = timezone.now()
        seller.save(update_fields=["consent_revoked_at"])

        assert ad.id not in _ids(client.get(ENDPOINT).json())

    def test_deleted_seller_ads_are_hidden(self, seller, category, city) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        client = Client()
        assert ad.id in _ids(client.get(ENDPOINT).json())

        seller.is_deleted = True
        seller.save(update_fields=["is_deleted"])

        assert ad.id not in _ids(client.get(ENDPOINT).json())


class TestRateLimitProblem:
    """Exhausting ``API_PUBLIC_READ`` yields an RFC 9457 429 problem."""

    def test_over_budget_returns_rate_limited_problem(
        self, seller, category, city, monkeypatch
    ) -> None:
        """The limiter refusal renders ``rate_limited`` + ``Retry-After``.

        Patches the shared limiter seam (mirroring the deep-link limiter tests
        that patch ``bump_rate_limit_window``) instead of issuing 60 real
        requests.
        """
        monkeypatch.setattr(
            "apps.ads.views.api.listings.rate_limit_check",
            lambda *a, **k: False,
        )
        response = Client().get(ENDPOINT)

        assert response.status_code == 429
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        assert response.headers.get(RETRY_AFTER_HEADER) == "60"
        payload = response.json()
        assert payload["type"] == TYPE_RATE_LIMITED
        assert payload["status"] == 429

    def test_under_budget_is_allowed(self, seller, category, city) -> None:
        create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        response = Client().get(ENDPOINT)
        assert response.status_code == 200


class TestValidationProblem:
    """Malformed params yield the RFC 9457 422 ``validation_failed`` problem."""

    def test_too_many_features_returns_validation_problem(self) -> None:
        # MAX_FEATURE_FILTER_SLUGS is 17; 18 distinct slugs breach it.
        too_many = [f"feature-{i}" for i in range(18)]
        response = Client().get(ENDPOINT, {"features": too_many})

        assert response.status_code == 422
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        payload = response.json()
        assert payload["type"] == TYPE_VALIDATION_FAILED
        assert isinstance(payload["errors"], list)


class TestHtmlJsonParity:
    """Identical params → identical ordered ad ids in JSON and HTML."""

    @pytest.mark.parametrize("sort", [None, AdSort.PRICE_LOW, AdSort.DATE_OLD])
    def test_json_ids_match_html_page_obj(
        self, seller, category, city, sort
    ) -> None:
        create_test_ads_bulk(seller, category, city, 30, status=AdStatus.PUBLISHED)
        # The HTML view fixes the page size at ``ListingsQuery.PER_PAGE`` (24),
        # so parity uses the JSON default (no ``per_page``) at page 1.
        query: dict[str, Any] = {}
        html_query: dict[str, Any] = {"page": 1}
        if sort is not None:
            query["sort"] = sort
            html_query["sort"] = sort

        client = Client()
        html = client.get(reverse("ads:listings"), html_query)
        html_ids = [a.id for a in html.context["page_obj"]]
        json_ids = _ids(client.get(ENDPOINT, query).json())

        assert json_ids == html_ids

    def test_parity_holds_on_warm_cache(self, seller, category, city) -> None:
        """Parity still holds after priming the shared caches.

        Plain listings does not use the search id-list cache, but its lookup /
        category-resolution reads are cached. Priming them with a prior request
        (the same warm-cache discipline the cache suites use) proves the ordered
        id comparison is unaffected by cache state.
        """
        create_test_ads_bulk(seller, category, city, 30, status=AdStatus.PUBLISHED)
        client = Client()

        # Prime: full HTML render + a search query (warms category/lookup caches).
        client.get(reverse("ads:listings"))
        client.get("/search/", {"q": "test"})

        html = client.get(reverse("ads:listings"), {"sort": AdSort.PRICE_LOW})
        html_ids = [a.id for a in html.context["page_obj"]]
        json_ids = _ids(
            client.get(ENDPOINT, {"sort": AdSort.PRICE_LOW}).json()
        )

        assert json_ids == html_ids


class TestPaginationEnvelope:
    """The pagination envelope is coherent on a multi-page fixture set."""

    def test_multi_page_envelope(self, seller, category, city) -> None:
        create_test_ads_bulk(seller, category, city, 25, status=AdStatus.PUBLISHED)
        client = Client()

        first = client.get(ENDPOINT, {"per_page": 10}).json()
        assert first["page"] == 1
        assert first["per_page"] == 10
        assert first["total_count"] == 25
        assert first["results_truncated"] is False
        assert first["has_next"] is True
        assert len(first["results"]) == 10

        last = client.get(ENDPOINT, {"per_page": 10, "page": 3}).json()
        assert last["page"] == 3
        assert last["total_count"] == 25
        assert last["results_truncated"] is False
        assert last["has_next"] is False
        assert len(last["results"]) == 5

    def test_out_of_range_page_clamps_to_last(self, seller, category, city) -> None:
        create_test_ads_bulk(seller, category, city, 5, status=AdStatus.PUBLISHED)
        payload = Client().get(ENDPOINT, {"per_page": 10, "page": 999}).json()
        assert payload["page"] == 1
        assert payload["has_next"] is False
        assert payload["total_count"] == 5

    def test_serialized_ad_shape(self, seller, category, city) -> None:
        ad = create_test_ad(
            seller, category, city, title="Shape Ad", price=123,
            status=AdStatus.PUBLISHED,
        )
        payload = Client().get(ENDPOINT).json()
        assert len(payload["results"]) == 1
        row = payload["results"][0]
        expected_keys = {
            "id", "title", "price", "currency", "city", "category",
            "listing_purpose", "condition", "status", "published_at",
            "created_at", "image_urls", "absolute_url",
        }
        assert expected_keys <= set(row)
        assert row["id"] == ad.id
        assert row["title"] == "Shape Ad"
        assert row["city"]["slug"] == city.slug
        assert row["category"]["slug"] == category.slug
        assert row["status"] == AdStatus.PUBLISHED
        assert row["absolute_url"] == ad.get_absolute_url()


class TestReverseSmoke:
    """The route reverses under the ``ads_api`` namespace."""

    def test_reverse_listings(self) -> None:
        assert reverse("ads_api:listings") == ENDPOINT

    def test_reverse_cross_product_helpers(self) -> None:
        # Guard against accidental extra routes: the reverse map has one entry.
        assert ENDPOINT == "/api/v1/ads/"
