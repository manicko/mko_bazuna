"""URL routes for the ``categories`` JSON API surface (``/api/v1/categories/``)."""

from django.urls import path

from apps.categories.api_tree import categories_view

app_name = "categories_api"

urlpatterns = [
    path("", categories_view, name="tree"),
]
