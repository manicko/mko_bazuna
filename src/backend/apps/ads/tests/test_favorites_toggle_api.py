"""Tests for the ``POST /api/v1/favorites/{ad_id}/toggle/`` write (S3.2).

Browserless (``Client()``) coverage of the favorites-toggle write half:

- **401 matrix** — an anonymous request answers the 401 ``unauthenticated``
  problem document and **no** ``WWW-Authenticate`` header.
- **405 matrix** — an authenticated non-POST request answers a 405
  ``method_not_allowed`` problem with an ``Allow: POST`` header.
- **422 matrix** — a malformed / missing / wrongly-typed ``ad_id`` body answers
  a 422 ``validation_failed`` problem.
- **404 uniform** — a missing ad and a non-PUBLISHED ad answer the identical 404
  ``not_found`` problem (mirrors the HTML toggle's ``Http404``).
- **Toggle cycle** — on → off → on with the ``is_favorited`` /
  ``favorites_count`` evolution the shared service returns.
- **429** — an exhausted ``API_WRITE`` namespace answers the RFC 9457
  ``rate_limited`` problem + ``Retry-After``.
- **Scoping** — the ``favorites_count`` reflects only the caller's own
  favorites, never another user's.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from django.test import Client
from django.urls import reverse

from apps.ads.models import AdFavorite
from apps.ads.services.favorites import toggle_favorite
from apps.core.enums import AdStatus
from apps.core.utils.problem import (
    PROBLEM_CONTENT_TYPE,
    RETRY_AFTER_HEADER,
    TYPE_RATE_LIMITED,
)
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

ENDPOINT = "/api/v1/favorites/{ad_id}/toggle/"


def _url(ad_id: int) -> str:
    """Build the favorites-toggle URL for *ad_id*."""
    return ENDPOINT.format(ad_id=ad_id)


def _post(
    ad_id: int,
    *,
    body: object | None = None,
    client: Client | None = None,
    raw: str | None = None,
) -> Any:
    """POST ``body`` (JSON) to the toggle endpoint and return the response."""
    payload = raw if raw is not None else json.dumps(body if body is not None else {})
    return (client or Client()).post(
        _url(ad_id),
        data=payload,
        content_type="application/json",
    )


class TestAuthMatrix:
    """Anonymous → 401 problem (no ``WWW-Authenticate``); session → allowed."""

    def test_anonymous_returns_401_problem(self, seller, category, city) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        response = _post(ad.id, body={"ad_id": ad.id})

        assert response.status_code == 401
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        payload = response.json()
        assert payload["type"] == "unauthenticated"
        assert payload["status"] == 401
        assert "WWW-Authenticate" not in response.headers
        # Nothing persisted for the anonymous caller.
        assert AdFavorite.objects.count() == 0

    def test_anonymous_gets_401_before_405(self) -> None:
        """Identity is checked before method: an anonymous GET is 401, not 405."""
        response = Client().get(_url(1))

        assert response.status_code == 401
        assert response.json()["type"] == "unauthenticated"

    def test_authenticated_toggle_is_allowed(
        self, buyer, buyer_client, seller, category, city
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        response = _post(ad.id, body={"ad_id": ad.id}, client=buyer_client)

        assert response.status_code == 200
        assert AdFavorite.objects.filter(user=buyer, ad=ad).exists()


class TestMethodNotAllowed:
    """Authenticated non-POST → 405 problem with ``Allow: POST``."""

    @pytest.mark.parametrize("method", ["get", "put"])
    def test_wrong_method_returns_405_problem(
        self, buyer_client, seller, category, city, method: str
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        response = getattr(buyer_client, method)(_url(ad.id))

        assert response.status_code == 405
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        assert response.headers.get("Allow") == "POST"
        assert response.json()["type"] == "method_not_allowed"


class TestValidationProblem:
    """Malformed / missing / wrongly-typed ``ad_id`` → 422 problem."""

    @pytest.mark.parametrize(
        "raw",
        [
            "{",  # not JSON at all
            "[]",  # JSON but not an object
            "{}",  # missing required ``ad_id``
            '{"ad_id": "not-an-int"}',  # wrong type
            '{"ad_id": 1, "extra": true}',  # extra key forbidden
        ],
    )
    def test_invalid_body_returns_422_problem(
        self, buyer_client, seller, category, city, raw: str
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        response = _post(ad.id, raw=raw, client=buyer_client)

        assert response.status_code == 422
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        payload = response.json()
        assert payload["type"] == "validation_failed"
        assert payload["status"] == 422
        assert "errors" in payload
        # No state change on a rejected body.
        assert AdFavorite.objects.count() == 0


class TestUniformNotFound:
    """A missing ad and a non-PUBLISHED ad answer the identical 404 problem."""

    def test_missing_ad_returns_uniform_404(self, buyer_client) -> None:
        response = _post(999_999_999, body={"ad_id": 999_999_999}, client=buyer_client)

        assert response.status_code == 404
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        payload = response.json()
        assert payload["type"] == "not_found"
        assert payload["status"] == 404

    def test_non_published_ad_returns_uniform_404(
        self, buyer_client, seller, category, city
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)
        response = _post(ad.id, body={"ad_id": ad.id}, client=buyer_client)

        assert response.status_code == 404
        assert response.json()["type"] == "not_found"
        assert AdFavorite.objects.filter(ad=ad).count() == 0


class TestToggleCycle:
    """on → off → on with the post-toggle state and count evolution."""

    def test_toggle_on_off_on(
        self, buyer, buyer_client, seller, category, city
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)

        first = _post(ad.id, body={"ad_id": ad.id}, client=buyer_client)
        assert first.status_code == 200
        assert first.json() == {
            "ad_id": ad.id,
            "is_favorited": True,
            "favorites_count": 1,
        }
        assert AdFavorite.objects.filter(user=buyer, ad=ad).exists()

        second = _post(ad.id, body={"ad_id": ad.id}, client=buyer_client)
        assert second.status_code == 200
        assert second.json() == {
            "ad_id": ad.id,
            "is_favorited": False,
            "favorites_count": 0,
        }
        assert not AdFavorite.objects.filter(user=buyer, ad=ad).exists()

        third = _post(ad.id, body={"ad_id": ad.id}, client=buyer_client)
        assert third.status_code == 200
        assert third.json() == {
            "ad_id": ad.id,
            "is_favorited": True,
            "favorites_count": 1,
        }

    def test_toggle_service_parity(
        self, buyer, buyer_client, seller, category, city
    ) -> None:
        """The endpoint's payload equals the shared service's result fields."""
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)

        response = _post(ad.id, body={"ad_id": ad.id}, client=buyer_client)
        result = toggle_favorite(buyer, ad.id)  # second call toggles back off

        # API call left the favorite ON; the direct service call turns it OFF.
        assert response.json()["is_favorited"] is True
        assert result.is_favorited is False
        assert result.favorites_count == 0


class TestOwnershipScoping:
    """``favorites_count`` is scoped to the caller, never another user."""

    def test_count_scoped_to_caller(
        self, buyer, buyer_client, seller, category, city, user
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        # The other user favors the same ad; the buyer's count must ignore it.
        AdFavorite.objects.create(user=user, ad=ad)

        response = _post(ad.id, body={"ad_id": ad.id}, client=buyer_client)

        assert response.status_code == 200
        assert response.json()["favorites_count"] == 1
        assert response.json()["is_favorited"] is True


class TestRateLimitProblem:
    """Exhausting ``API_WRITE`` yields the RFC 9457 429 problem."""

    def test_over_budget_returns_rate_limited_problem(
        self, buyer_client, seller, category, city, monkeypatch
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        monkeypatch.setattr(
            "apps.ads.views.api.favorite.rate_limit_check",
            lambda *a, **k: False,
        )
        response = _post(ad.id, body={"ad_id": ad.id}, client=buyer_client)

        assert response.status_code == 429
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        assert response.headers.get(RETRY_AFTER_HEADER) == "60"
        payload = response.json()
        assert payload["type"] == TYPE_RATE_LIMITED
        assert payload["status"] == 429

    def test_under_budget_is_allowed(
        self, buyer_client, seller, category, city
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        response = _post(ad.id, body={"ad_id": ad.id}, client=buyer_client)

        assert response.status_code == 200


def test_namespace_reverses() -> None:
    """The toggle route registers under the ``cabinet_api`` namespace."""
    assert reverse("cabinet_api:favorite_toggle", args=[7]) == (
        "/api/v1/favorites/7/toggle/"
    )
