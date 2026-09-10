"""
Analytics app URL configuration.

Routes:
    /analytics/trust/          — Seller trust dashboard (login required)
    /analytics/moderation/      — Moderation analytics dashboard (staff only)
"""

from django.urls import path

from apps.analytics.views.moderation_dashboard import moderation_analytics
from apps.analytics.views.seller_dashboard import seller_trust_dashboard

app_name = "analytics"

urlpatterns = [
    path("trust/", seller_trust_dashboard, name="seller_trust_dashboard"),
    path("moderation/", moderation_analytics, name="moderation_analytics"),
]
