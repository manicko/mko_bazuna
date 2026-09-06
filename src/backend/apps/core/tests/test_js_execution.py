"""
Tests for the JS-execution proof gate (Spec 18, CR-11).

Covers:
- ``JSExecutionMiddleware.process_request`` sets ``request.js_verified`` based on
  the ``js`` cookie value (``"true"`` only).
- ``js_verified(request)`` context processor bridges the attribute into the
  template context, defaulting to ``True`` when the middleware did not run.

These are pure unit tests — no database access required.
"""

from __future__ import annotations

import pytest
from django.http import HttpRequest

from apps.core.context_processors import js_verified
from apps.core.middleware.js_check import JSExecutionMiddleware

pytestmark = [pytest.mark.unit]


def _make_request(cookies: dict | None = None) -> HttpRequest:
    """Build a minimal ``HttpRequest`` with the given cookies."""
    request = HttpRequest()
    request.COOKIES = cookies or {}
    return request


@pytest.fixture
def middleware() -> JSExecutionMiddleware:
    """Instantiate the middleware once per test."""
    return JSExecutionMiddleware(get_response=lambda r: None)


# ---------------------------------------------------------------------------
# JSExecutionMiddleware
# ---------------------------------------------------------------------------


def test_js_verified_true_when_cookie_is_true(middleware: JSExecutionMiddleware) -> None:
    """``js=true`` cookie => ``request.js_verified`` is True."""
    request = _make_request(cookies={"js": "true"})
    middleware.process_request(request)
    assert request.js_verified is True


def test_js_verified_false_when_cookie_absent(middleware: JSExecutionMiddleware) -> None:
    """No ``js`` cookie => ``request.js_verified`` is False (scraper rejection)."""
    request = _make_request()
    middleware.process_request(request)
    assert request.js_verified is False


def test_js_verified_false_when_cookie_is_false(
    middleware: JSExecutionMiddleware,
) -> None:
    """``js=false`` is rejected — only the literal ``"true"`` clears the gate."""
    request = _make_request(cookies={"js": "false"})
    middleware.process_request(request)
    assert request.js_verified is False


def test_js_verified_false_when_cookie_is_garbage(
    middleware: JSExecutionMiddleware,
) -> None:
    """Arbitrary cookie values do not clear the gate."""
    request = _make_request(cookies={"js": "1"})
    middleware.process_request(request)
    assert request.js_verified is False


# ---------------------------------------------------------------------------
# js_verified context processor
# ---------------------------------------------------------------------------


def test_context_processor_true_when_request_verified() -> None:
    """``js_verified`` context processor forwards a ``True`` attribute."""
    request = _make_request(cookies={"js": "true"})
    middleware = JSExecutionMiddleware(get_response=lambda r: None)
    middleware.process_request(request)
    assert js_verified(request) == {"js_verified": True}


def test_context_processor_false_when_request_not_verified() -> None:
    """``js_verified`` context processor forwards a ``False`` attribute."""
    request = _make_request()
    middleware = JSExecutionMiddleware(get_response=lambda r: None)
    middleware.process_request(request)
    assert js_verified(request) == {"js_verified": False}


def test_context_processor_defaults_to_true_when_attr_missing() -> None:
    """When middleware did not run, the processor defaults to ``True``.

    This keeps links functional outside the request cycle (management
    commands, direct tag invocation) rather than silently gating them.
    """
    request = _make_request()
    # ``js_verified`` attribute is absent (no middleware ran).
    assert js_verified(request) == {"js_verified": True}
