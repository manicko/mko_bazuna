"""Core application views."""

import json
import logging

from django.core.cache import cache
from django.db import connection
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render

logger = logging.getLogger(__name__)


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
    """Readiness probe — verifies database and Redis cache are reachable.

    Returns 200 with check details when all dependencies are healthy,
    503 when any dependency fails. Bot health is verified separately
    via the bot container's own healthcheck (healthcheck-bot.sh).
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

    if db_healthy and cache_healthy:
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
    logger.warning("CSP violation report: %s", report)
    return JsonResponse({"status": "ok"})
