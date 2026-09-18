"""Core app URLs."""

from django.urls import path

from apps.core import views

app_name = "core"

urlpatterns = [
    path("health/", views.health_check, name="health"),
    path("health/live/", views.liveness_check, name="health_live"),
    path("health/ready/", views.readiness_check, name="health_ready"),
    path("health/v1/", views.readiness_check, name="health_v1"),
    path("csp-report/", views.csp_report, name="csp_report"),
    path("privacy/", views.privacy_policy, name="privacy"),
]
