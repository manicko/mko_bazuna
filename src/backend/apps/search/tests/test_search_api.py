"""Tests for the ``GET /api/v1/search/`` JSON FTS-search endpoint (S1.4).

Exercises the endpoint browserless (Django ``Client()``) with structured JSON
asserts across the same dimensions the HTML search view exposes: query
(exact / fuzzy / empty / multi-word), category (valid / invalid), city (via the
middleware-resolved current city), price bounds, sort, page and the
``all_categories`` opt-out — plus the cap/truncation semantics through the
warm-cache seam, HTML/JSON parity (incl. warm-cache), analytics/history
side-effect parity, ``?lang`` locale parity, and the 422/429 problems.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.test import Client
from django.urls import reverse

from apps.analytics.models import AnalyticsEvent
from apps.core.enums import AdSort, AdStatus
from apps.core.utils.problem import (
    PROBLEM_CONTENT_TYPE,
    RETRY_AFTER_HEADER,
    TYPE_RATE_LIMITED,
    TYPE_VALIDATION_FAILED,
)
from apps.locations.models import City
from apps.search.services.cache import SEARCH_CACHE_MAX_HITS
from conftest import create_test_ad, create_test_ads_bulk

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

ENDPOINT = "/api/v1/search/"


def _ids(payload: dict[str, Any]) -> list[int]:
    """Return the ordered ``id`` sequence from a JSON envelope's results."""
    return [row["id"] for row in payload["results"]]


class TestParamParity:
    """Each search dimension is exercised through the endpoint."""

    def _get(self, query: dict[str, Any]) -> dict[str, Any]:
        response = Client().get(ENDPOINT, query)
        assert response.status_code == 200
        assert response.headers.get("Content-Type", "").startswith("application/json")
        return response.json()

    def test_empty_query_returns_all_published(self, seller, category, city) -> None:
        create_test_ads_bulk(seller, category, city, 3, status=AdStatus.PUBLISHED)
        payload = self._get({})
        assert payload["total_count"] == 3
        assert payload["results_truncated"] is False
        assert payload["page"] == 1
        assert payload["per_page"] == 24
        assert payload["narrowed_category"] is None
        assert payload["suggested_category"] is None
        assert payload["suggested_city"] is None
        assert payload["search_cache_max_hits"] == SEARCH_CACHE_MAX_HITS

    def test_exact_query_match(self, seller, category, city) -> None:
        match = create_test_ad(
            seller, category, city, title="Красный велосипед",
            status=AdStatus.PUBLISHED,
        )
        create_test_ad(
            seller, category, city, title="Синий самокат", status=AdStatus.PUBLISHED
        )
        payload = self._get({"q": "велосипед", "lang": "ru"})
        assert _ids(payload) == [match.id]

    def test_multi_word_query(self, seller, category, city) -> None:
        match = create_test_ad(
            seller, category, city, title="Красный велосипед",
            status=AdStatus.PUBLISHED,
        )
        payload = self._get({"q": "красный велосипед", "lang": "ru"})
        assert match.id in _ids(payload)

    def test_invalid_category_yields_suggestion(
        self, seller, category, city
    ) -> None:
        create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        payload = self._get({"q": "товар", "category": "does-not-exist", "lang": "ru"})
        # Unknown category applies no filter and the raw slug is echoed back as
        # the did-you-mean suggestion (mirrors the HTML view).
        assert payload["suggested_category"] == "does-not-exist"

    def test_valid_category_sets_breadcrumb(self, seller, category, city) -> None:
        create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        payload = self._get({"category": category.slug})
        assert payload["suggested_category"] is None

    def test_price_bounds(self, seller, category, city) -> None:
        cheap = create_test_ad(
            seller, category, city, title="Cheap", price=50,
            status=AdStatus.PUBLISHED,
        )
        expensive = create_test_ad(
            seller, category, city, title="Expensive", price=300,
            status=AdStatus.PUBLISHED,
        )
        payload = self._get({"min_price": 100, "max_price": 500})
        ids = _ids(payload)
        assert expensive.id in ids
        assert cheap.id not in ids

    def test_sort_price_low_orders_ascending(self, seller, category, city) -> None:
        create_test_ad(
            seller, category, city, title="Expensive", price=300,
            status=AdStatus.PUBLISHED,
        )
        create_test_ad(
            seller, category, city, title="Cheap", price=100,
            status=AdStatus.PUBLISHED,
        )
        payload = self._get({"sort": AdSort.PRICE_LOW.value})
        prices = [float(row["price"]) for row in payload["results"]]
        assert prices == sorted(prices)

    def test_city_filters_via_middleware_param(self, seller, category, city) -> None:
        other_city = City.objects.create(
            country_code="ME", name="Другиград", region="Central", slug="drugigrad",
        )
        here = create_test_ad(
            seller, category, city, title="Велосипед здесь",
            status=AdStatus.PUBLISHED,
        )
        create_test_ad(
            seller, category, other_city, title="Велосипед там",
            status=AdStatus.PUBLISHED,
        )
        payload = self._get({"q": "велосипед", "city": city.slug, "lang": "ru"})
        assert _ids(payload) == [here.id]

    def test_all_categories_flag_disables_narrowing(
        self, seller, category, city
    ) -> None:
        create_test_ad(
            seller, category, city, title="Транспорт", status=AdStatus.PUBLISHED
        )
        payload = self._get({"q": "Транспорт", "all_categories": "1", "lang": "ru"})
        assert payload["narrowed_category"] is None


