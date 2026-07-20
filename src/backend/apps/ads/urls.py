"""Ads app URLs."""

from django.urls import path

from apps.ads.views.listings import listings, ad_detail

app_name = "ads"

urlpatterns = [
    path("", listings, name="listings"),
    path("category/<slug:category_slug>/", listings, name="listings_category"),
    path("city/<slug:city_slug>/", listings, name="listings_city"),
    path("<int:ad_id>/", ad_detail, name="detail"),
]