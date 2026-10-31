"""
Unit tests for ``login_required_api`` (S0.4).

Mirrors the ``staff_required_api`` test pattern
(``apps/moderation/tests/test_decorators.py``): a ``MagicMock`` request carrying
the auth attributes is passed to the decorated view, so no database or URL
routing is needed.

Pins:
- an anonymous request gets a 401 RFC 9457 problem document (both GET and POST);
- the refusal carries **no** ``WWW-Authenticate`` header;
- identity is checked before the method (anonymous POST → 401, not 405);
- an authenticated request reaches the wrapped view body.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from django.http import JsonResponse

from apps.core.utils.api_auth import TYPE_UNAUTHENTICATED, login_required_api

pytestmark = [pytest.mark.unit]


def _make_request(
    method: str = "GET",
    is_authenticated: bool = True,
) -> MagicMock:
    """Build a request mock with the desired user auth attributes."""
    request = MagicMock()
    request.method = method
    user = MagicMock()
    user.is_authenticated = is_authenticated
    request.user = user
    return request


class TestLoginRequiredApi:
    """Tests for the ``login_required_api`` JSON API decorator."""

    def test_anonymous_get_returns_401_problem(self) -> None:
        """An anonymous GET gets a 401 problem document."""
        request = _make_request(method="GET", is_authenticated=False)

        @login_required_api
        def view(request: object) -> JsonResponse:
            return JsonResponse({"ok": True})

        response = view(request)
        assert response.status_code == 401
        assert response["Content-Type"] == "application/problem+json"
        payload = json.loads(response.content)
        assert payload["type"] == TYPE_UNAUTHENTICATED
        assert payload["status"] == 401
        assert payload["title"] == "Unauthorized"

    def test_anonymous_post_returns_401_problem(self) -> None:
        """An anonymous POST gets a 401 problem document."""
        request = _make_request(method="POST", is_authenticated=False)

        @login_required_api
        def view(request: object) -> JsonResponse:
            return JsonResponse({"ok": True})

        response = view(request)
        assert response.status_code == 401
        assert response["Content-Type"] == "application/problem+json"
        assert json.loads(response.content)["type"] == TYPE_UNAUTHENTICATED

    def test_no_www_authenticate_header(self) -> None:
        """The 401 carries no ``WWW-Authenticate`` challenge (09-API-010)."""
        request = _make_request(method="POST", is_authenticated=False)

        @login_required_api
        def view(request: object) -> JsonResponse:
            return JsonResponse({"ok": True})

        response = view(request)
        assert "WWW-Authenticate" not in response.headers

    def test_identity_before_method_order(self) -> None:
        """An anonymous POST is a 401, proving identity precedes the method check.

        Mirrors ``staff_required_api``: the authn branch runs first, so an
        anonymous POST is refused as unauthenticated rather than as a wrong
        method. Phase 15 owns any reorder of this branch sequence.
        """
        request = _make_request(method="POST", is_authenticated=False)

        @login_required_api
        def view(request: object) -> JsonResponse:
            return JsonResponse({"ok": True})

        response = view(request)
        assert response.status_code == 401
        assert response.status_code != 405

    def test_authenticated_get_passthrough(self) -> None:
        """An authenticated GET reaches the wrapped view body."""
        request = _make_request(method="GET", is_authenticated=True)

        @login_required_api
        def view(request: object) -> JsonResponse:
            return JsonResponse({"ok": True})

        response = view(request)
        assert response.status_code == 200
        assert json.loads(response.content) == {"ok": True}

    def test_authenticated_post_passthrough(self) -> None:
        """An authenticated POST reaches the wrapped view body."""
        request = _make_request(method="POST", is_authenticated=True)

        @login_required_api
        def view(request: object) -> JsonResponse:
            return JsonResponse({"ok": True})

        response = view(request)
        assert response.status_code == 200
        assert json.loads(response.content) == {"ok": True}

    def test_preserves_wrapped_view_identity(self) -> None:
        """``functools.wraps`` preserves the wrapped view's name."""

        @login_required_api
        def my_view(request: object) -> JsonResponse:
            return JsonResponse({"ok": True})

        assert my_view.__name__ == "my_view"
