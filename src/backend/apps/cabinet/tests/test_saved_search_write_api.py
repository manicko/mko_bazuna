"""Tests for the saved-search write endpoints (S3.4).

Browserless (``Client()``) coverage of the four saved-search writes that
complete endpoint row 16:

- create — ``POST /api/v1/saved-searches/``
- toggle — ``POST /api/v1/saved-searches/{pk}/toggle/``
- edit — ``POST /api/v1/saved-searches/{pk}/edit/``
- delete — ``POST /api/v1/saved-searches/{pk}/delete/``

Matrices: 401 (anon, all four), 405 (wrong verb, all four), 422 (malformed
body), 404 (missing / cross-owner id), the happy paths asserting the shared S3.1
service effects, the over-cap query refusal (400 ``query_too_long``) and the 429
write budget. API-vs-HTML end-state equivalence is asserted for each operation by
exercising the HTML mirror and the API on identical fixtures and comparing the
resulting DB state.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from django.test import Client
from django.urls import reverse

from apps.core.utils.problem import PROBLEM_CONTENT_TYPE, RETRY_AFTER_HEADER
from apps.search.models import SavedSearch
from apps.search.services.saved_searches import QUERY_MAX_LENGTH
from conftest import make_user

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

COLLECTION = "/api/v1/saved-searches/"
TOGGLE = "/api/v1/saved-searches/{pk}/toggle/"
EDIT = "/api/v1/saved-searches/{pk}/edit/"
DELETE = "/api/v1/saved-searches/{pk}/delete/"

# HTML mirrors.
SAVE_SEARCH_HTML = "/save-search/"
CABINET_TOGGLE_HTML = "/cabinet/saved-searches/{pk}/toggle/"
CABINET_EDIT_HTML = "/cabinet/saved-searches/{pk}/edit/"
CABINET_DELETE_HTML = "/cabinet/saved-searches/{pk}/delete/"

ALL_WRITE_URLS = (COLLECTION, TOGGLE, EDIT, DELETE)


def _url(template: str, pk: int = 1) -> str:
    """Build a write URL for *pk*."""
    return template.format(pk=pk)


def _post(url: str, body: object | None = None, *, client: Client | None = None) -> Any:
    """POST ``body`` (JSON, default empty object) to *url*."""
    payload = json.dumps(body if body is not None else {})
    return (client or Client()).post(url, data=payload, content_type="application/json")


class TestAuthMatrix:
    """Anonymous → 401 ``unauthenticated`` problem on all four writes."""

    @pytest.mark.parametrize("template", ALL_WRITE_URLS)
    def test_anonymous_returns_401_problem(self, template: str) -> None:
        response = _post(_url(template))

        assert response.status_code == 401
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        payload = response.json()
        assert payload["type"] == "unauthenticated"
        assert payload["status"] == 401
        assert "WWW-Authenticate" not in response.headers

    def test_anonymous_gets_401_before_405(self) -> None:
        """Identity first: an anonymous GET on the toggle is 401, not 405."""
        response = Client().get(_url(TOGGLE))

        assert response.status_code == 401
        assert response.json()["type"] == "unauthenticated"

    def test_anonymous_create_writes_nothing(self) -> None:
        _post(COLLECTION, {"query": "x"})

        assert SavedSearch.objects.count() == 0


class TestMethodNotAllowed:
    """Authenticated non-POST → 405 ``method_not_allowed`` with ``Allow: POST``."""

    @pytest.mark.parametrize("template", (TOGGLE, EDIT, DELETE))
    @pytest.mark.parametrize("method", ["get", "put"])
    def test_wrong_method_returns_405_problem(
        self, buyer_client, buyer, template: str, method: str
    ) -> None:
        ss = SavedSearch.objects.create(user=buyer)
        response = getattr(buyer_client, method)(_url(template, ss.pk))

        assert response.status_code == 405
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        assert response.headers.get("Allow") == "POST"
        assert response.json()["type"] == "method_not_allowed"


class TestValidationProblem:
    """Malformed create/edit body → 422 ``validation_failed`` problem."""

    @pytest.mark.parametrize(
        "raw",
        [
            "{",
            "[]",
            '{"min_price": -1}',
            '{"unknown_field": 1}',
        ],
    )
    def test_create_invalid_body_returns_422(self, buyer_client, raw: str) -> None:
        response = buyer_client.post(
            COLLECTION, data=raw, content_type="application/json"
        )

        assert response.status_code == 422
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        payload = response.json()
        assert payload["type"] == "validation_failed"
        assert payload["status"] == 422
        assert "errors" in payload
        assert SavedSearch.objects.count() == 0

    def test_edit_invalid_body_returns_422(self, buyer_client, buyer) -> None:
        ss = SavedSearch.objects.create(user=buyer)
        response = buyer_client.post(
            _url(EDIT, ss.pk), data='{"min_price": -5}', content_type="application/json"
        )

        assert response.status_code == 422
        assert response.json()["type"] == "validation_failed"


class TestUniformNotFound:
    """A missing id and a cross-owner id answer the identical 404 problem."""

    @pytest.mark.parametrize("template", (TOGGLE, EDIT, DELETE))
    def test_missing_id_returns_404(self, buyer_client, template: str) -> None:
        response = _post(_url(template, 999_999_999), {}, client=buyer_client)

        assert response.status_code == 404
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        payload = response.json()
        assert payload["type"] == "not_found"
        assert payload["status"] == 404

    @pytest.mark.parametrize("template", (TOGGLE, EDIT, DELETE))
    def test_cross_owner_id_returns_404(self, buyer_client, template: str) -> None:
        other = make_user(940000401)
        theirs = SavedSearch.objects.create(user=other, query="чужой")

        response = _post(_url(template, theirs.pk), {"query": "hijack"}, client=buyer_client)

        assert response.status_code == 404
        assert response.json()["type"] == "not_found"
        # The foreign row is untouched.
        theirs.refresh_from_db()
        assert theirs.query == "чужой"


class TestHappyPaths:
    """Each write mutates through the shared S3.1 service and returns the entity."""

    def test_create_returns_serialized_entity(
        self, buyer, buyer_client, category, city
    ) -> None:
        response = _post(
            COLLECTION,
            {"query": "велосипед", "city_id": city.id, "min_price": 100, "max_price": 500},
            client=buyer_client,
        )

        assert response.status_code == 200
        row = response.json()
        assert row["query"] == "велосипед"
        assert row["city"]["id"] == city.id
        assert row["min_price"] == 100
        assert row["max_price"] == 500
        assert row["is_active"] is True
        assert row["language"]
        assert "unsubscribe_token" not in row

        saved = SavedSearch.objects.get(user=buyer)
        assert saved.pk == row["id"]
        assert saved.is_active is True

    def test_toggle_flips_is_active_and_returns_entity(self, buyer, buyer_client) -> None:
        ss = SavedSearch.objects.create(user=buyer, query="q", is_active=True)

        first = _post(_url(TOGGLE, ss.pk), {}, client=buyer_client)
        assert first.status_code == 200
        assert first.json()["is_active"] is False
        ss.refresh_from_db()
        assert ss.is_active is False

        second = _post(_url(TOGGLE, ss.pk), {}, client=buyer_client)
        assert second.json()["is_active"] is True
        ss.refresh_from_db()
        assert ss.is_active is True

    def test_edit_updates_fields_and_returns_entity(
        self, buyer, buyer_client, category
    ) -> None:
        ss = SavedSearch.objects.create(user=buyer, query="old", min_price=1)

        response = _post(
            _url(EDIT, ss.pk),
            {"query": "new", "category_id": category.id, "min_price": 7},
            client=buyer_client,
        )

        assert response.status_code == 200
        assert response.json()["query"] == "new"
        assert response.json()["category"]["id"] == category.id
        ss.refresh_from_db()
        assert ss.query == "new"
        assert ss.category_id == category.id
        assert ss.min_price == 7

    def test_delete_returns_confirmed_state_and_removes_row(
        self, buyer, buyer_client
    ) -> None:
        ss = SavedSearch.objects.create(user=buyer)
        pk = ss.pk

        response = _post(_url(DELETE, pk), {}, client=buyer_client)

        assert response.status_code == 200
        assert response.json() == {"id": pk, "deleted": True}
        assert not SavedSearch.objects.filter(pk=pk).exists()

    def test_token_never_regenerated_across_writes(
        self, buyer, buyer_client
    ) -> None:
        ss = SavedSearch.objects.create(user=buyer, query="q")
        original = ss.unsubscribe_token

        _post(_url(EDIT, ss.pk), {"query": "q2"}, client=buyer_client)
        _post(_url(TOGGLE, ss.pk), {}, client=buyer_client)

        ss.refresh_from_db()
        assert ss.unsubscribe_token == original


class TestOverCapQuery:
    """An over-cap query is refused with the HTML-mirroring 400 problem."""

    def test_create_over_cap_returns_400_query_too_long(self, buyer_client) -> None:
        response = _post(
            COLLECTION, {"query": "x" * (QUERY_MAX_LENGTH + 1)}, client=buyer_client
        )

        assert response.status_code == 400
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        payload = response.json()
        assert payload["type"] == "query_too_long"
        assert payload["status"] == 400
        assert SavedSearch.objects.count() == 0

    def test_create_at_cap_is_allowed(self, buyer_client) -> None:
        response = _post(
            COLLECTION, {"query": "x" * QUERY_MAX_LENGTH}, client=buyer_client
        )

        assert response.status_code == 200


class TestRateLimitProblem:
    """Exhausting ``API_WRITE`` yields the RFC 9457 429 problem."""

    @pytest.mark.parametrize("template", ALL_WRITE_URLS)
    def test_over_budget_returns_rate_limited(
        self, buyer, buyer_client, monkeypatch, template: str
    ) -> None:
        ss = SavedSearch.objects.create(user=buyer)
        monkeypatch.setattr(
            "apps.cabinet.views.api.saved_search_writes.rate_limit_check",
            lambda *a, **k: False,
        )
        response = _post(_url(template, ss.pk), {"query": "q"}, client=buyer_client)

        assert response.status_code == 429
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        assert response.headers.get(RETRY_AFTER_HEADER) == "60"
        payload = response.json()
        assert payload["type"] == "rate_limited"
        assert payload["status"] == 429


class TestHtmlEndStateEquivalence:
    """API and HTML produce the same persisted state for identical operations."""

    def test_create_parity(self, buyer, buyer_client, category, city) -> None:
        # HTML modal create.
        buyer_client.post(
            SAVE_SEARCH_HTML,
            {"query": "html-q", "city_id": city.id, "min_price": 10},
        )
        # API create.
        _post(
            COLLECTION,
            {"query": "api-q", "city_id": city.id, "min_price": 10},
            client=buyer_client,
        )

        html_row = SavedSearch.objects.get(query="html-q")
        api_row = SavedSearch.objects.get(query="api-q")
        assert html_row.city_id == api_row.city_id == city.id
        assert html_row.min_price == api_row.min_price == 10
        assert html_row.is_active is api_row.is_active is True
        assert html_row.language == api_row.language

    def test_toggle_parity(self, buyer, buyer_client) -> None:
        a = SavedSearch.objects.create(user=buyer, is_active=True)
        b = SavedSearch.objects.create(user=buyer, is_active=True)

        buyer_client.post(_url(CABINET_TOGGLE_HTML, a.pk))
        _post(_url(TOGGLE, b.pk), {}, client=buyer_client)

        a.refresh_from_db()
        b.refresh_from_db()
        assert a.is_active == b.is_active is False

    def test_edit_parity(self, buyer, buyer_client, category) -> None:
        a = SavedSearch.objects.create(user=buyer, query="old-a")
        b = SavedSearch.objects.create(user=buyer, query="old-b")

        buyer_client.post(
            _url(CABINET_EDIT_HTML, a.pk),
            {"query": "new", "category_id": category.id},
        )
        _post(
            _url(EDIT, b.pk),
            {"query": "new", "category_id": category.id},
            client=buyer_client,
        )

        a.refresh_from_db()
        b.refresh_from_db()
        assert a.query == b.query == "new"
        assert a.category_id == b.category_id == category.id

    def test_delete_parity(self, buyer, buyer_client) -> None:
        a = SavedSearch.objects.create(user=buyer, query="a")
        b = SavedSearch.objects.create(user=buyer, query="b")

        buyer_client.post(_url(CABINET_DELETE_HTML, a.pk))
        _post(_url(DELETE, b.pk), {}, client=buyer_client)

        assert not SavedSearch.objects.filter(pk__in=[a.pk, b.pk]).exists()


def test_namespace_reverses() -> None:
    """The write routes register under the ``cabinet_api`` namespace."""
    assert reverse("cabinet_api:saved_searches") == COLLECTION
    assert reverse("cabinet_api:saved_search_toggle", args=[7]) == (
        "/api/v1/saved-searches/7/toggle/"
    )
    assert reverse("cabinet_api:saved_search_edit", args=[7]) == (
        "/api/v1/saved-searches/7/edit/"
    )
    assert reverse("cabinet_api:saved_search_delete", args=[7]) == (
        "/api/v1/saved-searches/7/delete/"
    )
