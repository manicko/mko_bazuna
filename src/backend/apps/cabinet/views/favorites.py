"""
Cabinet Favorites list view (CAB-002).

Lists the authenticated user's favorited ads reusing the shared ad-card
partial (``ads/partials/ad_list.html``) with an empty state. Removal reuses
the FT-001 heart toggle; after a removal the list fragment is re-fetched so
the card disappears without a full page reload.
"""

import logging

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from apps.ads.services.favorites import PER_PAGE, favorites_queryset

logger = logging.getLogger(__name__)


@login_required
def favorites_list(request: HttpRequest) -> HttpResponse:
    """Render the authenticated user's favorited ads.

    The list queryset is built by ``apps.ads.services.favorites`` (S2.1) —
    PUBLISHED ads whose seller still passes the shared account-state predicate
    (``account_state_q("user__")``, 06-PII-104 / 08-SRCH-008), ordered
    most-recently-favorited first, so the cabinet HTML list and the future
    ``GET /api/v1/favorites/`` endpoint share one stack.
    """
    ads = favorites_queryset(request.user)

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


def favorites_count_badge(request: HttpRequest) -> HttpResponse:
    """Render the header favorites-badge fragment for the given request.

    Served to HTMX after a ``favorite:toggled`` event so the heart-with-count
    badge in the catalog header refreshes without a full page reload.

    Anonymous requests render the outline heart (no count); authenticated
    requests render the filled heart with ``request.user.favorites.count()``.
    """
    user = request.user
    favorites_count = None
    if user.is_authenticated:
        favorites_count = user.favorites.count()
    return render(
        request,
        "components/header_favorites_badge.html",
        {"favorites_count": favorites_count},
    )
