"""URL routes for the ``ads`` JSON API surface (``/api/v1/ads/``)."""

from django.urls import path

from apps.ads.views.api.detail import detail_view
from apps.ads.views.api.lifecycle_actions import (
    archive_view,
    delete_view,
    reactivate_view,
)
from apps.ads.views.api.listings import listings_view

app_name = "ads_api"

urlpatterns = [
    path("", listings_view, name="listings"),
    path("<int:ad_id>/", detail_view, name="ad_detail"),
    # S4.3 — lifecycle actions (plan §2.4 rows 7, 8, 9), verbatim plan URLs.
    path("<int:ad_id>/archive/", archive_view, name="archive"),
    path("<int:ad_id>/reactivate/", reactivate_view, name="reactivate"),
    path("<int:ad_id>/delete/", delete_view, name="delete"),
]
