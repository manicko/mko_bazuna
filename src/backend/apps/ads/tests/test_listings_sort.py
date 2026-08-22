"""
Sort-order tests for the ``listings`` view (AdSort.DATE_OLD / DATE_NEW).

Creates multiple PUBLISHED ads with distinct ``published_at`` timestamps and
asserts the response order for ``?sort=date_asc`` (oldest-first) and
``?sort=date_desc`` (newest-first, default).

These tests use the real Django test client (not mocked ORM) so the full
filter → sort → paginate → render pipeline is exercised.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.core.enums import AdSort, AdStatus

from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

# Three titles in alphabetical order so we can detect position in HTML.
_TITLES = ["Alpha Ad", "Beta Ad", "Gamma Ad"]


@pytest.fixture
def published_ads(seller, category, city):
    """Create 3 PUBLISHED ads with distinct, well-separated published_at values.

    Order by timestamp ascending: Alpha (oldest) < Beta < Gamma (newest).
    """
    now = timezone.now()
    ads = []
    offsets = [timedelta(days=2), timedelta(days=1), timedelta(minutes=30)]
    for title, offset in zip(_TITLES, offsets, strict=True):
        ad = create_test_ad(
            seller,
            category,
            city,
            title=title,
            description="Sort test description",
            status=AdStatus.PUBLISHED,
            published_at=now - offset,
        )
        ads.append(ad)
    return ads


class TestListingsSortOrder:
    """Verify DATE_OLD and DATE_NEW sort orderings in the listings view."""

    def test_date_old_orders_oldest_first(self, published_ads) -> None:
        """``?sort=date_asc`` (DATE_OLD) renders ads oldest-first."""
        client = Client()
        response = client.get(f"/?sort={AdSort.DATE_OLD}")

        assert response.status_code == 200
        html = response.content.decode()

        # Alpha has the oldest published_at → should appear first.
        pos_alpha = html.find("Alpha Ad")
        pos_beta = html.find("Beta Ad")
        pos_gamma = html.find("Gamma Ad")
        assert pos_alpha != -1
        assert pos_beta != -1
        assert pos_gamma != -1
        assert pos_alpha < pos_beta < pos_gamma

    def test_date_new_orders_newest_first(self, published_ads) -> None:
        """``?sort=date_desc`` (DATE_NEW, default) renders ads newest-first."""
        client = Client()
        response = client.get(f"/?sort={AdSort.DATE_NEW}")

        assert response.status_code == 200
        html = response.content.decode()

        # Gamma has the newest published_at → should appear first.
        pos_alpha = html.find("Alpha Ad")
        pos_beta = html.find("Beta Ad")
        pos_gamma = html.find("Gamma Ad")
        assert pos_gamma < pos_beta < pos_alpha

    def test_default_sort_is_date_new(self, published_ads) -> None:
        """No ``sort`` param defaults to ``date_desc`` (newest first)."""
        client = Client()
        response = client.get("/")

        assert response.status_code == 200
        html = response.content.decode()

        pos_alpha = html.find("Alpha Ad")
        pos_gamma = html.find("Gamma Ad")
        assert pos_gamma < pos_alpha

    def test_date_asc_and_desc_are_reversed(self, published_ads) -> None:
        """Ascending and descending produce opposite orderings (sanity reversal)."""
        client = Client()

        asc = client.get(f"/?sort={AdSort.DATE_OLD}")
        asc_html = asc.content.decode()
        desc = client.get(f"/?sort={AdSort.DATE_NEW}")
        desc_html = desc.content.decode()

        assert asc_html.find("Alpha Ad") < asc_html.find("Gamma Ad")
        assert desc_html.find("Gamma Ad") < desc_html.find("Alpha Ad")
