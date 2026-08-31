"""Core app URLs."""

from apps.core import views
from django.urls import path

app_name = "core"

urlpatterns = [
    path("health/", views.health_check, name="health"),
    path("csp-report/", views.csp_report, name="csp_report"),
    path("privacy/", views.privacy_policy, name="privacy"),
]
