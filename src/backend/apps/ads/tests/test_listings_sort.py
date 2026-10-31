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
        # Assert on the queryset order, not on HTML string positions.
        ids = [a.id for a in response.context["page_obj"]]
        assert ids == [a.id for a in sorted(published_ads, key=lambda a: a.published_at)]

    def test_date_new_orders_newest_first(self, published_ads) -> None:
        """``?sort=date_desc`` (DATE_NEW, default) renders ads newest-first."""
        client = Client()
        response = client.get(f"/?sort={AdSort.DATE_NEW}")

        assert response.status_code == 200
        ids = [a.id for a in response.context["page_obj"]]
        assert ids == [a.id for a in sorted(published_ads, key=lambda a: a.published_at, reverse=True)]

    def test_default_sort_is_date_new(self, published_ads) -> None:
        """No ``sort`` param defaults to ``date_desc`` (newest first)."""
        client = Client()
        response = client.get("/")

        assert response.status_code == 200
        ids = [a.id for a in response.context["page_obj"]]
        assert ids == [a.id for a in sorted(published_ads, key=lambda a: a.published_at, reverse=True)]


class TestListingsSortIdTiebreaker:
    """Equal sort keys are resolved deterministically by the ``-id`` tiebreaker.

    Ads sharing an identical ``published_at`` have no fixed relative order in
    PostgreSQL without a unique secondary key, so a page boundary inside the
    tied group could reorder or duplicate rows. The ``-id`` tiebreaker (plan R2,
    the single approved ordering delta) makes every page deterministic. These
    tests pin BOTH the DATE_NEW and DATE_OLD directions, driven through the real
    HTML listings view.
    """

    def test_date_new_equal_published_at_breaks_by_id_desc(
        self, seller, category, city
    ) -> None:
        """DATE_NEW with identical ``published_at`` orders by ``-id`` (newest first)."""
        shared = timezone.now()
        ads = [
            create_test_ad(
                seller,
                category,
                city,
                title=f"Tied {i}",
                status=AdStatus.PUBLISHED,
                published_at=shared,
            )
            for i in range(3)
        ]
        expected = sorted((a.id for a in ads), reverse=True)

        client = Client()
        response = client.get(f"/?sort={AdSort.DATE_NEW}")

        assert response.status_code == 200
        ids = [a.id for a in response.context["page_obj"]]
        assert ids == expected

    def test_date_old_equal_published_at_breaks_by_id_desc(
        self, seller, category, city
    ) -> None:
        """DATE_OLD with identical ``published_at`` also breaks by ``-id``.

        The tiebreaker is ``-id`` on every branch (not the primary direction),
        so even the oldest-first ordering resolves ties newest-id-first.
        """
        shared = timezone.now()
        ads = [
            create_test_ad(
                seller,
                category,
                city,
                title=f"Tied {i}",
                status=AdStatus.PUBLISHED,
                published_at=shared,
            )
            for i in range(3)
        ]
        expected = sorted((a.id for a in ads), reverse=True)

        client = Client()
        response = client.get(f"/?sort={AdSort.DATE_OLD}")

        assert response.status_code == 200
        ids = [a.id for a in response.context["page_obj"]]
        assert ids == expected
