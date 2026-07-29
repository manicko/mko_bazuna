"""Search app URLs."""

from apps.search.views.autocomplete import autocomplete
from apps.search.views.search import search
from django.urls import path

app_name = "search"

urlpatterns = [
    path("search/", search, name="search"),
    path("api/search/autocomplete", autocomplete, name="autocomplete"),
]