"""Tests for ``POST /api/v1/search-history/clear/`` (S3.5).

Browserless (``Client()``) coverage of the search-history clear half:

- **401** — an anonymous request answers the 401 ``unauthenticated`` problem (no
  ``WWW-Authenticate``), mirroring the HTML cabinet ``@login_required`` gate (A6).
- **405** — an authenticated non-POST answers the 405 ``method_not_allowed``
  problem with ``Allow: POST``.
- **Clear** — a populated history is emptied; the S2.7 read then reports
  ``total_count == 0``.
- **Idempotent (Q8)** — re-POSTing on an already-empty history returns the same
  confirmed state ``{"cleared": true, "remaining": 0}``.
- **Scope parity** — another user's history is untouched (the HTML clear's scope
  is the caller's rows only).
- **429** — an exhausted ``API_WRITE`` budget answers the ``rate_limited``
  problem + ``Retry-After``.

No pre-existing test file is edited. The S2.7 read endpoint is only *read* here to
confirm the cleared state is re-retrievable.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.test import Client

from apps.core.utils.problem import (
    PROBLEM_CONTENT_TYPE,
    RETRY_AFTER_HEADER,
    TYPE_RATE_LIMITED,
)
from apps.search.models import SearchHistory
from conftest import make_user

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

CLEAR_ENDPOINT = "/api/v1/search-history/clear/"
READ_ENDPOINT = "/api/v1/search-history/"
CLEAR_HTML = "/cabinet/search-history/clear/"


def _make_history(owner: Any, query: str) -> SearchHistory:
    """Create one history row for *owner*."""
    return SearchHistory.objects.create(
        user=owner, query=query, query_normalized=query
    )


class TestAuthMatrix:
    """Anonymous → 401 ``unauthenticated`` problem (no challenge)."""

    def test_anonymous_returns_401_problem(self) -> None:
        response = Client().post(CLEAR_ENDPOINT)

        assert response.status_code == 401
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        payload = response.json()
        assert payload["type"] == "unauthenticated"
        assert payload["status"] == 401
        assert "WWW-Authenticate" not in response.headers

    def test_anonymous_gets_401_before_405(self) -> None:
        """Identity first: an anonymous GET is 401, not 405."""
        response = Client().get(CLEAR_ENDPOINT)

        assert response.status_code == 401
        assert response.json()["type"] == "unauthenticated"


class TestMethodNotAllowed:
    """Authenticated non-POST → 405 ``method_not_allowed`` with ``Allow: POST``."""

    @pytest.mark.parametrize("method", ["get", "put"])
    def test_wrong_method_returns_405_problem(self, buyer_client, method: str) -> None:
        response = getattr(buyer_client, method)(CLEAR_ENDPOINT)

        assert response.status_code == 405
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        assert response.headers.get("Allow") == "POST"
        assert response.json()["type"] == "method_not_allowed"


class TestClear:
    """Clearing empties the caller's history; the S2.7 read confirms it."""

    def test_clear_populated_history(self, buyer, buyer_client) -> None:
        for i in range(5):
            _make_history(buyer, f"q{i}")

        response = buyer_client.post(CLEAR_ENDPOINT)

        assert response.status_code == 200
        assert response.json() == {"cleared": True, "remaining": 0}
        assert not SearchHistory.objects.filter(user=buyer).exists()

        # Re-retrievable via the S2.7 read: the cleared state reports 0.
        read = buyer_client.get(READ_ENDPOINT).json()
        assert read["total_count"] == 0
        assert read["results"] == []

    def test_repost_on_empty_is_idempotent(self, buyer, buyer_client) -> None:
        _make_history(buyer, "q")

        first = buyer_client.post(CLEAR_ENDPOINT)
        second = buyer_client.post(CLEAR_ENDPOINT)

        assert first.json() == {"cleared": True, "remaining": 0}
        assert second.status_code == 200
        assert second.json() == {"cleared": True, "remaining": 0}

    def test_clear_on_already_empty_history(self, buyer_client) -> None:
        response = buyer_client.post(CLEAR_ENDPOINT)

        assert response.status_code == 200
        assert response.json() == {"cleared": True, "remaining": 0}


class TestScopeParity:
    """Only the caller's history is cleared; other users are untouched."""

    def test_other_users_history_untouched(self, buyer, buyer_client) -> None:
        other = make_user(940000501)
        _make_history(buyer, "мой")
        _make_history(other, "чужой")

        response = buyer_client.post(CLEAR_ENDPOINT)

        assert response.json() == {"cleared": True, "remaining": 0}
        assert not SearchHistory.objects.filter(user=buyer).exists()
        assert SearchHistory.objects.filter(user=other).count() == 1

    def test_scope_matches_html_clear(self, buyer, buyer_client) -> None:
        """The API clear and the HTML clear leave identical DB state."""
        _make_history(buyer, "a")
        _make_history(buyer, "b")

        buyer_client.post(CLEAR_ENDPOINT)
        api_count = SearchHistory.objects.filter(user=buyer).count()

        # Repopulate and clear through the HTML mirror instead.
        _make_history(buyer, "c")
        buyer_client.post(CLEAR_HTML)
        html_count = SearchHistory.objects.filter(user=buyer).count()

        assert api_count == html_count == 0


class TestRateLimitProblem:
    """Exhausting ``API_WRITE`` yields the RFC 9457 429 problem."""

    def test_over_budget_returns_rate_limited(
        self, buyer_client, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            "apps.cabinet.views.api.search_history_clear.rate_limit_check",
            lambda *a, **k: False,
        )
        response = buyer_client.post(CLEAR_ENDPOINT)

        assert response.status_code == 429
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        assert response.headers.get(RETRY_AFTER_HEADER) == "60"
        payload = response.json()
        assert payload["type"] == TYPE_RATE_LIMITED
        assert payload["status"] == 429
