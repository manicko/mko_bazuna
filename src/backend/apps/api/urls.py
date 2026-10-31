"""URL-only aggregator for the ``/api/v1/`` JSON surface.

This module imports **only** URL modules (per-app ``<app>/api_urls.py``) and
never imports views, services or models. The purity guarantee is what keeps the
import graph acyclic and is enforced mechanically by
``apps/api/tests/test_urls.py`` (aggregator purity) and
``apps/api/tests/test_import_rule.py`` (the R-F2 API→mirror import-subset
harness).

Each app that owns ``/api/v1/`` routes contributes one ``path(...,
include("<app>.api_urls"))`` line to ``urlpatterns`` below.
"""

from django.urls import include, path

urlpatterns: list = [
    path("ads/", include("apps.ads.api_urls")),
    # Dashboard is hosted in the ads app but its plan URL has no ``/ads/`` prefix
    # (row 11: ``GET /api/v1/dashboard/``); the plan keeps the URL prefix
    # orthogonal to the module host, so it gets its own ads route module.
    path("dashboard/", include("apps.ads.api_dashboard_urls")),
    path("search/", include("apps.search.api_urls")),
    path("categories/", include("apps.categories.api_urls")),
    path("cities/", include("apps.locations.api_urls")),
    # The cabinet API module hosts several prefix-based routes
    # (favorites/, saved-searches/, search-history/), so it is mounted at the
    # /api/v1/ root rather than under a single `favorites/` prefix.
    path("", include("apps.cabinet.api_urls")),
    # The users API module hosts two prefix-based routes (consent/ for consent
    # accept/decline/withdraw and auth/logout/ for logout), so it is mounted at
    # the /api/v1/ root rather than under a single prefix.
    path("", include("apps.users.api_urls")),
    path("moderation/", include("apps.moderation.api_urls")),
    path("trust/", include("apps.analytics.api_urls")),
]
