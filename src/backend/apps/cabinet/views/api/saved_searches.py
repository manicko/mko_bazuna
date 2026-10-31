"""
JSON saved-searches list endpoint — ``GET /api/v1/saved-searches/``.

The read-only JSON mirror of
:func:`apps.cabinet.views.saved_searches.saved_searches_list`: the **same**
queryset (the caller's own saved searches, ``select_related("city",
"category")``, most-recently-created first) and the **same** per-row facts the
HTML list renders (query, localized city/category, price bounds, active toggle).
Ownership scoping is by construction — the queryset is filtered on
``user=request.user``, so another user's rows are never visible.

Pagination: the HTML mirror renders every saved search on one page (it has no
paginator), so there is no HTML page size to mirror; ``PER_PAGE`` below is the
one addition the mandated pagination envelope requires. Ordering and the
``select_related`` set mirror the HTML queryset exactly.

Rate limiting: none — the HTML cabinet mirror has no rate-limit check and the
plan assigns no budget namespace to this session-gated read.
"""

import logging
from typing import Any

from django.core.paginator import Paginator
from django.http import HttpRequest, JsonResponse

from apps.core.utils.api_auth import login_required_api
from apps.search.models import SavedSearch

logger = logging.getLogger(__name__)

# API page size (the HTML mirror is unpaginated — see module docstring).
PER_PAGE = 24


@login_required_api
def saved_searches_list_view(request: HttpRequest) -> JsonResponse:
    """Return a page of the caller's saved searches as a JSON envelope.

    Mirrors the HTML cabinet saved-searches list 1:1 (same queryset, same
    ``-created_at`` ordering, same ``select_related``) with the standard
    pagination envelope instead of a rendered row list. The caller's saved
    searches only — ownership scoping is the ``user=request.user`` filter.
    """
    searches = (
        SavedSearch.objects.filter(user=request.user)
        .select_related("city", "category")
        .order_by("-created_at")
    )

    paginator = Paginator(searches, PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    locale = request.LANGUAGE_CODE
    return JsonResponse(
        {
            "page": page_obj.number,
            "per_page": PER_PAGE,
            "total_count": paginator.count,
            "results_truncated": False,
            "results": [
                _serialize_saved_search(ss, locale) for ss in page_obj.object_list
            ],
            "has_next": page_obj.has_next(),
        }
    )


def _serialize_saved_search(ss: SavedSearch, locale: str) -> dict[str, Any]:
    """Serialize one saved search into the stable JSON shape (D4).

    Carries the facts the HTML row renders (query, localized city/category,
    price bounds, the active toggle) plus the model timestamps. The
    ``unsubscribe_token`` capability token is deliberately **never** exposed.
    """
    return {
        "id": ss.id,
        "query": ss.query,
        "city": _named(ss.city, locale),
        "category": _named(ss.category, locale),
        "min_price": ss.min_price,
        "max_price": ss.max_price,
        "language": ss.language,
        "is_active": ss.is_active,
        "created_at": ss.created_at.isoformat(),
        "updated_at": ss.updated_at.isoformat(),
        "last_notified_at": (
            ss.last_notified_at.isoformat() if ss.last_notified_at else None
        ),
    }


def _named(obj: Any, locale: str) -> dict[str, Any] | None:
    """Return ``{"id", "slug", "name"}`` for an optional related object.

    ``name`` is localized for the request locale, exactly as the HTML row's
    ``get_city_name`` / ``get_category_name`` filters render it.
    """
    if obj is None:
        return None
    return {"id": obj.id, "slug": obj.slug, "name": obj.get_name(locale=locale)}
