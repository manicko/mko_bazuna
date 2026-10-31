"""URL routes for the ``cabinet`` JSON API surface.

Hosts every cabinet ``/api/v1/`` endpoint in this one module (plan §2.3 Q1
layout): ``GET /api/v1/favorites/`` (S2.4) and the matching
``POST /api/v1/favorites/{ad_id}/toggle/`` write (S3.2 — the toggle view lives in
``apps.ads.views.api.favorite`` but the plan's URL prefix is orthogonal to the
module host, so the route is registered here alongside the list),
``GET /api/v1/saved-searches/`` and ``GET /api/v1/search-history/`` (S2.7).
Routes are prefix-based; the aggregator mounts this module at the ``/api/v1/``
root (``path("", include("apps.cabinet.api_urls"))``).
"""

from django.urls import path

from apps.ads.views.api.favorite import favorite_toggle_view
from apps.cabinet.views.api.favorites import favorites_list_view
from apps.cabinet.views.api.saved_searches import saved_searches_list_view
from apps.cabinet.views.api.search_history import search_history_view

app_name = "cabinet_api"

urlpatterns = [
    path("favorites/", favorites_list_view, name="favorites"),
    path(
        "favorites/<int:ad_id>/toggle/",
        favorite_toggle_view,
        name="favorite_toggle",
    ),
    path("saved-searches/", saved_searches_list_view, name="saved_searches"),
    path("search-history/", search_history_view, name="search_history"),
]
