"""
Tests for the CSP report endpoint.

Verifies the Content-Security-Policy-Report-Only violation receiver:
- Rejects non-POST methods with 405
- Accepts valid JSON reports with 200
- Rejects malformed JSON with 400

No database interaction required — uses Django's SimpleTestCase.
"""

from __future__ import annotations

import json

from django.test import SimpleTestCase
from django.urls import reverse


class CspReportViewTests(SimpleTestCase):
    """Tests for the csp_report view."""

    @property
    def url(self) -> str:
        return reverse("core:csp_report")

    def test_get_returns_405(self) -> None:
        """GET requests are rejected with 405 Method Not Allowed."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    def test_post_valid_report_returns_200(self) -> None:
        """POST with valid JSON body returns 200 and ok status."""
        body = json.dumps({"csp-report": {"violated-directive": "script-src"}}).encode()
        response = self.client.post(
            self.url,
            data=body,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content.decode(), {"status": "ok"})

    def test_post_invalid_json_returns_400(self) -> None:
        """POST with malformed JSON returns 400 Bad Request."""
        response = self.client.post(
            self.url,
            data=b"not json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
