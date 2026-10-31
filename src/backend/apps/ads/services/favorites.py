"""
Ad favorites service — favorite state annotation, listing and toggle.

``annotate_favorites`` was extracted from ``apps.ads.views.favorite``
(10-QLT-005) so that the shared listings query service can depend on this
annotation without inverting the layering (service -> views).

The list + toggle operations were hoisted here in the API-parity program
(S2.1) so that the HTML favorite surfaces (``apps.ads.views.favorite`` and
``apps.cabinet.views.favorites``) and the future ``/api/v1/`` favorites
endpoints share **one** favorites stack instead of two hand-built queries.

Contract: request-free, returns ORM objects (the project's service contract).
``annotate_favorites`` stays a pure queryset annotation; the new functions add
the caller's list and the toggle result without touching the annotation.
"""

import logging
from typing import NamedTuple

from django.db.models import Exists, OuterRef, QuerySet

from apps.ads.models import Ad, AdFavorite
from apps.core.enums import AdStatus
from apps.users.models import User
from apps.users.services.account_state import account_state_q

logger = logging.getLogger(__name__)

# Ad cards shown per favorites page (CAB-002). Kept here so the HTML view and
# any future API adapter paginate the same list identically.
PER_PAGE = 24


class FavoriteToggleResult(NamedTuple):
    """Outcome of :func:`toggle_favorite` for the current user and ad.

    ``is_favorited`` is the post-toggle state (``True`` = the heart is now
    filled), exactly the ``created`` flag the HTML toggle fragment renders.
    ``favorites_count`` is the caller's total favorite count *after* the
    toggle, the same value the header badge exposes. It is named
    ``favorites_count`` (not ``count``) so it does not shadow ``tuple.count``
    (a ``NamedTuple`` field of that name would override the method with an
    incompatible type).
    """

    ad: Ad
    is_favorited: bool
    favorites_count: int


def annotate_favorites(queryset: QuerySet[Ad], user_id: int | None) -> QuerySet[Ad]:
    """Annotate each Ad with an ``is_favorited`` flag for the current user.

    Uses a correlated ``Exists`` subquery on ``AdFavorite`` so cards render the
    correct initial heart state without per-card queries. Anonymous users
    (``user_id`` None) never match a favorite, so every ad is False.
    """
    favorite_exists = AdFavorite.objects.filter(
        ad_id=OuterRef("pk"),
        user_id=user_id,
    )
    return queryset.annotate(is_favorited=Exists(favorite_exists))


def favorites_queryset(user: User) -> QuerySet[Ad]:
    """Return the user's favorited ads exactly as the cabinet list shows them.

    Only PUBLISHED ads are returned, and only those whose seller still passes
    the shared account-state predicate (``account_state_q("user__")``,
    06-PII-104 / 08-SRCH-008). Without the account-state term a banned seller's
    ad stayed visible in any buyer's favourites list with its title, price,
    thumbnail and contact affordance. A banned seller's ad is hidden here
    exactly as it is on search, category listings, ad detail and the media
    gate: the *same* one predicate, not a second one.

    Ordering is most-recently-favorited first (``-favorites__created_at``) and
    the ``is_favorited`` annotation is applied so cards render their initial
    heart state. The queryset is the single shared stack for the cabinet HTML
    list and the future ``GET /api/v1/favorites/`` endpoint.
    """
    ads = (
        Ad.objects.filter(
            favorites__user=user,
            status=AdStatus.PUBLISHED,
        )
        .filter(account_state_q("user__"))
        .select_related("category", "city", "user")
        .prefetch_related("images", "features", "user__trust_score")
        .order_by("-favorites__created_at")
    )
    return annotate_favorites(ads, user.id)


def toggle_favorite(user: User, ad_id: int) -> FavoriteToggleResult:
    """Toggle whether *user* has favorited the PUBLISHED ad ``ad_id``.

    Upsert-or-delete on the ``(user, ad)`` pair; the unique constraint guards
    against races. Returns a :class:`FavoriteToggleResult` carrying the
    post-toggle state and the caller's favorite count, i.e. the same two facts
    the HTML heart fragment and the badge expose.

    Raises:
        Ad.DoesNotExist: If the ad does not exist or is not PUBLISHED. The
            caller (HTML or API) maps this to its own response (the HTML view
            raises ``Http404``; the API returns a uniform 404 problem).
    """
    ad = Ad.objects.get(id=ad_id, status=AdStatus.PUBLISHED)

    favorite, created = AdFavorite.objects.get_or_create(
        user=user,
        ad=ad,
    )
    if not created:
        favorite.delete()

    return FavoriteToggleResult(
        ad=ad,
        is_favorited=created,
        favorites_count=AdFavorite.objects.filter(user=user).count(),
    )
