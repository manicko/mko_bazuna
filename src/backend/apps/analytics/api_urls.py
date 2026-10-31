"""URL routes for the ``analytics`` JSON API surface (``/api/v1/trust/``).

Mounted by ``apps/api/urls.py`` under the ``trust/`` prefix. The URL prefix is
**orthogonal to the module host** (plan S2.6: the dashboards are hosted in
``apps/analytics`` but keep the ``trust/`` prefix). ``app_name`` is
``analytics_api`` to avoid colliding with the HTML ``analytics`` namespace
(``apps/analytics/urls.py``).
"""

from django.urls import path

from apps.analytics.views.api.moderation import moderation_dashboard_view
from apps.analytics.views.api.seller import seller_dashboard_view

app_name = "analytics_api"

urlpatterns = [
    path("seller/", seller_dashboard_view, name="seller"),
    path("moderation/", moderation_dashboard_view, name="moderation"),
]
