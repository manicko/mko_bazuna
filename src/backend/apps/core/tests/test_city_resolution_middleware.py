"""
Tests for CityResolutionMiddleware URL-city resolution.

Verifies that ``request.current_city`` is resolved from the URL slug with
priority: path form ``/city/<slug>/`` > query form ``?city=<slug>`` > ``None``.
The middleware does not query the ``City`` model, does not validate slugs,
and does not touch cookies.

No database interaction required (pure unit tests).
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest

from apps.core.middleware.city_resolution import CityResolutionMiddleware

pytestmark = [pytest.mark.unit]


def _make_request(
    path: str = "/",
    get: dict | None = None,
    cookies: dict | None = None,
) -> HttpRequest:
    """Create a minimal HttpRequest with the given path and query params."""
    request = HttpRequest()
    request.path = path
    request.GET = get or {}
    request.COOKIES = cookies or {}
    # ``user`` mimics AuthenticationMiddleware having run already.
    request.user = AnonymousUser()
    return request


@pytest.fixture
def middleware() -> CityResolutionMiddleware:
    """Instantiate middleware once per test."""
    return CityResolutionMiddleware(get_response=lambda r: None)


# --- Path form ---


def test_path_city_resolved(middleware: CityResolutionMiddleware) -> None:
    """Path form ``/city/budva/`` resolves to ``current_city == "budva"``."""
    request = _make_request(path="/city/budva/")
    middleware.process_request(request)
    assert request.current_city == "budva"


def test_path_city_no_trailing_slash(middleware: CityResolutionMiddleware) -> None:
    """Path form ``/city/budva`` (no trailing slash) resolves to ``current_city``."""
    request = _make_request(path="/city/budva")
    middleware.process_request(request)
    assert request.current_city == "budva"


# --- Query form ---


def test_query_city_resolved(middleware: CityResolutionMiddleware) -> None:
    """Query form ``?city=budva`` resolves to ``current_city == "budva"``."""
    request = _make_request(path="/", get={"city": "budva"})
    middleware.process_request(request)
    assert request.current_city == "budva"


# --- Default / no city ---


def test_no_city_is_none(middleware: CityResolutionMiddleware) -> None:
    """No city in path or query => ``current_city is None``."""
    request = _make_request(path="/")
    middleware.process_request(request)
    assert request.current_city is None


def test_category_path_not_matched(middleware: CityResolutionMiddleware) -> None:
    """A ``/category/...`` path must NOT match the ``/city/<slug>/`` pattern."""
    request = _make_request(path="/category/city-foo/")
    middleware.process_request(request)
    assert request.current_city is None


# --- Priority ---


def test_path_takes_priority_over_query(middleware: CityResolutionMiddleware) -> None:
    """Path form takes priority over ``?city=`` when both are present."""
    request = _make_request(path="/city/bar/", get={"city": "budva"})
    middleware.process_request(request)
    assert request.current_city == "bar"


# --- Contracts: no DB, no cookies ---


def test_cookie_does_not_leak_into_current_city(
    middleware: CityResolutionMiddleware,
) -> None:
    """The ``preferred_city`` cookie is ignored; ``current_city`` stays ``None``."""
    request = _make_request(
        path="/",
        cookies={"preferred_city": "budva"},
    )
    middleware.process_request(request)
    assert request.current_city is None


def test_stale_slug_passthrough(middleware: CityResolutionMiddleware) -> None:
    """An unrecognized slug in the path is passed through unvalidated.

    No ``City`` model lookup is performed by the middleware (CR-7 defers
    validation to the views), so even an invalid slug reaches the view.
    """
    request = _make_request(path="/city/invalid-slug/")
    middleware.process_request(request)
    assert request.current_city == "invalid-slug"
