"""Tests for the cabinet saved-searches + search-history JSON list reads (S2.7).

Browserless (``Client()``) coverage of the two session-only reads:

- **401 matrix** — anonymous answers the 401 ``unauthenticated`` problem for
  **both** endpoints (no ``WWW-Authenticate``); a logged-in session answers 200.
- **Ownership scoping** — only the caller's own rows are returned on either
  endpoint; another user's rows are never visible.
- **Pagination envelope + ordering parity** — the shared
  ``{page, per_page, total_count, results_truncated, results[], has_next}``
  envelope, correct across pages, with JSON ordering matching the HTML cabinet
  mirrors for identical fixtures.
- **A6** — an anonymous session cannot read search history via the API (401),
  consistent with the HTML cabinet ``@login_required`` gate (302 to login).
- **Restructure guard** — ``GET /api/v1/favorites/`` still behaves exactly as it
  did after S2.4 despite the ``api_urls.py`` prefix restructure.
"""

from __future__ import annotations

import datetime
from typing import Any

import pytest
from django.test import Client
from django.utils import timezone

from apps.ads.models import AdFavorite
from apps.core.enums import AdStatus
from apps.core.utils.problem import PROBLEM_CONTENT_TYPE
from apps.search.models import SavedSearch, SearchHistory
from conftest import create_test_ad, make_user

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

SAVED_SEARCHES_ENDPOINT = "/api/v1/saved-searches/"
SEARCH_HISTORY_ENDPOINT = "/api/v1/search-history/"
FAVORITES_ENDPOINT = "/api/v1/favorites/"
SAVED_SEARCHES_HTML = "/cabinet/saved-searches/"
SEARCH_HISTORY_HTML = "/cabinet/search-history/"

# Page sizes declared by the API modules (kept in sync with them).
SAVED_SEARCHES_PER_PAGE = 24
SEARCH_HISTORY_PER_PAGE = 100


def _make_saved_search(owner: Any, *, age_seconds: int = 0, **kwargs: Any) -> SavedSearch:
    """Create a saved search with a deterministic ``created_at``.

    The HTML mirror and the API order by ``-created_at`` only (no ``-id``
    tiebreaker), so equal timestamps would make the two orderings
    non-deterministic. Backdating each row by a distinct offset pins the order
    identically on both surfaces.
    """
    ss = SavedSearch.objects.create(user=owner, **kwargs)
    created_at = timezone.now() - datetime.timedelta(seconds=age_seconds)
    SavedSearch.objects.filter(pk=ss.pk).update(created_at=created_at)
    ss.refresh_from_db()
    return ss


def _make_history(owner: Any, query: str, *, age_seconds: int = 0) -> SearchHistory:
    """Create a history row with a deterministic ``created_at`` (see above)."""
    entry = SearchHistory.objects.create(
        user=owner, query=query, query_normalized=query
    )
    created_at = timezone.now() - datetime.timedelta(seconds=age_seconds)
    SearchHistory.objects.filter(pk=entry.pk).update(created_at=created_at)
    entry.refresh_from_db()
    return entry


class TestAuthMatrix:
    """Anonymous → 401 problem; authenticated session → 200 envelope."""

    def test_saved_searches_anonymous_returns_401_problem(self) -> None:
        response = Client().get(SAVED_SEARCHES_ENDPOINT)

        assert response.status_code == 401
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        payload = response.json()
        assert payload["type"] == "unauthenticated"
        assert payload["status"] == 401
        assert "WWW-Authenticate" not in response.headers

    def test_search_history_anonymous_returns_401_problem(self) -> None:
        response = Client().get(SEARCH_HISTORY_ENDPOINT)

        assert response.status_code == 401
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        payload = response.json()
        assert payload["type"] == "unauthenticated"
        assert payload["status"] == 401
        assert "WWW-Authenticate" not in response.headers

    def test_saved_searches_authenticated_returns_200_envelope(
        self, buyer, buyer_client
    ) -> None:
        _make_saved_search(buyer, query="велосипед")

        response = buyer_client.get(SAVED_SEARCHES_ENDPOINT)

        assert response.status_code == 200
        payload = response.json()
        assert payload["page"] == 1
        assert payload["per_page"] == SAVED_SEARCHES_PER_PAGE
        assert payload["total_count"] == 1
        assert payload["results_truncated"] is False
        assert payload["has_next"] is False
        assert payload["results"][0]["query"] == "велосипед"

    def test_search_history_authenticated_returns_200_envelope(
        self, buyer, buyer_client
    ) -> None:
        _make_history(buyer, "самокат")

        response = buyer_client.get(SEARCH_HISTORY_ENDPOINT)

        assert response.status_code == 200
        payload = response.json()
        assert payload["page"] == 1
        assert payload["per_page"] == SEARCH_HISTORY_PER_PAGE
        assert payload["total_count"] == 1
        assert payload["results_truncated"] is False
        assert payload["has_next"] is False
        assert payload["results"][0]["query"] == "самокат"


class TestOwnershipScoping:
    """Only the caller's rows are visible on either endpoint."""

    def test_saved_searches_other_users_rows_not_visible(
        self, buyer, buyer_client
    ) -> None:
        other = make_user(940000301)
        mine = _make_saved_search(buyer, query="мой запрос")
        theirs = _make_saved_search(other, query="чужой запрос")

        payload = buyer_client.get(SAVED_SEARCHES_ENDPOINT).json()

        ids = {r["id"] for r in payload["results"]}
        assert ids == {mine.id}
        assert theirs.id not in ids

    def test_search_history_other_users_rows_not_visible(
        self, buyer, buyer_client
    ) -> None:
        other = make_user(940000302)
        _make_history(buyer, "мой поиск")
        _make_history(other, "чужой поиск")

        payload = buyer_client.get(SEARCH_HISTORY_ENDPOINT).json()

        queries = {r["query"] for r in payload["results"]}
        assert queries == {"мой поиск"}


