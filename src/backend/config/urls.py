"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
"""

import ipaddress

from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from django.urls import include, path
from django_prometheus.exports import ExportToDjangoView

# The API surface is an internal HTMX/JSON surface for a single-consumer
# frontend. `/api/v1/` is the only versioned prefix (moderation bulk actions);
# versioning the rest is a deliberate non-goal while there is one consumer. See
# docs/01-spec/architecture-structure.md.


def _metrics_gate(request: HttpRequest) -> HttpResponse:
    """Restrict ``/metrics`` to loopback callers in Django (09-API-014).

    nginx already carries ``allow 127.0.0.1; deny all;`` on ``location =
    /metrics``, but that control lives in one file and does not cover a caller
    that reaches the ``web`` container directly across the Docker bridge (a
    sibling container, or dev's published ``8000:8000``). This view is the
    second control: it reads the raw socket peer ``REMOTE_ADDR`` and returns 403
    unless it is a loopback address.

    It reads ``request.META`` directly rather than routing through a private
    ``_get_client_ip`` helper — phase 16 owns that collapse — and it is a plain
    ``urls.py`` view, not middleware, so the 15-entry ``MIDDLEWARE`` list phase
    16 pins is untouched and no per-request tax is added to the whole site.

    The Prometheus scrape from inside the network is expected to originate on
    loopback; an operator centralising Prometheus through a proxy must widen this
    deliberately. Django's test ``RequestFactory`` hard-codes
    ``REMOTE_ADDR="127.0.0.1"``, so the existing ``test_metrics_endpoint`` stays
    green unchanged.
    """
    peer = request.META.get("REMOTE_ADDR")
    try:
        is_loopback = peer is not None and ipaddress.ip_address(peer).is_loopback
    except ValueError:
        is_loopback = False
    if not is_loopback:
        return HttpResponse(status=403)
    return ExportToDjangoView(request)


urlpatterns = [
    path("metrics", _metrics_gate, name="prometheus-django-metrics"),
    path("", include("django_prometheus.urls")),
    path("admin/", admin.site.urls),
    path("moderation/", include("apps.moderation.urls")),
    path("analytics/", include("apps.analytics.urls")),
    path("cabinet/", include("apps.cabinet.urls")),
    path("", include("apps.users.urls")),
    path("", include("apps.ads.urls")),
    path("", include("apps.categories.urls")),
    path("", include("apps.locations.urls")),
    path("", include("apps.search.urls")),
    path("", include("apps.core.urls")),
]
