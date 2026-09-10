"""Core app URLs."""

from django.urls import path

from apps.core import views

app_name = "core"

urlpatterns = [
    path("health/", views.health_check, name="health"),
    path("csp-report/", views.csp_report, name="csp_report"),
    path("privacy/", views.privacy_policy, name="privacy"),
]
