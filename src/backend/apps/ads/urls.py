"""Ads app URLs."""

from django.urls import path

from apps.ads.views.dashboard import dashboard
from apps.ads.views.edit import ad_edit, ad_archive, ad_reactivate
from apps.ads.views.listings import listings, ad_detail

app_name = "ads"

urlpatterns = [
    path("", listings, name="listings"),
    path("category/<slug:category_slug>/", listings, name="listings_category"),
    path("city/<slug:city_slug>/", listings, name="listings_city"),
    path("<int:ad_id>/", ad_detail, name="detail"),
    path("dashboard/", dashboard, name="dashboard"),
    path("<int:ad_id>/edit/", ad_edit, name="edit"),
    path("<int:ad_id>/archive/", ad_archive, name="archive"),
    path("<int:ad_id>/reactivate/", ad_reactivate, name="reactivate"),
]