"""
Cabinet Favorites list view (CAB-002).

Lists the authenticated user's favorited ads reusing the shared ad-card
partial (``ads/partials/ad_list.html``) with an empty state. Removal reuses
the FT-001 heart toggle; after a removal the list fragment is re-fetched so
the card disappears without a full page reload.
"""

import logging

from apps.ads.models import Ad
from apps.ads.views.favorite import annotate_favorites
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

logger = logging.getLogger(__name__)

PER_PAGE = 24


@login_required
def favorites_list(request: HttpRequest) -> HttpResponse:
    """Render the authenticated user's favorited ads."""
    ads = (
        Ad.objects.filter(favorites__user=request.user)
        .select_related("category", "city", "user")
        .prefetch_related("images", "user__trust_score")
        .order_by("-favorites__created_at")
    )
    ads = annotate_favorites(ads, request.user.id)

    paginator = Paginator(ads, PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    context = {
        "page_obj": page_obj,
        "has_results": paginator.count > 0,
    }

    # HTMX fragment: re-render only the grid so a removed favorite disappears
    # without a full reload.
    if request.headers.get("HX-Request"):
        return render(request, "ads/partials/ad_list.html", context)

    return render(request, "cabinet/favorites.html", context)
