"""
Tests for PreferredCityMiddleware resolution priority and stale-cookie cleanup.

Mirrors ``test_language_middleware.py`` (SimpleTestCase, minimal ``HttpRequest``
helper). Because the middleware reads ``City.objects`` (a DB lookup), the
``City`` model is mocked so no database connection is required.

Behavior covered:
- authenticated with DB preference -> DB slug wins over cookie (AC-1)
- anonymous with valid cookie -> cookie slug (AC-2)
- absent cookie -> ``None``
- stale cookie -> ``None`` + cookie deleted in ``process_response`` (AC-4)
- no crash when ``request.user`` is absent (ordering guard)
- no cookie write happens here (writes are the endpoint's job)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest, HttpResponse

from apps.core.middleware.preferred_city import (
    PREFERRED_CITY_COOKIE_NAME,
    PreferredCityMiddleware,
)

pytestmark = [pytest.mark.unit]


def _make_request(
    cookies: dict | None = None,
    user: object | None = None,
) -> HttpRequest:
    """Create a minimal HttpRequest with the given attributes."""
    request = HttpRequest()
    request.COOKIES = cookies or {}
    # ``user`` defaults to an anonymous user (mimics AuthenticationMiddleware).
    request.user = user if user is not None else AnonymousUser()
    return request


@pytest.fixture
def middleware() -> PreferredCityMiddleware:
    """Instantiate middleware once per test."""
    return PreferredCityMiddleware(get_response=lambda r: None)


# --- Authenticated: DB wins ---


def test_authenticated_db_wins_over_cookie(middleware: PreferredCityMiddleware) -> None:
    """Authenticated with ``User.preferred_city`` => DB slug (AC-1)."""
    user = MagicMock(is_authenticated=True, preferred_city_id=1)
    user.preferred_city.slug = "podgorica"
    request = _make_request(
        cookies={PREFERRED_CITY_COOKIE_NAME: "budva"},
        user=user,
    )
    middleware.process_request(request)
    assert request.preferred_city == "podgorica"


def test_authenticated_without_db_preference_falls_back_to_cookie(
    middleware: PreferredCityMiddleware,
) -> None:
    """Authenticated with no DB preference => valid cookie slug."""
    user = MagicMock(is_authenticated=True, preferred_city_id=None)
    valid_city = MagicMock()
    valid_city.exists.return_value = True
    with patch(
        "apps.core.middleware.preferred_city.City.objects.filter",
        return_value=valid_city,
    ):
        request = _make_request(
            cookies={PREFERRED_CITY_COOKIE_NAME: "budva"},
            user=user,
        )
        middleware.process_request(request)
        assert request.preferred_city == "budva"


# --- Anonymous: cookie is the default ---


def test_anonymous_valid_cookie(middleware: PreferredCityMiddleware) -> None:
    """Anonymous with a valid cookie slug => cookie slug (AC-2)."""
    valid_city = MagicMock()
    valid_city.exists.return_value = True
    with patch(
        "apps.core.middleware.preferred_city.City.objects.filter",
        return_value=valid_city,
    ):
        request = _make_request(cookies={PREFERRED_CITY_COOKIE_NAME: "podgorica"})
        middleware.process_request(request)
        assert request.preferred_city == "podgorica"


def test_anonymous_absent_cookie_is_none(middleware: PreferredCityMiddleware) -> None:
    """No cookie => ``request.preferred_city`` is None."""
    request = _make_request()
    middleware.process_request(request)
    assert request.preferred_city is None


# --- Stale cookie ---


def test_anonymous_stale_cookie_is_none(middleware: PreferredCityMiddleware) -> None:
    """Cookie referencing a deleted city => ``None`` (AC-4)."""
    stale_city = MagicMock()
    stale_city.exists.return_value = False
    with patch(
        "apps.core.middleware.preferred_city.City.objects.filter",
        return_value=stale_city,
    ):
        request = _make_request(cookies={PREFERRED_CITY_COOKIE_NAME: "old-city"})
        middleware.process_request(request)
        assert request.preferred_city is None
        assert request._preferred_city_stale_cookie is True


def test_stale_cookie_deleted_in_response(middleware: PreferredCityMiddleware) -> None:
    """A stale cookie is deleted in ``process_response`` (AC-4)."""
    stale_city = MagicMock()
    stale_city.exists.return_value = False
    request = _make_request(cookies={PREFERRED_CITY_COOKIE_NAME: "old-city"})
    response = HttpResponse()
    with patch(
        "apps.core.middleware.preferred_city.City.objects.filter",
        return_value=stale_city,
    ):
        middleware.process_request(request)
        middleware.process_response(request, response)
    # ``delete_cookie`` is reflected in response.cookies (max-age 0).
    assert PREFERRED_CITY_COOKIE_NAME in response.cookies
    assert response.cookies[PREFERRED_CITY_COOKIE_NAME].value == ""


def test_valid_cookie_not_deleted(middleware: PreferredCityMiddleware) -> None:
    """A valid cookie is NOT deleted in ``process_response``."""
    valid_city = MagicMock()
    valid_city.exists.return_value = True
    request = _make_request(cookies={PREFERRED_CITY_COOKIE_NAME: "podgorica"})
    response = HttpResponse()
    with patch(
        "apps.core.middleware.preferred_city.City.objects.filter",
        return_value=valid_city,
    ):
        middleware.process_request(request)
        middleware.process_response(request, response)
    assert PREFERRED_CITY_COOKIE_NAME not in response.cookies


# --- Ordering guard ---


def test_no_crash_when_user_absent(middleware: PreferredCityMiddleware) -> None:
    """Must not crash when ``request.user`` is absent (ordering guard)."""
    request = _make_request(cookies={PREFERRED_CITY_COOKIE_NAME: "podgorica"})
    # Deliberately remove ``user`` to simulate AuthenticationMiddleware not
    # having run yet.
    del request.user
    valid_city = MagicMock()
    valid_city.exists.return_value = True
    with patch(
        "apps.core.middleware.preferred_city.City.objects.filter",
        return_value=valid_city,
    ):
        middleware.process_request(request)
    assert request.preferred_city == "podgorica"


# --- No write here ---


def test_middleware_never_writes_cookie(middleware: PreferredCityMiddleware) -> None:
    """Middleware only resolves/cleans; it never writes the cookie."""
    request = _make_request(cookies={PREFERRED_CITY_COOKIE_NAME: "podgorica"})
    response = HttpResponse()
    with patch(
        "apps.core.middleware.preferred_city.City.objects.filter",
        return_value=MagicMock(exists=MagicMock(return_value=True)),
    ):
        middleware.process_request(request)
        middleware.process_response(request, response)
    # No cookie set in the response.
    assert len(response.cookies) == 0
