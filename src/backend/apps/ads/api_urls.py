"""URL routes for the ``ads`` JSON API surface (``/api/v1/ads/``)."""

from django.urls import path

from apps.ads.views.api.listings import listings_view

app_name = "ads_api"

urlpatterns = [
    path("", listings_view, name="listings"),
]
