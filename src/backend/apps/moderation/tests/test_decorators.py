"""
Direct unit tests for moderation view decorators.

Covers both ``staff_required`` (template views → Http404 for non-staff) and
``staff_required_api`` (JSON API → 403 JSON for non-staff, 405 for wrong method).
All tests are DB-free (no persistence required) except where a User/Permission
instance is needed for authentication attributes — those use ``@pytest.mark.unit``
without ``django_db``.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from django.http import Http404, JsonResponse

from apps.moderation.views.decorators import staff_required, staff_required_api

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request(method: str = "GET", is_staff: bool = False, is_superuser: bool = False) -> MagicMock:
    """Build a request mock with the desired user auth attributes."""
    request = MagicMock()
    request.method = method
    user = MagicMock()
    user.is_staff = is_staff
    user.is_superuser = is_superuser
    request.user = user
    return request


# ---------------------------------------------------------------------------
# staff_required
# ---------------------------------------------------------------------------


class TestStaffRequired:
    """Tests for ``staff_required`` template-view decorator."""

    def test_non_staff_user_raises_404(self) -> None:
        """A non-staff, non-superuser request raises Http404 (URL-leak prevention)."""
        request = _make_request(is_staff=False, is_superuser=False)

        @staff_required
        def view(request: object) -> str:
            return "should not reach"

        with pytest.raises(Http404, match="Not found"):
            view(request)

    def test_staff_user_passthrough(self) -> None:
        """A staff user reaches the wrapped view body."""
        request = _make_request(is_staff=True)

        @staff_required
        def view(request: object) -> str:
            return "ok"

        assert view(request) == "ok"

    def test_superuser_passthrough(self) -> None:
        """A superuser reaches the wrapped view body even without is_staff."""
        request = _make_request(is_staff=False, is_superuser=True)

        @staff_required
        def view(request: object) -> str:
            return "ok"

        assert view(request) == "ok"

    def test_superuser_without_staff_flag_still_passthrough(self) -> None:
        """Superuser=True alone is sufficient (is_staff may be False)."""

        @staff_required
        def view(request: object) -> str:
            return "reached"

        assert view(_make_request(is_superuser=True)) == "reached"


# ---------------------------------------------------------------------------
# staff_required_api
# ---------------------------------------------------------------------------


class TestStaffRequiredApi:
    """Tests for ``staff_required_api`` JSON API decorator."""

    def test_non_staff_returns_403_json(self) -> None:
        """A non-staff user gets a 403 JSON response."""
        request = _make_request(method="POST", is_staff=False)

        @staff_required_api
        def view(request: object) -> JsonResponse:
            return JsonResponse({"ok": True})

        response = view(request)
        assert response.status_code == 403
        assert json.loads(response.content) == {"error": "Unauthorized"}

    def test_staff_get_returns_405(self) -> None:
        """A staff user using GET (wrong method) gets a 405 JSON response."""
        request = _make_request(method="GET", is_staff=True)

        @staff_required_api
        def view(request: object) -> JsonResponse:
            return JsonResponse({"ok": True})

        response = view(request)
        assert response.status_code == 405
        assert json.loads(response.content) == {"error": "POST required"}

    def test_staff_post_passthrough(self) -> None:
        """A staff user with POST reaches the wrapped view body."""
        request = _make_request(method="POST", is_staff=True)

        @staff_required_api
        def view(request: object) -> JsonResponse:
            return JsonResponse({"ok": True})

        response = view(request)
        assert response.status_code == 200
        assert json.loads(response.content) == {"ok": True}

    def test_superuser_post_passthrough(self) -> None:
        """A superuser with POST reaches the wrapped view body."""
        request = _make_request(method="POST", is_superuser=True)

        @staff_required_api
        def view(request: object) -> JsonResponse:
            return JsonResponse({"ok": True})

        response = view(request)
        assert response.status_code == 200
        assert json.loads(response.content) == {"ok": True}

    def test_non_staff_get_checks_staff_first(self) -> None:
        """For a non-staff GET, the 403 staff check precedes the 405 method check."""
        request = _make_request(method="GET", is_staff=False)

        @staff_required_api
        def view(request: object) -> JsonResponse:
            return JsonResponse({"ok": True})

        response = view(request)
        assert response.status_code == 403
