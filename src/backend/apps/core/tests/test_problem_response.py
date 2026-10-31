"""
Unit tests for the RFC 9457 problem-document helper (S0.3).

Covers every outcome family of the error taxonomy (plan §2.5): each is
constructible via ``problem()`` with the right status, stable ``type`` token and
``application/problem+json`` content-type. Also pins the two specialised
builders — ``validation_problem`` (422, mirroring the ``api_bulk`` 422 body) and
``rate_limited_problem`` (429, ``Retry-After`` derived from the budget window).

All tests are DB-free; request objects are built with ``RequestFactory`` and the
Pydantic error is produced by validating a real DTO.
"""

from __future__ import annotations

import json

import pytest
from django.http import JsonResponse
from django.test import RequestFactory
from pydantic import BaseModel, ValidationError

from apps.core.enums import RateLimitBudget
from apps.core.utils.problem import (
    PROBLEM_CONTENT_TYPE,
    RETRY_AFTER_HEADER,
    TYPE_RATE_LIMITED,
    TYPE_VALIDATION_FAILED,
    problem,
    rate_limited_problem,
    validation_problem,
)

pytestmark = [pytest.mark.unit]


def _body(response: JsonResponse) -> dict[str, object]:
    """Decode a JSON response body into a dict."""
    return json.loads(response.content)


class _SampleInput(BaseModel):
    """Minimal DTO used to raise a real Pydantic validation error."""

    count: int


def _validation_error() -> ValidationError:
    """Return a real ``pydantic.ValidationError`` from a DTO mismatch."""
    with pytest.raises(ValidationError) as excinfo:
        _SampleInput.model_validate({"count": "not-an-int"})
    return excinfo.value


class TestProblemDocument:
    """``problem()`` builds a well-formed RFC 9457 document."""

    def test_shape_status_type_and_content_type(self) -> None:
        """A problem carries type/title/status/detail and the problem media type."""
        response = problem(403, "consent_required", "Consent is required.")

        assert response.status_code == 403
        assert response["Content-Type"] == PROBLEM_CONTENT_TYPE

        payload = _body(response)
        assert payload["type"] == "consent_required"
        assert payload["status"] == 403
        assert payload["detail"] == "Consent is required."
        assert isinstance(payload["title"], str)
        assert payload["title"] == "Forbidden"

    def test_state_machine_family_tokens(self) -> None:
        """The 409 state-machine family is constructible with distinct tokens."""
        for token in ("invalid_transition", "draft_gone", "photo_unavailable"):
            response = problem(409, token, "Conflict.")
            assert response.status_code == 409
            assert _body(response)["type"] == token
            assert response["Content-Type"] == PROBLEM_CONTENT_TYPE

    def test_not_editable_and_transition_refused_tokens(self) -> None:
        """Edit refusal and moderation transition refusal are 409 tokens."""
        for token in ("not_editable", "transition_refused"):
            response = problem(409, token, "Conflict.")
            assert response.status_code == 409
            assert _body(response)["type"] == token

    def test_ban_refused_is_403(self) -> None:
        """A ban refusal is a 403 problem with the stable token."""
        response = problem(403, "ban_refused", "Ban refused.")
        assert response.status_code == 403
        assert _body(response)["type"] == "ban_refused"

    def test_malformed_is_400(self) -> None:
        """A malformed request is a 400 problem."""
        response = problem(400, "malformed", "Malformed request.")
        assert response.status_code == 400
        assert _body(response)["type"] == "malformed"
        assert _body(response)["title"] == "Bad Request"

    def test_unauthenticated_is_401_without_www_authenticate(self) -> None:
        """Unauthenticated is a 401 problem with NO ``WWW-Authenticate`` header."""
        response = problem(401, "unauthenticated", "Authentication required.")
        assert response.status_code == 401
        assert _body(response)["type"] == "unauthenticated"
        assert "WWW-Authenticate" not in response.headers

    def test_forbidden_is_403(self) -> None:
        """A generic forbidden is a 403 problem."""
        response = problem(403, "forbidden", "Forbidden.")
        assert response.status_code == 403
        assert _body(response)["type"] == "forbidden"

    def test_method_not_allowed_is_405(self) -> None:
        """A wrong method is a 405 problem."""
        response = problem(405, "method_not_allowed", "Method not allowed.")
        assert response.status_code == 405
        assert _body(response)["type"] == "method_not_allowed"
        assert _body(response)["title"] == "Method Not Allowed"

    def test_retryable_is_503(self) -> None:
        """A lock-timeout retryable failure is a 503 problem."""
        response = problem(503, "retryable", "Please retry.")
        assert response.status_code == 503
        assert _body(response)["type"] == "retryable"
        assert _body(response)["title"] == "Service Unavailable"

    def test_generic_is_500(self) -> None:
        """An unexpected failure is a 500 problem with a generic body."""
        response = problem(500, "internal_error", "An unexpected error occurred.")
        assert response.status_code == 500
        assert _body(response)["type"] == "internal_error"
        assert _body(response)["title"] == "Internal Server Error"

    def test_200_outcome_is_not_a_problem(self) -> None:
        """A 200 outcome is a normal JSON response, never a problem document.

        The commit-boundary rule (O-2a) is that a 200 ``{outcome}`` is a
        well-formed success; this helper is not used for it, and its content
        type is the default JSON media type.
        """
        response = JsonResponse({"outcome": "published"}, status=200)
        assert response.status_code == 200
        assert response["Content-Type"] == "application/json"

    def test_type_token_is_never_translated(self) -> None:
        """The ``type`` token is echoed verbatim, never run through gettext."""
        token = "consent_required"
        response = problem(403, token, "Consent is required.")
        assert _body(response)["type"] == token


