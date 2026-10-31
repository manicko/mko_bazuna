"""URL routes for the ``cabinet`` JSON API surface.

Hosts every cabinet ``/api/v1/`` endpoint in this one module (plan §2.3 Q1
layout): ``GET /api/v1/favorites/`` (S2.4) and the matching
``POST /api/v1/favorites/{ad_id}/toggle/`` write (S3.2 — the toggle view lives in
``apps.ads.views.api.favorite`` but the plan's URL prefix is orthogonal to the
module host, so the route is registered here alongside the list),
``GET /api/v1/saved-searches/`` and ``GET /api/v1/search-history/`` (S2.7),
their write halves ``POST /api/v1/saved-searches/`` +
``POST /api/v1/saved-searches/{pk}/{toggle,edit,delete}/`` (S3.4) and
``POST /api/v1/search-history/clear/`` (S3.5).
Routes are prefix-based; the aggregator mounts this module at the ``/api/v1/``
root (``path("", include("apps.cabinet.api_urls"))``).
"""

from django.urls import path

from apps.ads.views.api.favorite import favorite_toggle_view
from apps.cabinet.views.api.favorites import favorites_list_view
from apps.cabinet.views.api.saved_search_writes import (
    saved_search_delete_view,
    saved_search_edit_view,
    saved_search_toggle_view,
    saved_searches_collection_view,
)
from apps.cabinet.views.api.search_history import search_history_view
from apps.cabinet.views.api.search_history_clear import search_history_clear_view

app_name = "cabinet_api"

urlpatterns = [
    path("favorites/", favorites_list_view, name="favorites"),
    path(
        "favorites/<int:ad_id>/toggle/",
        favorite_toggle_view,
        name="favorite_toggle",
    ),
    # S2.7 read + S3.4 create share the plan's single collection URL
    # (``GET/POST /api/v1/saved-searches/``); ``saved_searches_list_view`` remains
    # importable and is delegated to by the dispatcher for GET.
    path(
        "saved-searches/",
        saved_searches_collection_view,
        name="saved_searches",
    ),
    # S3.4 — saved-search write halves (plan row 16): toggle/edit/delete are
    # keyed sub-routes.
    path(
        "saved-searches/<int:pk>/toggle/",
        saved_search_toggle_view,
        name="saved_search_toggle",
    ),
    path(
        "saved-searches/<int:pk>/edit/",
        saved_search_edit_view,
        name="saved_search_edit",
    ),
    path(
        "saved-searches/<int:pk>/delete/",
        saved_search_delete_view,
        name="saved_search_delete",
    ),
    path("search-history/", search_history_view, name="search_history"),
    # S3.5 — search-history clear half (plan row 18).
    path(
        "search-history/clear/",
        search_history_clear_view,
        name="search_history_clear",
    ),
]
