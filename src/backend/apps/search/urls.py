"""Search app URLs."""

from apps.search.views.autocomplete import autocomplete
from apps.search.views.preferred_city import set_preferred_city
from apps.search.views.save_search import save_search
from apps.search.views.search import search
from django.urls import path

app_name = "search"

urlpatterns = [
    path("search/", search, name="search"),
    path("save-search/", save_search, name="save-search"),
    path("api/search/autocomplete", autocomplete, name="autocomplete"),
    path("api/preferred-city/", set_preferred_city, name="preferred_city"),
]
