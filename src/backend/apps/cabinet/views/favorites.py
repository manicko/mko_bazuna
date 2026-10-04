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

from apps.ads.models import Ad
from apps.ads.services.favorites import annotate_favorites
from apps.core.enums import AdStatus
from apps.users.services.account_state import account_state_q

logger = logging.getLogger(__name__)

PER_PAGE = 24


@login_required
def favorites_list(request: HttpRequest) -> HttpResponse:
    """Render the authenticated user's favorited ads.

    Only PUBLISHED ads are shown, and only those whose seller still passes the
    shared account-state predicate (``account_state_q("user__")``, 06-PII-104 /
    08-SRCH-008). Without the account-state term a banned seller's ad stayed
    visible in any buyer's favourites list with its title, price, thumbnail and
    contact affordance — the fifth public surface O6's "every public surface"
    covers. A banned seller's ad is hidden here exactly as it is on search,
    category listings, ad detail and the media gate: the *same* one predicate,
    not a second one.
    """
    ads = (
        Ad.objects.filter(
            favorites__user=request.user,
            status=AdStatus.PUBLISHED,
        )
        .filter(account_state_q("user__"))
        .select_related("category", "city", "user")
        .prefetch_related("images", "features", "user__trust_score")
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
