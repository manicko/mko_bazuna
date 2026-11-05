"""URL-surface guard for the retired /api/v1/ mount (plan §8 G5).

Replaces apps.api.tests.test_urls (deleted with its aggregator): the
removed root mount must stay absent while the retained legacy JSON
route keeps its exact path and reverse name.
"""

import pytest
from django.test import Client
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_api_v1_root_returns_404() -> None:
    # With the mount removed nothing resolves under /api/v1/.
    assert Client().get("/api/v1/").status_code == 404


def test_api_v1_ads_prefix_returns_404() -> None:
    # A re-added per-app route module under the old mount would resolve here.
    assert Client().get("/api/v1/ads/").status_code == 404


def test_moderation_bulk_action_legacy_route_pinned() -> None:
    # The retained legacy JSON surface lives OUTSIDE the retired mount.
    assert reverse("moderation:bulk_action") == "/moderation/api/v1/bulk-action/"
