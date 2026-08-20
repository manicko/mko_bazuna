"""Cabinet app URLs.

This module is the shared append target for the cabinet sections
(CAB-002 favorites, CAB-003 saved-searches, CAB-004 search-history),
which are serialized here to avoid concurrent-edit conflicts.
"""

from apps.cabinet.views import cabinet_hub, cabinet_settings
from apps.cabinet.views.favorites import favorites_count_badge, favorites_list
from apps.cabinet.views.saved_searches import (
    saved_search_delete,
    saved_search_edit,
    saved_search_toggle,
    saved_searches_list,
)
from apps.cabinet.views.search_history import search_history_clear, search_history_list
from django.urls import path

app_name = "cabinet"

urlpatterns = [
    path("", cabinet_hub, name="home"),
    path("settings/", cabinet_settings, name="settings"),
    path("favorites/", favorites_list, name="favorites"),
    path("favorites/count/", favorites_count_badge, name="favorites_count"),
    path(
        "saved-searches/",
        saved_searches_list,
        name="saved-searches",
    ),
    path(
        "saved-searches/<int:pk>/toggle/",
        saved_search_toggle,
        name="saved-search-toggle",
    ),
    path(
        "saved-searches/<int:pk>/edit/",
        saved_search_edit,
        name="saved-search-edit",
    ),
    path(
        "saved-searches/<int:pk>/delete/",
        saved_search_delete,
        name="saved-search-delete",
    ),
    path("search-history/", search_history_list, name="search-history"),
    path(
        "search-history/clear/",
        search_history_clear,
        name="search-history-clear",
    ),
]
