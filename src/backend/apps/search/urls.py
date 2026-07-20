"""Search app URLs."""

from django.urls import path

from apps.search.views.search import search

app_name = "search"

urlpatterns = [
    path("search/", search, name="search"),
]