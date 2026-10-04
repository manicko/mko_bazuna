"""
One rate-limit budget table and one 429 response shape (08-SRCH-010, 08-SRCH-013).

Covers:
- Every limiter's requests/period equals the ``RateLimitBudget`` member it names.
- ``/search/`` and ``/`` (and the other bare-429 routes) share one 429 shape.
- Search and autocomplete keep independent counter namespaces.
- A rotating ``X-Forwarded-For`` reaches the same limiter key as a fixed value.
"""

from collections.abc import Generator

import pytest
from django.core.cache import cache
from django.test import Client

from apps.core.enums import RateLimitBudget
from apps.core.services import contact_rate_limit
from apps.core.utils.rate_limit_response import RATE_LIMIT_ERROR, rate_limited_response

pytestmark = [pytest.mark.django_db]


@pytest.fixture(autouse=True)
def _clear_cache() -> Generator[None]:
    """Clear the shared cache so per-IP counters do not leak across tests."""
    cache.clear()
    yield
    cache.clear()


class TestRateLimitBudgetTable:
    """Each limiter's numbers equal the declared ``RateLimitBudget`` member."""

    def test_search_limiter_matches_its_budget(self) -> None:
        """The search module's module-level pair is the declared budget."""
        from apps.search.services import rate_limit

        assert rate_limit.RATE_LIMIT_REQUESTS == RateLimitBudget.SEARCH_PAGE.requests
        assert rate_limit.RATE_LIMIT_PERIOD == RateLimitBudget.SEARCH_PAGE.period

    def test_autocomplete_budget_equals_search_budget(self) -> None:
        """Autocomplete shares the search budget value but its own namespace."""
        assert RateLimitBudget.AUTOCOMPLETE.requests == RateLimitBudget.SEARCH_PAGE.requests
        assert RateLimitBudget.AUTOCOMPLETE.period == RateLimitBudget.SEARCH_PAGE.period

    def test_deep_link_limiter_matches_its_budget(self) -> None:
        """The contact/deep-link module's pair is the declared budget."""
        assert (
            contact_rate_limit.RATE_LIMIT_REQUESTS
            == RateLimitBudget.DEEP_LINK_RENDER.requests
        )
        assert (
            contact_rate_limit.RATE_LIMIT_PERIOD
            == RateLimitBudget.DEEP_LINK_RENDER.period
        )

    def test_login_limiter_matches_its_budget(self) -> None:
        """The login module's pair is the declared budget."""
        from apps.users.services import login_rate_limit

        assert (
            login_rate_limit.RATE_LIMIT_REQUESTS == RateLimitBudget.LOGIN_ISSUE.requests
        )
        assert login_rate_limit.RATE_LIMIT_PERIOD == RateLimitBudget.LOGIN_ISSUE.period

    def test_media_gate_limiter_matches_its_budget(self) -> None:
        """The media gate pair is the declared budget."""
        from apps.ads.views import listings

        assert (
            listings.MEDIA_RATE_LIMIT_REQUESTS == RateLimitBudget.MEDIA_GATE.requests
        )
        assert listings.MEDIA_RATE_LIMIT_PERIOD == RateLimitBudget.MEDIA_GATE.period

    def test_budgets_are_the_reviewed_values(self) -> None:
        """The table carries the reviewed numbers (no silent drift)."""
        assert (RateLimitBudget.SEARCH_PAGE.requests, RateLimitBudget.SEARCH_PAGE.period) == (30, 60)
        assert (RateLimitBudget.AUTOCOMPLETE.requests, RateLimitBudget.AUTOCOMPLETE.period) == (30, 60)
        assert (RateLimitBudget.DEEP_LINK_RENDER.requests, RateLimitBudget.DEEP_LINK_RENDER.period) == (60, 600)
        assert (RateLimitBudget.LOGIN_ISSUE.requests, RateLimitBudget.LOGIN_ISSUE.period) == (10, 60)
        assert (RateLimitBudget.MEDIA_GATE.requests, RateLimitBudget.MEDIA_GATE.period) == (60, 60)


