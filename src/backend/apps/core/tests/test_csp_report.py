"""
Tests for the CSP report endpoint.

Verifies the Content-Security-Policy-Report-Only violation receiver:
- Rejects non-POST methods with 405
- Accepts valid JSON reports with 200
- Rejects malformed JSON with 400
- Rejects missing 'csp-report' key with 400
- Rejects non-dict 'csp-report' value with 400
- Logs valid reports at INFO level (not WARNING)
- Accepts complete CSP reports with all standard fields

No database interaction required.
"""

from __future__ import annotations

import json
import logging

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


def test_post_missing_csp_report_key_returns_400(
    client: Client, csp_url: str
) -> None:
    """POST where the JSON body lacks the 'csp-report' key returns 400."""
    body = json.dumps({"some-other-key": "value"}).encode()
    response = client.post(
        csp_url,
        data=body,
        content_type="application/json",
    )
    assert response.status_code == 400

    response = client.post(
        csp_url,
        data=b"{}",
        content_type="application/json",
    )
    assert response.status_code == 400


def test_post_non_dict_csp_report_value_returns_400(
    client: Client, csp_url: str
) -> None:
    """POST where 'csp-report' is not a JSON object returns 400."""
    response = client.post(
        csp_url,
        data=json.dumps({"csp-report": "not-a-dict"}).encode(),
        content_type="application/json",
    )
    assert response.status_code == 400

    response = client.post(
        csp_url,
        data=json.dumps({"csp-report": ["array"]}).encode(),
        content_type="application/json",
    )
    assert response.status_code == 400


def test_post_valid_report_logs_at_info_level(
    client: Client,
    csp_url: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Valid reports are logged at INFO level, not WARNING."""
    caplog.set_level(logging.INFO, logger="apps.core.views")
    body = json.dumps(
        {"csp-report": {"violated-directive": "script-src"}}
    ).encode()
    response = client.post(
        csp_url,
        data=body,
        content_type="application/json",
    )
    assert response.status_code == 200

    info_records = [
        r
        for r in caplog.records
        if r.name == "apps.core.views" and r.levelno == logging.INFO
    ]
    warning_records = [
        r
        for r in caplog.records
        if r.name == "apps.core.views" and r.levelno == logging.WARNING
    ]
    assert len(info_records) >= 1
    assert len(warning_records) == 0


def test_post_valid_report_with_all_fields_returns_200(
    client: Client, csp_url: str
) -> None:
    """POST with a complete CSP report containing all standard fields returns 200."""
    report = {
        "csp-report": {
            "document-uri": "https://example.com/page.html",
            "referrer": "https://example.com/",
            "violated-directive": "script-src 'self'",
            "blocked-uri": "https://evil.com/script.js",
            "original-policy": "default-src 'self'; script-src 'self'",
            "status-code": 200,
            "source-file": "https://example.com/page.html",
            "line-number": 10,
            "column-number": 5,
            "disposition": "report",
        }
    }
    body = json.dumps(report).encode()
    response = client.post(
        csp_url,
        data=body,
        content_type="application/json",
    )
    assert response.status_code == 200
    assert json.loads(response.content) == {"status": "ok"}


def test_post_invalid_csp_report_field_returns_422(
    client: Client, csp_url: str
) -> None:
    """A CSPReportPayload field-type mismatch returns 422 (DTO validation)."""
    payload = {"csp-report": {"document-uri": 123}}  # wrong type for document-uri
    response = client.post(
        csp_url,
        data=json.dumps(payload).encode(),
        content_type="application/json",
    )
    assert response.status_code == 422
    data = json.loads(response.content)
    assert data["error"]
    assert "errors" in data


def _info_message(caplog: pytest.LogCaptureFixture) -> str:
    """Return the joined text of INFO records emitted by ``apps.core.views``."""
    return "\n".join(
        r.getMessage()
        for r in caplog.records
        if r.name == "apps.core.views" and r.levelno == logging.INFO
    )


def test_document_uri_query_string_never_reaches_the_log(
    client: Client,
    csp_url: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``document-uri``'s query string is not logged (09-API-015).

    A violation on a search-results page carries the buyer's own query in the
    query string; the endpoint is unauthenticated, so that text must never reach
    the log stream.
    """
    caplog.set_level(logging.INFO, logger="apps.core.views")
    body = json.dumps(
        {
            "csp-report": {
                "document-uri": "https://site.example/search/?q=buyer-secret-text",
                "violated-directive": "script-src",
            }
        }
    ).encode()
    response = client.post(csp_url, data=body, content_type="application/json")
    assert response.status_code == 200

    message = _info_message(caplog)
    assert message, "an INFO record must still be emitted"
    assert "buyer-secret-text" not in message
    assert "?" not in message


def test_referrer_never_reaches_the_log(
    client: Client,
    csp_url: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``referrer`` is not logged at all (09-API-015)."""
    caplog.set_level(logging.INFO, logger="apps.core.views")
    body = json.dumps(
        {
            "csp-report": {
                "document-uri": "https://site.example/page",
                "referrer": "https://site.example/search/?q=referrer-secret",
                "violated-directive": "script-src",
            }
        }
    ).encode()
    response = client.post(csp_url, data=body, content_type="application/json")
    assert response.status_code == 200

    message = _info_message(caplog)
    assert "referrer-secret" not in message
    assert "referrer" not in message.lower()
    # The whole-dict dump is gone: the old log line rendered the report mapping
    # verbatim, which carried every field including ``referrer``.
    assert "{'csp-report'" not in message


def test_operator_actionable_fields_are_still_logged(
    client: Client,
    csp_url: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The fields an operator acts on survive the narrowing (09-API-015 test 4).

    A blanket "log nothing" passes the PII tests and destroys triage; this is
    the control that keeps the sink useful. ``blocked-uri`` and ``document-uri``
    are reduced to host + path, so their query strings are absent but their
    hosts remain.
    """
    caplog.set_level(logging.INFO, logger="apps.core.views")
    body = json.dumps(
        {
            "csp-report": {
                "document-uri": "https://site.example/page?q=secret",
                "violated-directive": "script-src 'self'",
                "effective-directive": "script-src",
                "disposition": "report",
                "blocked-uri": "https://evil.example/x.js?v=1",
                "sample": "alert(1)",
            }
        }
    ).encode()
    response = client.post(csp_url, data=body, content_type="application/json")
    assert response.status_code == 200

    message = _info_message(caplog)
    assert "script-src 'self'" in message
    assert "effective=script-src" in message
    assert "disposition=report" in message
    assert "https://evil.example/x.js" in message
    assert "alert(1)" in message
    assert "site.example/page" in message

    warning_records = [
        r
        for r in caplog.records
        if r.name == "apps.core.views" and r.levelno == logging.WARNING
    ]
    assert len(warning_records) == 0

