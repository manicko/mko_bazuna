"""Tests for the ``GET /api/v1/favorites/`` JSON list endpoint (S2.4).

Browserless (``Client()``) coverage of the favorites-list read:

- **401 matrix** — anonymous answers the 401 ``unauthenticated`` problem; a
  logged-in session answers 200.
- **Ownership scoping** — only the caller's own favorites are returned; another
  user's favorites are never visible.
- **Pagination envelope** — the same ``{page, per_page, total_count,
  results_truncated, results[], has_next}`` envelope as every other listing
  endpoint, correct across multiple pages.
- **Ordering + HTML parity** — the JSON ``results[].id`` sequence equals the HTML
  cabinet list's ``page_obj`` ids for identical fixtures (the shared
  ``favorites_queryset`` guarantees it).
"""

from __future__ import annotations

from typing import Any

import pytest
from django.test import Client

from apps.ads.models import AdFavorite
from apps.ads.services.favorites import PER_PAGE
from apps.core.enums import AdStatus
from apps.core.utils.problem import PROBLEM_CONTENT_TYPE
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

ENDPOINT = "/api/v1/favorites/"
HTML_ENDPOINT = "/cabinet/favorites/"


def _favorite(owner: Any, ad: Any) -> AdFavorite:
    """Create the (owner, ad) favorite row."""
    return AdFavorite.objects.create(user=owner, ad=ad)


class TestAuthMatrix:
    """Anonymous → 401 problem; authenticated session → 200 envelope."""

    def test_anonymous_returns_401_problem(self) -> None:
        response = Client().get(ENDPOINT)

        assert response.status_code == 401
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        payload = response.json()
        assert payload["type"] == "unauthenticated"
        assert payload["status"] == 401
        assert "WWW-Authenticate" not in response.headers

    def test_authenticated_returns_200_envelope(
        self, buyer, buyer_client, seller, category, city
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        _favorite(buyer, ad)

        response = buyer_client.get(ENDPOINT)

        assert response.status_code == 200
        payload = response.json()
        assert payload["page"] == 1
        assert payload["per_page"] == PER_PAGE
        assert payload["total_count"] == 1
        assert payload["results_truncated"] is False
        assert payload["has_next"] is False
        assert [r["id"] for r in payload["results"]] == [ad.id]


class TestOwnershipScoping:
    """Only the caller's favorites are visible — never another user's."""

    def test_other_users_favorites_are_not_visible(
        self, buyer, buyer_client, user, seller, category, city
    ) -> None:
        mine = create_test_ad(seller, category, city, title="Mine", status=AdStatus.PUBLISHED)
        theirs = create_test_ad(
            seller, category, city, title="Theirs", status=AdStatus.PUBLISHED
        )
        _favorite(buyer, mine)
        _favorite(user, theirs)

        payload = buyer_client.get(ENDPOINT).json()

        ids = {r["id"] for r in payload["results"]}
        assert ids == {mine.id}
        assert theirs.id not in ids


class TestPaginationEnvelope:
    """The envelope is correct across multiple pages."""

    def test_multi_page_envelope(
        self, buyer, buyer_client, seller, category, city
    ) -> None:
        ads = [
            create_test_ad(seller, category, city, title=f"Ad {i}", status=AdStatus.PUBLISHED)
            for i in range(PER_PAGE + 2)
        ]
        for ad in ads:
            _favorite(buyer, ad)

        first = buyer_client.get(ENDPOINT).json()
        assert first["page"] == 1
        assert first["total_count"] == PER_PAGE + 2
        assert len(first["results"]) == PER_PAGE
        assert first["has_next"] is True

        second = buyer_client.get(ENDPOINT, {"page": 2}).json()
        assert second["page"] == 2
        assert len(second["results"]) == 2
        assert second["has_next"] is False

        # No row appears on both pages.
        first_ids = {r["id"] for r in first["results"]}
        second_ids = {r["id"] for r in second["results"]}
        assert first_ids.isdisjoint(second_ids)


class TestHtmlParity:
    """JSON ``results[].id`` == HTML cabinet ``page_obj`` ids, incl. ordering."""

    def test_results_ids_match_html_page_obj(
        self, buyer, buyer_client, seller, category, city
    ) -> None:
        ads = [
            create_test_ad(seller, category, city, title=f"Ad {i}", status=AdStatus.PUBLISHED)
            for i in range(PER_PAGE + 2)
        ]
        for ad in ads:
            _favorite(buyer, ad)

        for page in (1, 2):
            html_ids = [
                a.id
                for a in buyer_client.get(HTML_ENDPOINT, {"page": page}).context["page_obj"]
            ]
            json_ids = [
                r["id"]
                for r in buyer_client.get(ENDPOINT, {"page": page}).json()["results"]
            ]
            assert json_ids == html_ids
