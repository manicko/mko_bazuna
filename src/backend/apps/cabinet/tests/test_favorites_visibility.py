"""Ban enforcement on the favourites list — the fifth public surface (O6 / 08-SRCH-008).

O6 claimed a ban hides inventory from "every public surface" while only search,
category listings, ad detail and the media gate were covered. The authenticated
favourites list rendered through the same ad-card partial with neither a status
filter nor an account-state filter, so a banned seller's PUBLISHED ad stayed
visible there. This module pins the predicate extension and the positive control
that stops an over-correction from hiding a legitimate favourite.

A ban is a **moderation** sanction; this is not a consent test. ``is_declined``
keeps its exact semantics — it is carried by the same shared predicate.
"""

from __future__ import annotations

import pytest
from django.test import Client

from apps.ads.models import AdFavorite
from apps.categories.models import Category
from apps.core.enums import AdStatus
from apps.locations.models import City
from apps.users.models import User
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _login(buyer: User) -> Client:
    client = Client()
    client.force_login(buyer)
    return client


def _ban(user: User) -> None:
    """Ban *user* through a plain save (the moderation action's effect)."""
    user.is_banned = True
    user.save(update_fields=["is_banned"])


class TestBannedSellerHiddenFromFavorites:
    """A banned seller's favourited PUBLISHED ad is absent from the list."""

    def test_banned_seller_ad_absent_from_favorites(
        self, buyer: User, seller: User, category: Category, city: City
    ) -> None:
        ad = create_test_ad(
            seller,
            category,
            city,
            title="Продам красный велосипед",
            status=AdStatus.PUBLISHED,
        )
        AdFavorite.objects.create(user=buyer, ad=ad)

        client = _login(buyer)

        # Positive control: visible while the seller is active.
        assert ad.id in {a.id for a in client.get("/cabinet/favorites/").context["page_obj"]}

        _ban(seller)

        response = client.get("/cabinet/favorites/")
        assert response.status_code == 200
        assert ad.id not in {a.id for a in response.context["page_obj"]}


class TestFavoritesVisibilityUnchanged:
    """Positive and preservation controls — no over-correction."""

    def test_active_seller_favourite_unchanged(
        self, buyer: User, seller: User, category: Category, city: City
    ) -> None:
        """An active, non-declined seller's favourited ad is visible."""
        ad = create_test_ad(
            seller,
            category,
            city,
            title="Продам красный велосипед",
            status=AdStatus.PUBLISHED,
        )
        AdFavorite.objects.create(user=buyer, ad=ad)

        response = _login(buyer).get("/cabinet/favorites/")

        assert response.status_code == 200
        assert ad.id in {a.id for a in response.context["page_obj"]}

    def test_non_published_favourite_is_not_rendered(
        self, buyer: User, seller: User, category: Category, city: City
    ) -> None:
        """A DRAFT favourite is not shown as a live ad card."""
        ad = create_test_ad(
            seller,
            category,
            city,
            title="Черновик",
            status=AdStatus.DRAFT,
        )
        AdFavorite.objects.create(user=buyer, ad=ad)

        response = _login(buyer).get("/cabinet/favorites/")

        assert response.status_code == 200
        assert ad.id not in {a.id for a in response.context["page_obj"]}

    def test_declined_only_favourite_is_hidden(
        self, buyer: User, seller: User, category: Category, city: City
    ) -> None:
        """``is_declined`` keeps its semantics: a declined seller's ad is hidden."""
        ad = create_test_ad(
            seller,
            category,
            city,
            title="Продам красный велосипед",
            status=AdStatus.PUBLISHED,
        )
        AdFavorite.objects.create(user=buyer, ad=ad)

        seller.is_declined = True
        seller.save(update_fields=["is_declined"])

        response = _login(buyer).get("/cabinet/favorites/")

        assert response.status_code == 200
        assert ad.id not in {a.id for a in response.context["page_obj"]}
