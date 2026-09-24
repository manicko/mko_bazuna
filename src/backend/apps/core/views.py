"""Core application views."""

from __future__ import annotations

import json
import logging
from time import time as _time

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from apps.core.utils.sanitize import pydantic_errors_json

logger = logging.getLogger(__name__)


class CSPReportPayload(BaseModel):
    """Pydantic v2 DTO for validating Content-Security-Policy violation reports.

    Browsers send reports as a JSON object whose top-level key is
    ``csp-report``.  This model validates each inner field.  All fields are
    optional so minimal reports (e.g. only ``violated-directive``) are accepted.
    ``extra="ignore"`` tolerates future/spec-variation keys without failing.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    document_uri: str | None = Field(default=None, alias="document-uri")
    referrer: str | None = None
    violated_directive: str | None = Field(default=None, alias="violated-directive")
    blocked_uri: str | None = Field(default=None, alias="blocked-uri")
    original_policy: str | None = Field(default=None, alias="original-policy")
    status_code: int | str | None = Field(default=None, alias="status-code")
    source_file: str | None = Field(default=None, alias="source-file")
    line_number: int | None = Field(default=None, alias="line-number")
    column_number: int | None = Field(default=None, alias="column-number")
    disposition: str | None = None


def privacy_policy(request: HttpRequest) -> HttpResponse:
    """Render the public privacy policy page (GDPR Article 13).

    Publicly accessible — no authentication required. Discloses the cookie
    declaration, third-party data flows, processing purposes, legal bases,
    user rights, controller contact, and the 30-day erasure policy.

    Args:
        request: HTTP request (anonymous or authenticated).

    Returns:
        Rendered ``templates/privacy.html`` page.
    """
    from apps.core.services.contact_rate_limit import check_deep_link_render_rate_limit

    if not check_deep_link_render_rate_limit(request):
        logger.warning("Deep-link render rate limit exceeded (privacy)")
        return HttpResponse(status=429)

    from apps.core.services.site_config import get_bot_username

    return render(
        request,
        "privacy.html",
        {"bot_username": get_bot_username()},
    )


def liveness_check(request: HttpRequest) -> JsonResponse:
    """Liveness probe — process is alive. No DB or cache dependency."""
    return JsonResponse({"status": "alive"})


def readiness_check(request: HttpRequest) -> JsonResponse:
    """Readiness probe — verifies database and Redis cache health.

    Returns 200 with check details when the required dependencies are healthy,
    503 when any of them fails.

    Bot liveness is a soft/alert dimension, not a web readiness gate by
    default: ``BOT_HEALTH_CHECK_ENABLED`` defaults to ``False``, so the probe
    reports ``checks["bot"] == "disabled"`` and does not gate web readiness on
    the bot. When explicitly enabled (``BOT_HEALTH_CHECK_ENABLED=True``), the
    Redis ``bot:liveness`` key (written by the bot process on startup and on
    every inbound update) is verified: fresh -> ``"ok"``; missing or old ->
    ``"stale"`` and the probe returns 503. The bot's file-based healthcheck
    (``BOT_LIVENESS_FILE``) remains its separate alert mechanism.
    """
    checks = {"database": "ok", "cache": "ok"}

    db_healthy = True
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        db_healthy = False
        checks["database"] = "fail"

    cache_healthy = True
    try:
        cache.set("health_readiness_probe", "ok", timeout=30)
        if cache.get("health_readiness_probe") != "ok":
            cache_healthy = False
            checks["cache"] = "fail"
    except Exception:
        cache_healthy = False
        checks["cache"] = "fail"

    bot_healthy = True
    if not settings.BOT_HEALTH_CHECK_ENABLED:
        checks["bot"] = "disabled"
    else:
        marker_ts = None
        try:
            marker_ts = cache.get("bot:liveness")
        except Exception:
            pass

        if marker_ts is None:
            checks["bot"] = "stale"
            bot_healthy = False
        elif int(_time()) - int(marker_ts) > settings.BOT_HEALTH_STALE_SECONDS:
            checks["bot"] = "stale"
            bot_healthy = False
        else:
            checks["bot"] = "ok"

    if db_healthy and cache_healthy and bot_healthy:
        return JsonResponse(
            {"version": 1, "status": "ready", "checks": checks}
        )
    return JsonResponse(
        {"version": 1, "status": "not_ready", "checks": checks},
        status=503,
    )


def health_check(request: HttpRequest) -> JsonResponse:
    """Backward-compatible alias for readiness_check.

    Kept so existing monitors pointing at /health/ continue to work.
    Returns the readiness response (includes dependency checks).
    """
    return readiness_check(request)


def csp_report(request: HttpRequest) -> JsonResponse:
    """Receive CSP violation reports from browsers.

    Report-Only mode: browsers send violation reports to this endpoint.
    Reports are logged for monitoring. No CSP is enforced at this stage.
    """
    if request.method != "POST":
        return JsonResponse(
            {"status": "error", "error": "POST required"},
            status=405,
        )
    try:
        report = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    if not isinstance(report, dict) or "csp-report" not in report:
        return JsonResponse({"error": "Missing 'csp-report' key"}, status=400)
    if not isinstance(report["csp-report"], dict):
        return JsonResponse({"error": "'csp-report' must be a JSON object"}, status=400)
    try:
        CSPReportPayload(**report["csp-report"])
    except ValidationError as exc:
        logger.warning("Invalid CSP report payload: %s", exc)
        return JsonResponse(
            {
                "error": "Invalid CSP report schema",
                "errors": pydantic_errors_json(exc),
            },
            status=422,
        )
    logger.info("CSP violation report: %s", report)
    return JsonResponse({"status": "ok"})