class TestEnvelopeParity:
    """Ordered ids match the HTML ``page_obj`` exactly (incl. warm cache)."""

    @pytest.mark.parametrize("sort", [None, AdSort.PRICE_LOW])
    def test_json_ids_match_html(self, seller, category, city, sort) -> None:
        create_test_ads_bulk(seller, category, city, 5, status=AdStatus.PUBLISHED)
        json_query: dict[str, Any] = {"q": "Test"}
        html_query: dict[str, Any] = {"q": "Test"}
        if sort is not None:
            json_query["sort"] = sort.value
            html_query["sort"] = sort.value

        client = Client()
        html = client.get(reverse("search:search"), html_query)
        html_ids = [a.id for a in html.context["page_obj"]]
        json_ids = _ids(client.get(ENDPOINT, json_query).json())
        assert json_ids == html_ids

    def test_parity_holds_on_warm_cache(self, seller, category, city) -> None:
        """After priming the cache, JSON and HTML still return identical ids.

        This proves the API endpoint uses ``_rank_cache_hit_page`` identically —
        the HTML request primed the shared cache, then both surfaces hit it.
        """
        create_test_ads_bulk(seller, category, city, 5, status=AdStatus.PUBLISHED)
        client = Client()

        client.get(reverse("search:search"), {"q": "Test"})  # prime cache
        html = client.get(reverse("search:search"), {"q": "Test"})
        html_ids = [a.id for a in html.context["page_obj"]]
        json_ids = _ids(client.get(ENDPOINT, {"q": "Test"}).json())
        assert json_ids == html_ids


class TestCapSemantics:
    """Cap/truncation semantics through the warm-cache seam (O-2b)."""

    def test_at_cap_reports_truncated_and_cap_plus_one(
        self, seller, category, city, monkeypatch
    ) -> None:
        """A cached id list at the cap reports ``truncated`` and ``cap + 1``.

        The production path pushes ``SEARCH_CACHE_MAX_HITS`` into SQL, so a set
        of 1000 ad rows is required to reach the cap. Building 1000 real rows is
        unnecessary here: ``get_cached_search_ids`` returns whatever the producer
        yields, so the producer's bound is patched down to a tiny cap and exactly
        that many matching ads are seeded. Both the view's producer slice and the
        shared ``_resolve_search_count`` read their own module-level
        ``SEARCH_CACHE_MAX_HITS``, so both are patched. The endpoint's truncation
        decision is driven by the shared ``_resolve_search_count`` and is
        identical for any cap value.
        """
        small_cap = 3
        monkeypatch.setattr(
            "apps.search.views.api.search.SEARCH_CACHE_MAX_HITS", small_cap
        )
        monkeypatch.setattr(
            "apps.search.services.fts.SEARCH_CACHE_MAX_HITS", small_cap
        )
        create_test_ads_bulk(
            seller, category, city, small_cap, title_prefix="Товар",
            status=AdStatus.PUBLISHED,
        )

        payload = Client().get(ENDPOINT, {"q": "Товар", "lang": "ru"}).json()
        assert payload["results_truncated"] is True
        assert payload["total_count"] == small_cap + 1

    def test_below_cap_is_not_truncated(self, seller, category, city) -> None:
        create_test_ads_bulk(
            seller, category, city, 3, title_prefix="Товар", status=AdStatus.PUBLISHED
        )
        payload = Client().get(ENDPOINT, {"q": "Товар", "lang": "ru"}).json()
        assert payload["results_truncated"] is False
        assert payload["total_count"] == 3


