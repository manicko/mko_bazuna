"""
Favorites toggle view (FT-001).

The heart toggle is an auth-gated HTMX endpoint. It uses a **manual** auth
check so an anonymous tap returns the ``login_prompt`` fragment (HTTP 200,
no 302) that htmx swaps in place, instead of following a redirect blindly
(R7 / F10 / C4). ``@login_required`` is deliberately NOT used here.
"""

import logging

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from apps.ads.models import Ad, AdFavorite
from apps.core.enums import AdStatus

logger = logging.getLogger(__name__)

# Template used to render a heart for an ad card / detail page.
_FAVORITE_HEART_TEMPLATE = "components/favorite_heart.html"
# Template returned to anonymous users who tap the heart (guest login gate).
_LOGIN_PROMPT_TEMPLATE = "components/login_prompt.html"


@require_POST
def toggle_favorite(request: HttpRequest, ad_id: int) -> HttpResponse:
    """
    Toggle whether the current user has favorited a PUBLISHED ad.

    - Anonymous request: return the ``login_prompt`` fragment (200, no 302);
      nothing is persisted.
    - Authenticated request: add (upsert) or remove the ``AdFavorite`` for the
      ad and return the re-rendered heart fragment reflecting the new state.

    Raises:
        Http404: If the ad does not exist or is not PUBLISHED.
    """
    # Guest login gate: return a fragment, never a 302.
    if not request.user.is_authenticated:
        return render(
            request,
            _LOGIN_PROMPT_TEMPLATE,
            {"ad_id": ad_id},
        )

    try:
        ad = Ad.objects.get(id=ad_id, status=AdStatus.PUBLISHED)
    except Ad.DoesNotExist:
        raise Http404("Ad not found") from None

    # Upsert-or-delete. Unique (user, ad) constraint guards against races.
    favorite, created = AdFavorite.objects.get_or_create(
        user=request.user,
        ad=ad,
    )
    if not created:
        favorite.delete()

    return render(
        request,
        _FAVORITE_HEART_TEMPLATE,
        {"ad": ad, "is_favorited": created},
    )
