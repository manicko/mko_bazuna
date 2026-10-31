"""URL routes for the ``locations`` JSON API surface (``/api/v1/cities/``)."""

from django.urls import path

from apps.locations.api_cities import cities_view

app_name = "locations_api"

urlpatterns = [
    path("", cities_view, name="cities"),
]
