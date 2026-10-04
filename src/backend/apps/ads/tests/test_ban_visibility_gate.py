"""Ban enforcement on the public web surface (Q7 / 08-SRCH-008).

A ban is a **moderation** sanction. On 2026-10-03 the Product Owner ruled (Q7)
that a ban hides inventory: a banned seller's ads are excluded from the public
ad-visibility predicate across **search**, **category listings**, **ad detail**
and the **media gate**. Phase 06 landed ``account_state_q()`` and applied it to
the alert path; the public web surface still filtered only ``user__is_declined``
with no ``is_banned`` term, so a banned seller's ads stayed publicly visible.
Phase 08 implements the read boundary here, using the same shared predicate.

This module is deliberately **not** a consent test. ``is_declined`` is a separate
concept and its existing semantics are preserved exactly; the tests below prove
the ban term and keep a declined-only control.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from django.test import Client, override_settings
from django.urls import reverse

from apps.ads.services.listings_query import ListingsQuery, ListingsQueryParams
from apps.core.enums import AdStatus
from apps.media.services.filesystem import generate_storage_key
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def isolated_media_root() -> Generator[Path]:
    """A temporary MEDIA_ROOT so media files never touch the real volume."""
    with TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def _ban(user) -> None:
    """Ban *user* through a plain save (the moderation action's effect)."""
    user.is_banned = True
    user.save(update_fields=["is_banned"])


class TestBannedSellerHiddenFromSearch:
    """A banned seller's ad is absent from search results and detail."""

    def test_banned_seller_ad_absent_from_search(
        self, seller, category, city
    ) -> None:
        ad = create_test_ad(
            seller,
            category,
            city,
            title="Продам красный велосипед",
            status=AdStatus.PUBLISHED,
        )
        client = Client()
        url = "/search/?q=велосипед&lang=ru"

        # Positive control: visible while the seller is active.
        assert ad.id in {a.id for a in client.get(url).context["page_obj"]}

        _ban(seller)

        assert ad.id not in {a.id for a in client.get(url).context["page_obj"]}

    def test_banned_seller_ad_absent_from_category_listings(
        self, seller, category, city
    ) -> None:
        ad = create_test_ad(
            seller,
            category,
            city,
            title="Транспорт — прицеп",
            status=AdStatus.PUBLISHED,
        )
        params = ListingsQueryParams()
        assert ListingsQuery.build_queryset(params).filter(pk=ad.pk).exists()

        _ban(seller)

        assert not ListingsQuery.build_queryset(params).filter(pk=ad.pk).exists()

    def test_banned_seller_ad_detail_is_not_found(
        self, seller, category, city
    ) -> None:
        """Detail returns the same not-found treatment an unpublished ad gets.

        A 403 would confirm the ad exists; a banned seller's ad must 404 exactly
        as an unpublished ad does, revealing nothing about the hidden row.
        """
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        client = Client()
        detail_url = reverse("ads:detail", args=[ad.id])

        assert client.get(detail_url).status_code == 200

        _ban(seller)

        assert client.get(detail_url).status_code == 404


class TestBannedSellerHiddenFromMediaGate:
    """The media gate refuses a banned seller's image to non-staff."""

    @pytest.fixture(autouse=True)
    def _debug_false(self):
        with override_settings(DEBUG=False):
            yield

    def test_banned_seller_image_is_forbidden(
        self, seller, category, city, isolated_media_root
    ) -> None:
        from apps.ads.models import AdImage

        key = generate_storage_key()
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        AdImage.objects.create(ad=ad, image=key)
        client = Client()
        url = f"/media/{key}"

        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            assert client.get(url).status_code == 200

        _ban(seller)

        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            response = client.get(url)
        assert response.status_code == 403


class TestActiveAndDeclinedSellersUnchanged:
    """The positive control and the declined-only preservation."""

    def test_active_seller_ads_unchanged_on_all_surfaces(
        self, seller, category, city, isolated_media_root
    ) -> None:
        """An active, non-declined seller's ads are visible on every surface."""
        from apps.ads.models import AdImage

        key = generate_storage_key()
        ad = create_test_ad(
            seller,
            category,
            city,
            title="Продам красный велосипед",
            status=AdStatus.PUBLISHED,
        )
        AdImage.objects.create(ad=ad, image=key)
        client = Client()

        # Search
        assert ad.id in {
            a.id
            for a in client.get("/search/?q=велосипед&lang=ru").context[
                "page_obj"
            ]
        }
        # Category listings / shared queryset
        assert ListingsQuery.build_queryset(ListingsQueryParams()).filter(
            pk=ad.pk
        ).exists()
        # Detail
        assert (
            client.get(reverse("ads:detail", args=[ad.id])).status_code == 200
        )
        # Media gate (serves the redirect / file, never 403)
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            assert client.get(f"/media/{key}").status_code == 200

    def test_declined_only_case_is_unchanged(
        self, seller, category, city
    ) -> None:
        """``is_declined`` keeps its exact existing semantics.

        A declined seller's ad is hidden from the shared queryset and from
        detail — unchanged by this block, which adds the ban term rather than
        redefining the decline term.
        """
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        params = ListingsQueryParams()
        assert ListingsQuery.build_queryset(params).filter(pk=ad.pk).exists()

        seller.is_declined = True
        seller.save(update_fields=["is_declined"])

        assert not ListingsQuery.build_queryset(params).filter(pk=ad.pk).exists()
        assert (
            Client().get(reverse("ads:detail", args=[ad.id])).status_code == 404
        )
