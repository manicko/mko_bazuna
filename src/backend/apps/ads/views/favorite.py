"""
Favorites toggle view (FT-001).

The heart toggle is an auth-gated HTMX endpoint. It uses a **manual** auth
check so an anonymous tap returns the ``login_prompt`` fragment (HTTP 200,
no 302) that htmx swaps in place, instead of following a redirect blindly
(R7 / F10 / C4). ``@login_required`` is deliberately NOT used here.

The toggle mechanics live in ``apps.ads.services.favorites`` (S2.1) so the
HTML fragment and the future ``/api/v1/`` toggle endpoint share one stack.
"""

import logging

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from apps.ads.models import Ad
from apps.ads.services.favorites import toggle_favorite as toggle_favorite_service

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
        result = toggle_favorite_service(request.user, ad_id)
    except Ad.DoesNotExist:
        raise Http404("Ad not found") from None

    return render(
        request,
        _FAVORITE_HEART_TEMPLATE,
        {"ad": result.ad, "is_favorited": result.is_favorited},
    )
