"""URL routes for the ``ads`` JSON dashboard surface (``/api/v1/dashboard/``).

A **second** URL module in ``apps.ads`` (the plan's ``apps/ads/api_urls.py``
hosts the ``/api/v1/ads/`` listings/detail routes). The plan's URL prefix is
orthogonal to the module host (plan S2.6: *"URLs keep the trust prefix… prefix
orthogonal to module host"*), so the dashboard route — whose plan URL is
``GET /api/v1/dashboard/`` (row 11) with no ``/ads/`` prefix — gets its own
route module and its own namespace rather than a prefix that would diverge from
the plan's inventory.
"""

from django.urls import path

from apps.ads.views.api.dashboard import dashboard_view

app_name = "dashboard_api"

urlpatterns = [
    path("", dashboard_view, name="dashboard"),
]