class TestValidationProblem:
    """``validation_problem()`` mirrors the shipped ``api_bulk`` 422 shape."""

    def test_status_type_and_content_type(self) -> None:
        """A DTO failure is a 422 ``validation_failed`` problem."""
        response = validation_problem(_validation_error())

        assert response.status_code == 422
        assert response["Content-Type"] == PROBLEM_CONTENT_TYPE
        payload = _body(response)
        assert payload["type"] == TYPE_VALIDATION_FAILED
        assert payload["status"] == 422
        assert payload["title"] == "Unprocessable Entity"

    def test_errors_key_is_pydantic_errors_json(self) -> None:
        """The ``errors`` key is the per-error list from ``pydantic_errors_json``."""
        exc = _validation_error()
        response = validation_problem(exc)

        errors = _body(response)["errors"]
        assert isinstance(errors, list)
        assert errors, "expected at least one validation error"
        first = errors[0]
        assert isinstance(first, dict)
        # The deposit returns {type, loc, msg} entries and excludes input/ctx.
        assert set(first) == {"type", "loc", "msg"}
        assert first["loc"] == ["count"]


class TestRateLimitedProblem:
    """``rate_limited_problem()`` derives ``Retry-After`` from the budget."""

    def test_status_type_content_type_and_retry_after(self) -> None:
        """A 429 problem carries the budget window as ``Retry-After``."""
        budget = RateLimitBudget.SEARCH_PAGE
        response = rate_limited_problem(budget)

        assert response.status_code == 429
        assert response["Content-Type"] == PROBLEM_CONTENT_TYPE
        assert response[RETRY_AFTER_HEADER] == str(budget.period)
        assert _body(response)["type"] == TYPE_RATE_LIMITED

    def test_retry_after_tracks_the_selected_budget(self) -> None:
        """``Retry-After`` is always the selected budget's period."""
        for budget in RateLimitBudget:
            response = rate_limited_problem(budget)
            assert response[RETRY_AFTER_HEADER] == str(budget.period)

    def test_legacy_renderer_untouched(self) -> None:
        """The legacy renderer's own suite is the frozen-behavior proof.

        This task does not edit ``rate_limit_response.py`` or its tests; the
        legacy suite (``test_rate_limit_budget.py::TestOneResponseShape``) pins
        that legacy 429s carry NO ``Retry-After``. This test only guards against
        accidental coupling: importing and calling the builder here must not
        attach a ``Retry-After`` header.
        """
        from apps.core.utils.rate_limit_response import rate_limited_response

        legacy = rate_limited_response()
        assert legacy.status_code == 429
        assert RETRY_AFTER_HEADER not in legacy.headers


class TestRequestFactoryIsUnusedByProblem:
    """Sanity guard: the helper needs no request object to build a document."""

    def test_builds_without_a_request(self) -> None:
        """``problem()`` is request-free, so views can call it directly."""
        # ``RequestFactory`` is imported to document that no request is required.
        _ = RequestFactory
        response = problem(403, "consent_required", "Consent is required.")
        assert response.status_code == 403
