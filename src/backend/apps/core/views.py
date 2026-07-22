"""Core application views."""

from django.db import connection
from django.http import JsonResponse


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