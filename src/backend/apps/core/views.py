"""Core application views."""

import json
import logging

from django.db import connection
from django.http import HttpRequest, JsonResponse

logger = logging.getLogger(__name__)


def health_check(request):
    """Health check endpoint for container orchestration.

    Returns HTTP 200 with status if healthy, HTTP 503 if unhealthy.
    Includes database connectivity check.
    """
    db_healthy = True
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        db_healthy = False

    if db_healthy:
        return JsonResponse({"status": "healthy"})
    return JsonResponse({"status": "unhealthy"}, status=503)


def csp_report(request: HttpRequest) -> JsonResponse:
    """Receive CSP violation reports from browsers.

    Report-Only mode: browsers send violation reports to this endpoint.
    Reports are logged for monitoring. No CSP is enforced at this stage.
    """
    if request.method != "POST":
        return JsonResponse(
            {"status": "error", "error": "POST required"}, status=405,
        )
    try:
        report = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    logger.warning("CSP violation report: %s", report)
    return JsonResponse({"status": "ok"})