class TestAnalyticsHistoryParity:
    """API search side effects match an HTML search for the same query."""

    def test_api_records_search_performed_event(self, seller, category, city) -> None:
        create_test_ad(seller, category, city, title="Товар", status=AdStatus.PUBLISHED)
        before = AnalyticsEvent.objects.filter(event_type="search_performed").count()
        Client().get(ENDPOINT, {"q": "товар", "lang": "ru"})
        after = AnalyticsEvent.objects.filter(event_type="search_performed").count()
        assert after == before + 1

    def test_api_and_html_record_identically(self, seller, category, city) -> None:
        """Each surface records exactly one event, popular-search hit and row.

        Uses an authenticated session (``force_login``) so ``record_search_history``
        persists a DB row; for an anonymous session history would stay in the
        session instead. A *distinct* query is used per surface because
        ``record_search_history`` dedupes by (user, query) — a repeated identical
        query updates one row rather than adding another.
        """
        from apps.search.models import PopularSearch, SearchHistory

        create_test_ad(seller, category, city, title="Товар", status=AdStatus.PUBLISHED)
        client = Client()
        client.force_login(seller)

        client.get(ENDPOINT, {"q": "товар", "lang": "ru"})
        api_events = AnalyticsEvent.objects.filter(event_type="search_performed").count()
        api_history = SearchHistory.objects.filter(user=seller).count()
        api_popular = PopularSearch.objects.get(query_normalized="товар").hit_count

        client.get(reverse("search:search"), {"q": "самокат", "lang": "ru"})
        html_events = AnalyticsEvent.objects.filter(
            event_type="search_performed"
        ).count()
        html_history = SearchHistory.objects.filter(user=seller).count()
        html_popular = PopularSearch.objects.get(query_normalized="самокат").hit_count

        # Each request adds exactly one event, one history row and one hit.
        assert html_events == api_events + 1
        assert html_history == api_history + 1
        assert html_popular == 1
        assert api_popular == 1


class TestLocaleParity:
    """``?lang`` resolves the per-language FTS vector via the middleware."""

    def test_ru_locale_matches_russian_content(self, seller, category, city) -> None:
        match = create_test_ad(
            seller, category, city, title="Красный велосипед",
            status=AdStatus.PUBLISHED,
        )
        payload = Client().get(ENDPOINT, {"q": "велосипед", "lang": "ru"}).json()
        assert match.id in _ids(payload)

    def test_lang_param_does_not_error(self, seller, category, city) -> None:
        create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        for lang in ("ru", "en", "bs"):
            response = Client().get(ENDPOINT, {"q": "test", "lang": lang})
            assert response.status_code == 200


class TestErrorProblems:
    """422 / 429 use the RFC 9457 problem documents; anonymous access is OK."""

    def test_too_many_features_returns_validation_problem(self) -> None:
        too_many = [f"feature-{i}" for i in range(18)]  # MAX_FEATURE_FILTER_SLUGS=17
        response = Client().get(ENDPOINT, {"q": "x", "features": too_many})
        assert response.status_code == 422
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        payload = response.json()
        assert payload["type"] == TYPE_VALIDATION_FAILED
        assert isinstance(payload["errors"], list)

    def test_over_budget_returns_rate_limited_problem(
        self, seller, category, city, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            "apps.search.views.api.search.rate_limit_check",
            lambda *a, **k: False,
        )
        response = Client().get(ENDPOINT)
        assert response.status_code == 429
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        assert response.headers.get(RETRY_AFTER_HEADER) == "60"
        payload = response.json()
        assert payload["type"] == TYPE_RATE_LIMITED
        assert payload["status"] == 429

    def test_anonymous_access_allowed(self, seller, category, city) -> None:
        create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        response = Client().get(ENDPOINT)
        assert response.status_code == 200


class TestReverseSmoke:
    """The route reverses under the ``search_api`` namespace."""

    def test_reverse_search(self) -> None:
        assert reverse("search_api:search") == ENDPOINT
