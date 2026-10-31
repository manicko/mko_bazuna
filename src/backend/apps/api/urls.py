"""URL-only aggregator for the ``/api/v1/`` JSON surface.

This module imports **only** URL modules (per-app ``<app>/api_urls.py``) and
never imports views, services or models. The purity guarantee is what keeps the
import graph acyclic and is enforced mechanically by
``apps/api/tests/test_urls.py`` (aggregator purity) and
``apps/api/tests/test_import_rule.py`` (the R-F2 API→mirror import-subset
harness).

No routes exist yet: later stages append one ``path("<prefix>/",
include("<app>.api_urls"))`` line per app to ``urlpatterns`` below.
"""

from django.urls import include, path

urlpatterns: list = [
    path("ads/", include("apps.ads.api_urls")),
]
