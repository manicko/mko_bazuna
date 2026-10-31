"""URL routes for the ``cabinet`` JSON API surface (``/api/v1/favorites/``)."""

from django.urls import path

from apps.cabinet.views.api.favorites import favorites_list_view

app_name = "cabinet_api"

urlpatterns = [
    path("", favorites_list_view, name="favorites"),
]
