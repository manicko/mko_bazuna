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

from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.ads.models import Ad, AdFavorite
from apps.ads.services.favorites import (
    FavoriteToggleResult,
    annotate_favorites,
    favorites_queryset,
    toggle_favorite,
)
from apps.categories.models import Category
from apps.core.enums import AdStatus
from apps.locations.models import City
from apps.users.models import User
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Heart toggle endpoint
# ---------------------------------------------------------------------------


class TestFavoriteToggle:
    """Tests for the ads:favorite_toggle endpoint."""

    def test_authenticated_toggle_adds_and_removes(
        self, buyer: User, seller: User, category: Category, city: City
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        client = Client()
        client.force_login(buyer)

        # First tap adds the favorite and returns a filled heart.
        resp = client.post(f"/favorite/{ad.id}/")
        assert resp.status_code == 200
        assert AdFavorite.objects.filter(user=buyer, ad=ad).exists()
        content = resp.content.decode()
        assert 'aria-pressed="true"' in content

        # Second tap removes the favorite and returns an outline heart.
        resp = client.post(f"/favorite/{ad.id}/")
        assert resp.status_code == 200
        assert not AdFavorite.objects.filter(user=buyer, ad=ad).exists()
        content = resp.content.decode()
        assert 'aria-pressed="false"' in content

    def test_guest_tap_returns_login_prompt_no_302(
        self, seller: User, category: Category, city: City
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        client = Client()

        resp = client.post(f"/favorite/{ad.id}/?lang=ru")

        # NO redirect (302) — a guest must get a fragment htmx can swap.
        assert resp.status_code == 200
        # Structural assertion: the login prompt links to the Telegram login
        # flow (not a hard-coded translated string).
        assert reverse("consent:login_issue") in resp.content.decode()
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
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        client = Client()
        client.force_login(buyer)

        resp = client.post(f"/favorite/{ad.id}/")
        assert resp.status_code == 200
        assert "hx-on" not in resp.content.decode()

    def test_non_published_ad_is_404(
        self, buyer: User, seller: User, category: Category, city: City
    ) -> None:
        ad = create_test_ad(
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

    def test_get_toggle_returns_405(
        self, buyer: User, seller: User, category: Category, city: City
    ) -> None:
        """A GET to /favorite/<ad_id>/ is rejected — POST-only via @require_POST.

        Mirrors test_logout.py::test_get_logout_returns_405. Anonymous users
        must not toggle favorites on any method.
        """
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        client = Client()
        client.force_login(buyer)
        response = client.get(f"/favorite/{ad.id}/")
        assert response.status_code == 405

    def test_get_toggle_does_not_mutate_favorites(
        self, buyer: User, seller: User, category: Category, city: City
    ) -> None:
        """A GET must not create or delete an AdFavorite row (CSRF-safe).

        Verifies the state-changing body (get_or_create + delete) is not reached
        on a non-POST request.
        """
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        client = Client()
        client.force_login(buyer)

        response = client.get(f"/favorite/{ad.id}/")
        assert response.status_code == 405
        assert not AdFavorite.objects.filter(user=buyer, ad=ad).exists()

    def test_heart_form_carries_csrf_header(
        self, buyer: User, seller: User, category: Category, city: City
    ) -> None:
        """The heart form embeds its own hx-headers with X-CSRFToken (AUTZ-002).

        The component renders via the ads:favorite_toggle view. After the fix,
        its <form> must carry hx-headers so the POST is self-contained even when
        rendered outside a parent <body hx-headers> scope.
        """
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        client = Client()
        client.force_login(buyer)

        response = client.post(f"/favorite/{ad.id}/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "hx-headers" in content
        assert "X-CSRFToken" in content


# ---------------------------------------------------------------------------
# annotate_favorites helper
# ---------------------------------------------------------------------------


class TestAnnotateFavorites:
    """Tests for the annotate_favorites queryset annotation."""

    def test_annotates_initial_state(
        self, buyer: User, seller: User, category: Category, city: City
    ) -> None:
        favorited = create_test_ad(
            seller, category, city, status=AdStatus.PUBLISHED, title="Избранное"
        )
        not_favorited = create_test_ad(
            seller, category, city, status=AdStatus.PUBLISHED, title="Другое"
        )
        AdFavorite.objects.create(user=buyer, ad=favorited)

        qs = Ad.objects.filter(pk__in=[favorited.pk, not_favorited.pk])
        annotated = annotate_favorites(qs, buyer.id)

        state = {a.pk: a.is_favorited for a in annotated}
        assert state[favorited.pk] is True
        assert state[not_favorited.pk] is False

    def test_anonymous_is_all_false(
        self, seller: User, category: Category, city: City
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
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
        assert resp.status_code == 302  # redirect to login

    def test_lists_favorited_ads(
        self, buyer: User, seller: User, category: Category, city: City
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        AdFavorite.objects.create(user=buyer, ad=ad)

        client = Client()
        client.force_login(buyer)
        resp = client.get("/cabinet/favorites/")

        assert resp.status_code == 200
        assert ad.title in resp.content.decode()

    def test_empty_state(
        self, buyer: User, seller: User, category: Category, city: City
    ) -> None:
        create_test_ad(
            seller, category, city, status=AdStatus.PUBLISHED
        )  # another seller's ad, not favorited
        client = Client()
        client.force_login(buyer)
        resp = client.get("/cabinet/favorites/?lang=ru")
        assert resp.status_code == 200
        assert "Пока нет избранного" in resp.content.decode()


# ---------------------------------------------------------------------------
# favorites_queryset service (S2.1)
# ---------------------------------------------------------------------------


class TestFavoritesQuerysetService:
    """Service-level tests for ``favorites_queryset`` (the shared list stack)."""

    def test_returns_only_the_callers_favorites(
        self, buyer: User, user: User, seller: User, category: Category, city: City
    ) -> None:
        """Ownership scoping: only the caller's favorited ads are returned."""
        mine = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        theirs = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        AdFavorite.objects.create(user=buyer, ad=mine)
        AdFavorite.objects.create(user=user, ad=theirs)

        ids = {a.id for a in favorites_queryset(buyer)}

        assert mine.id in ids
        assert theirs.id not in ids

    def test_orders_most_recently_favorited_first(
        self, buyer: User, seller: User, category: Category, city: City
    ) -> None:
        """Ordering matches the cabinet list: ``-favorites__created_at``."""
        first = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        second = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        fav_first = AdFavorite.objects.create(user=buyer, ad=first)
        AdFavorite.objects.create(user=buyer, ad=second)
        # ``created_at`` is ``auto_now_add``, so passing it to ``create()`` is
        # ignored — backdate via queryset ``update()`` for a deterministic order.
        AdFavorite.objects.filter(pk=fav_first.pk).update(
            created_at=timezone.now() - timedelta(days=1)
        )

        ordered = list(favorites_queryset(buyer).values_list("id", flat=True))

        assert ordered == [second.id, first.id]

    def test_annotates_favorited_state_true(
        self, buyer: User, seller: User, category: Category, city: City
    ) -> None:
        """Every returned row carries ``is_favorited=True`` (they are favorites)."""
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        AdFavorite.objects.create(user=buyer, ad=ad)

        row = favorites_queryset(buyer).get(pk=ad.pk)

        assert row.is_favorited is True

    def test_excludes_non_published_and_blocked_sellers(
        self, buyer: User, seller: User, category: Category, city: City
    ) -> None:
        """Only PUBLISHED ads from account-state-passing sellers are returned."""
        published = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        draft = create_test_ad(seller, category, city, status=AdStatus.DRAFT)
        banned = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        for ad in (published, draft, banned):
            AdFavorite.objects.create(user=buyer, ad=ad)

        seller.is_banned = True
        seller.save(update_fields=["is_banned"])

        # Both PUBLISHED rows belong to the (now banned) seller → none pass.
        assert list(favorites_queryset(buyer)) == []


# ---------------------------------------------------------------------------
# toggle_favorite service (S2.1)
# ---------------------------------------------------------------------------


class TestToggleFavoriteService:
    """Service-level tests for ``toggle_favorite`` (the shared toggle stack)."""

    def test_toggle_on_off_on_reports_active_and_count(
        self, buyer: User, seller: User, category: Category, city: City
    ) -> None:
        """on -> off -> on flips ``is_favorited`` and tracks the count."""
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)

        first = toggle_favorite(buyer, ad.id)
        assert first.is_favorited is True
        assert first.favorites_count == 1
        assert AdFavorite.objects.filter(user=buyer, ad=ad).exists()

        second = toggle_favorite(buyer, ad.id)
        assert second.is_favorited is False
        assert second.favorites_count == 0
        assert not AdFavorite.objects.filter(user=buyer, ad=ad).exists()

        third = toggle_favorite(buyer, ad.id)
        assert third.is_favorited is True
        assert third.favorites_count == 1

    def test_returns_the_toggled_ad(
        self, buyer: User, seller: User, category: Category, city: City
    ) -> None:
        """The result carries the resolved ad for the caller to render."""
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)

        result = toggle_favorite(buyer, ad.id)

        assert isinstance(result, FavoriteToggleResult)
        assert result.ad.id == ad.id

    def test_count_is_scoped_to_the_caller(
        self, buyer: User, user: User, seller: User, category: Category, city: City
    ) -> None:
        """The count reflects only the caller's favorites, not other users'."""
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        AdFavorite.objects.create(user=user, ad=ad)

        result = toggle_favorite(buyer, ad.id)

        assert result.is_favorited is True
        assert result.favorites_count == 1  # buyer only; ``user``'s favorite excluded

    def test_non_published_ad_raises_does_not_exist(
        self, buyer: User, seller: User, category: Category, city: City
    ) -> None:
        """A non-PUBLISHED ad raises ``Ad.DoesNotExist`` (caller maps to 404)."""
        ad = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.ARCHIVED,
            archived_at=timezone.now(),
        )

        with pytest.raises(Ad.DoesNotExist):
            toggle_favorite(buyer, ad.id)

    def test_missing_ad_raises_does_not_exist(self, buyer: User) -> None:
        with pytest.raises(Ad.DoesNotExist):
            toggle_favorite(buyer, 999999)
