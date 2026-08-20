"""
Tests for the favorite heart toggle + cabinet favorites (FT-001 / CAB-002).

Covers:
- Authenticated toggle adds/removes an ``AdFavorite`` and returns the swapped
  heart fragment.
- Guest tap returns the ``login_prompt`` fragment (HTTP 200, NO 302) and does
  not persist anything.
- Non-PUBLISHED / missing ad is a 404.
- ``/cabinet/favorites/`` lists the user's favorited ads + empty state, and
  requires login.
- The ``annotate_favorites`` helper annotates the correct initial state.
"""

import pytest
from django.test import Client
from django.utils import timezone

from apps.ads.models import Ad, AdFavorite
from apps.ads.views.favorite import annotate_favorites
from apps.categories.models import Category
from apps.core.enums import AdStatus
from apps.locations.models import City
from apps.users.models import User

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


@pytest.fixture
def seller() -> User:
    """Create a seller user."""
    return User.objects.create(
        telegram_id=920000200,
        chat_id=920000200,
        password="x",
    )


@pytest.fixture
def buyer() -> User:
    """Create a registered buyer user."""
    return User.objects.create(
        telegram_id=920000201,
        chat_id=920000201,
        password="y",
    )


@pytest.fixture
def category() -> Category:
    """Create a root category."""
    return Category.objects.create(name="Транспорт", slug="transport")


@pytest.fixture
def city() -> City:
    """Create a city."""
    return City.objects.create(
        country_code="ME",
        name="Тестград",
        region="FBiH",
        slug="test-grad",
    )


def _published_ad(seller: User, category: Category, city: City, **kwargs) -> Ad:
    defaults = {
        "user": seller,
        "title": "Красный велосипед",
        "category": category,
        "city": city,
        "category_name": category.name,
        "status": AdStatus.PUBLISHED,
        "published_at": timezone.now(),
    }
    defaults.update(kwargs)
    return Ad.objects.create(**defaults)


# ---------------------------------------------------------------------------
# Heart toggle endpoint
# ---------------------------------------------------------------------------


class TestFavoriteToggle:
    """Tests for the ads:favorite_toggle endpoint."""

    def test_authenticated_toggle_adds_and_removes(
        self, buyer: User, seller: User, category: Category, city: City
    ) -> None:
        ad = _published_ad(seller, category, city)
        client = Client()
        client.force_login(buyer)

        # First tap adds the favorite and returns a filled heart.
        resp = client.post(f"/favorite/{ad.id}/")
        assert resp.status_code == 200
        assert AdFavorite.objects.filter(user=buyer, ad=ad).exists()
        content = resp.content.decode()
        assert "aria-pressed=\"true\"" in content

        # Second tap removes the favorite and returns an outline heart.
        resp = client.post(f"/favorite/{ad.id}/")
        assert resp.status_code == 200
        assert not AdFavorite.objects.filter(user=buyer, ad=ad).exists()
        content = resp.content.decode()
        assert "aria-pressed=\"false\"" in content

    def test_guest_tap_returns_login_prompt_no_302(
        self, seller: User, category: Category, city: City
    ) -> None:
        ad = _published_ad(seller, category, city)
        client = Client()

        resp = client.post(f"/favorite/{ad.id}/")

        # NO redirect (302) — a guest must get a fragment htmx can swap.
        assert resp.status_code == 200
        assert "Log in to save" in resp.content.decode()
        # Nothing persisted, and the ad detail/login url is referenced.
        assert not AdFavorite.objects.filter(ad=ad).exists()

    def test_missing_ad_is_404(self, buyer: User) -> None:
        client = Client()
        client.force_login(buyer)
        resp = client.post("/favorite/999999/")
        assert resp.status_code == 404

    def test_heart_template_no_hx_on(
        self, buyer: User, seller: User, category: Category, city: City
    ) -> None:
        """The heart component no longer uses the unsupported hx-on attribute.

        HTMX 1.9.12 has no ``hx-on``; the event dispatch was replaced with a
        native ``htmx:afterRequest`` listener, so a toggled heart must not
        carry the broken attribute.
        """
        ad = _published_ad(seller, category, city)
        client = Client()
        client.force_login(buyer)

        resp = client.post(f"/favorite/{ad.id}/")
        assert resp.status_code == 200
        assert "hx-on" not in resp.content.decode()

    def test_non_published_ad_is_404(
        self, buyer: User, seller: User, category: Category, city: City
    ) -> None:
        ad = _published_ad(
            seller,
            category,
            city,
            status=AdStatus.ARCHIVED,
            archived_at=timezone.now(),
        )
        client = Client()
        client.force_login(buyer)
        resp = client.post(f"/favorite/{ad.id}/")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# annotate_favorites helper
# ---------------------------------------------------------------------------


class TestAnnotateFavorites:
    """Tests for the annotate_favorites queryset annotation."""

    def test_annotates_initial_state(
        self, buyer: User, seller: User, category: Category, city: City
    ) -> None:
        favorited = _published_ad(seller, category, city, title="Избранное")
        not_favorited = _published_ad(seller, category, city, title="Другое")
        AdFavorite.objects.create(user=buyer, ad=favorited)

        qs = Ad.objects.filter(pk__in=[favorited.pk, not_favorited.pk])
        annotated = annotate_favorites(qs, buyer.id)

        state = {a.pk: a.is_favorited for a in annotated}
        assert state[favorited.pk] is True
        assert state[not_favorited.pk] is False

    def test_anonymous_is_all_false(
        self, seller: User, category: Category, city: City
    ) -> None:
        ad = _published_ad(seller, category, city)
        qs = Ad.objects.filter(pk=ad.pk)
        annotated = annotate_favorites(qs, None)
        annotated_ad = annotated.get(pk=ad.pk)
        assert annotated_ad.is_favorited is False


# ---------------------------------------------------------------------------
# Cabinet favorites list
# ---------------------------------------------------------------------------


class TestFavoritesList:
    """Tests for the /cabinet/favorites/ section."""

    def test_requires_login(self) -> None:
        resp = Client().get("/cabinet/favorites/")
        assert resp.status_code in (301, 302)  # redirect to login

    def test_lists_favorited_ads(
        self, buyer: User, seller: User, category: Category, city: City
    ) -> None:
        ad = _published_ad(seller, category, city)
        AdFavorite.objects.create(user=buyer, ad=ad)

        client = Client()
        client.force_login(buyer)
        resp = client.get("/cabinet/favorites/")

        assert resp.status_code == 200
        assert ad.title in resp.content.decode()

    def test_empty_state(
        self, buyer: User, seller: User, category: Category, city: City
    ) -> None:
        _published_ad(seller, category, city)  # another seller's ad, not favorited
        client = Client()
        client.force_login(buyer)
        resp = client.get("/cabinet/favorites/")
        assert resp.status_code == 200
        assert "No favorites yet" in resp.content.decode()
