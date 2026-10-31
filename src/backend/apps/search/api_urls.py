"""URL routes for the ``search`` JSON API surface (``/api/v1/search/``)."""

from django.urls import path

from apps.search.views.api.search import search_view

app_name = "search_api"

urlpatterns = [
    path("", search_view, name="search"),
]
