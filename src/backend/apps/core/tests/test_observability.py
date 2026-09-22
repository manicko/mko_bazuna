"""
Tests for Block B3 — Observability Wiring (finding 12-OPS-004).

Verifies that ``django-prometheus`` is properly wired into the application:
- ``django_prometheus`` is registered in ``INSTALLED_APPS``
- ``PrometheusBeforeMiddleware`` is the FIRST middleware entry
- ``PrometheusAfterMiddleware`` is the LAST middleware entry
- ``/metrics`` endpoint returns HTTP 200 with Prometheus exposition format
"""

from __future__ import annotations

import pytest
from django.conf import settings
from django.test import Client

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# INSTALLED_APPS
# ---------------------------------------------------------------------------


def test_prometheus_in_installed_apps() -> None:
    """``django_prometheus`` is present in ``settings.INSTALLED_APPS``."""
    assert "django_prometheus" in settings.INSTALLED_APPS


# ---------------------------------------------------------------------------
# MIDDLEWARE ordering
# ---------------------------------------------------------------------------


def test_prometheus_middleware_ordering() -> None:
    """``PrometheusBeforeMiddleware`` is first and ``PrometheusAfterMiddleware`` is last.

    django-prometheus does not enforce ordering at runtime; the Before middleware
    must be index 0 and the After middleware must be the last entry so that
    latency histograms capture the full request lifecycle through all other
    middleware layers.
    """
    middleware = list(settings.MIDDLEWARE)
    assert middleware[0] == "django_prometheus.middleware.PrometheusBeforeMiddleware"
    assert middleware[-1] == "django_prometheus.middleware.PrometheusAfterMiddleware"


# ---------------------------------------------------------------------------
# /metrics endpoint
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_metrics_endpoint(client: Client) -> None:
    """``/metrics`` returns 200 with Prometheus exposition format markers."""
    response = client.get("/metrics")
    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "# HELP" in content or "# TYPE" in content
