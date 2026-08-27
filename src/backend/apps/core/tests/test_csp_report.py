"""
Tests for the CSP report endpoint.

Verifies the Content-Security-Policy-Report-Only violation receiver:
- Rejects non-POST methods with 405
- Accepts valid JSON reports with 200
- Rejects malformed JSON with 400

No database interaction required.
"""

from __future__ import annotations

import json

import pytest
from django.test import Client
from django.urls import reverse

pytestmark = [pytest.mark.unit]


@pytest.fixture
def csp_url() -> str:
    return reverse("core:csp_report")


def test_get_returns_405(client: Client, csp_url: str) -> None:
    """GET requests are rejected with 405 Method Not Allowed."""
    response = client.get(csp_url)
    assert response.status_code == 405


def test_post_valid_report_returns_200(client: Client, csp_url: str) -> None:
    """POST with valid JSON body returns 200 and ok status."""
    body = json.dumps({"csp-report": {"violated-directive": "script-src"}}).encode()
    response = client.post(
        csp_url,
        data=body,
        content_type="application/json",
    )
    assert response.status_code == 200
    assert json.loads(response.content) == {"status": "ok"}


def test_post_invalid_json_returns_400(client: Client, csp_url: str) -> None:
    """POST with malformed JSON returns 400 Bad Request."""
    response = client.post(
        csp_url,
        data=b"not json",
        content_type="application/json",
    )
    assert response.status_code == 400