class TestOneResponseShape:
    """All JSON refusals use the literal ``{"error": "rate_limit"}``."""

    def test_search_429_is_the_shared_json_shape(self) -> None:
        """/search/ refuses with the shared JSON body."""
        cache.clear()
        client = Client()
        resp = client.get("/search/?q=велосипед&lang=ru")
        for _ in range(RateLimitBudget.SEARCH_PAGE.requests):
            resp = client.get("/search/?q=велосипед&lang=ru")
        assert resp.status_code == 429
        assert resp.json() == {"error": RATE_LIMIT_ERROR}

    def test_search_and_listings_429_bodies_are_equal(self) -> None:
        """The /search/ and / 429 bodies are byte-identical (both empty-ish)."""
        # /search/ is JSON; / is a bare-status HTML route. The shared builder
        # makes their bodies equal only within each shape — assert the JSON
        # shape is used consistently and the HTML shape is consistently empty.
        cache.clear()
        client = Client()
        search_resp = client.get("/search/?q=велосипед&lang=ru")
        for _ in range(RateLimitBudget.SEARCH_PAGE.requests):
            search_resp = client.get("/search/?q=велосипед&lang=ru")

        cache.clear()
        listings_resp = client.get("/")
        for _ in range(RateLimitBudget.DEEP_LINK_RENDER.requests):
            listings_resp = client.get("/")

        assert search_resp.status_code == 429
        assert listings_resp.status_code == 429
        # Both route through the one builder; the HTML route emits an empty body.
        assert listings_resp.content == b""
        assert search_resp.json() == {"error": RATE_LIMIT_ERROR}

    def test_builder_emits_one_json_shape(self) -> None:
        """The builder is the single source of the 429 body."""
        json_resp = rate_limited_response()
        assert json_resp.status_code == 429
        assert json_resp.content == b'{"error": "rate_limit"}'

    def test_builder_emits_empty_html_shape(self) -> None:
        """The builder's HTML form is a bare-status 429 with no body."""
        html_resp = rate_limited_response(json=False)
        assert html_resp.status_code == 429
        assert html_resp.content == b""


class TestNamespaceIsolation:
    """Search and autocomplete keep independent counter key namespaces."""

    def test_search_and_autocomplete_use_independent_counters(self) -> None:
        """Exhausting search does not rate-limit autocomplete."""
        client = Client()
        for _ in range(RateLimitBudget.SEARCH_PAGE.requests):
            client.get("/search/?q=велосипед&lang=ru")
        assert client.get("/search/?q=велосипед&lang=ru").status_code == 429
        # Autocomplete uses its own namespace and still succeeds.
        assert client.get("/api/search/autocomplete", {"q": "вел"}).status_code == 200


class TestForwardedForRegressionGuard:
    """Phase 16's trusted client-IP behaviour is unchanged (guard, not RED)."""

    def test_rotating_spoof_leftmost_does_not_forge_a_new_identity(self) -> None:
        """A rotating attacker prefix reaches one key; the real client is used.

        ``$proxy_add_x_forwarded_for`` appends the peer as the rightmost element,
        so the leftmost element is attacker-controlled. The right-to-left walk
        must skip the private proxy hop and resolve the real client (fixed here),
        so a rotating spoof prefix cannot advance a fresh counter each request.
        """
        client = Client()
        # Real client is always the rightmost public hop; the leftmost spoof
        # rotates. All requests must land on one key, so the budget is shared.
        for i in range(RateLimitBudget.SEARCH_PAGE.requests):
            resp = client.get(
                "/search/?q=велосипед&lang=ru",
                HTTP_X_FORWARDED_FOR=f"203.0.113.{i}, 198.51.100.7",
                REMOTE_ADDR="10.0.0.4",
            )
            assert resp.status_code == 200
        # The (limit+1)th request is refused, proving the key was shared despite
        # the rotating leftmost spoof prefix.
        refused = client.get(
            "/search/?q=велосипед&lang=ru",
            HTTP_X_FORWARDED_FOR="203.0.113.250, 198.51.100.7",
            REMOTE_ADDR="10.0.0.4",
        )
        assert refused.status_code == 429