class TestPaginationEnvelope:
    """The envelope is correct across multiple pages."""

    def test_saved_searches_multi_page_envelope(self, buyer, buyer_client) -> None:
        for i in range(SAVED_SEARCHES_PER_PAGE + 2):
            _make_saved_search(buyer, query=f"q{i}", age_seconds=i)

        first = buyer_client.get(SAVED_SEARCHES_ENDPOINT).json()
        assert first["page"] == 1
        assert first["total_count"] == SAVED_SEARCHES_PER_PAGE + 2
        assert len(first["results"]) == SAVED_SEARCHES_PER_PAGE
        assert first["has_next"] is True

        second = buyer_client.get(SAVED_SEARCHES_ENDPOINT, {"page": 2}).json()
        assert second["page"] == 2
        assert len(second["results"]) == 2
        assert second["has_next"] is False

        first_ids = {r["id"] for r in first["results"]}
        second_ids = {r["id"] for r in second["results"]}
        assert first_ids.isdisjoint(second_ids)

    def test_search_history_multi_page_envelope(self, buyer, buyer_client) -> None:
        for i in range(SEARCH_HISTORY_PER_PAGE + 2):
            _make_history(buyer, f"q{i}", age_seconds=i)

        first = buyer_client.get(SEARCH_HISTORY_ENDPOINT).json()
        assert first["page"] == 1
        assert first["total_count"] == SEARCH_HISTORY_PER_PAGE + 2
        assert len(first["results"]) == SEARCH_HISTORY_PER_PAGE
        assert first["has_next"] is True

        second = buyer_client.get(SEARCH_HISTORY_ENDPOINT, {"page": 2}).json()
        assert second["page"] == 2
        assert len(second["results"]) == 2
        assert second["has_next"] is False


class TestHtmlParity:
    """JSON ordering matches the HTML cabinet mirrors for identical fixtures."""

    def test_saved_searches_results_match_html_order(
        self, buyer, buyer_client, category, city
    ) -> None:
        expected = [
            _make_saved_search(
                buyer,
                query=f"q{i}",
                age_seconds=i,
                city=city if i == 0 else None,
                category=category if i == 0 else None,
                min_price=100 if i == 0 else None,
                max_price=500 if i == 0 else None,
            ).id
            for i in range(3)
        ]

        html_ids = [ss.id for ss in buyer_client.get(SAVED_SEARCHES_HTML).context["saved_searches"]]
        json_ids = [r["id"] for r in buyer_client.get(SAVED_SEARCHES_ENDPOINT).json()["results"]]

        assert json_ids == html_ids
        # Newest first (distinct created_at → deterministic).
        assert json_ids == expected

    def test_saved_searches_payload_renders_html_fields(
        self, buyer, buyer_client, category, city
    ) -> None:
        ss = _make_saved_search(
            buyer,
            query="велосипед",
            city=city,
            category=category,
            min_price=100,
            max_price=500,
        )

        row = buyer_client.get(SAVED_SEARCHES_ENDPOINT).json()["results"][0]

        assert row["id"] == ss.id
        assert row["query"] == "велосипед"
        assert row["city"]["slug"] == city.slug
        assert row["category"]["slug"] == category.slug
        assert row["min_price"] == 100
        assert row["max_price"] == 500
        assert row["is_active"] is True
        # The capability token must never leak.
        assert "unsubscribe_token" not in row

    def test_search_history_results_match_html_order(self, buyer, buyer_client) -> None:
        _make_history(buyer, "первый", age_seconds=0)
        _make_history(buyer, "второй", age_seconds=1)
        _make_history(buyer, "третий", age_seconds=2)

        html_queries = [
            entry["query"]
            for entry in buyer_client.get(SEARCH_HISTORY_HTML).context["history_entries"]
        ]
        json_queries = [r["query"] for r in buyer_client.get(SEARCH_HISTORY_ENDPOINT).json()["results"]]

        assert json_queries == html_queries
        assert json_queries == ["первый", "второй", "третий"]


class TestA6SearchHistoryIsSessionOnly:
    """A6: anon session history is never exposed — API 401 mirrors HTML gate."""

    def test_anonymous_cannot_read_history_via_api_consistent_with_html_gate(
        self,
    ) -> None:
        # The HTML cabinet mirror is @login_required → anon is redirected to login.
        html_response = Client().get(SEARCH_HISTORY_HTML)
        assert html_response.status_code == 302
        assert html_response.url.startswith("/login/issue/")

        # The API mirrors that gate as a 401 problem — no history is ever exposed.
        api_response = Client().get(SEARCH_HISTORY_ENDPOINT)
        assert api_response.status_code == 401
        assert api_response.json()["type"] == "unauthenticated"


class TestUrlRestructureGuard:
    """The api_urls.py restructure keeps GET /api/v1/favorites/ working."""

    def test_favorites_endpoint_still_works(
        self, buyer, buyer_client, seller, category, city
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        AdFavorite.objects.create(user=buyer, ad=ad)

        response = buyer_client.get(FAVORITES_ENDPOINT)

        assert response.status_code == 200
        assert [r["id"] for r in response.json()["results"]] == [ad.id]

    def test_favorites_endpoint_still_requires_session(self) -> None:
        response = Client().get(FAVORITES_ENDPOINT)

        assert response.status_code == 401
        assert response.json()["type"] == "unauthenticated"
