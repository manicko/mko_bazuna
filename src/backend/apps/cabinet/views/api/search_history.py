"""
JSON search-history list endpoint — ``GET /api/v1/search-history/``.

The read-only JSON mirror of
:func:`apps.cabinet.views.search_history.search_history_list`, and it is
**session-only** (A6): the HTML mirror is ``@login_required`` and the cabinet
docstring states anonymous (session) search history is never shown there, so
this endpoint mirrors that gate exactly — an anonymous request is refused with a
401 problem and anonymous session history is **never** exposed. Anonymous
session history remains machine-reachable only through the autocomplete endpoint
(plan stance #4), which is out of scope here.

Same ordering (``-created_at``) and the same page cap (``_HISTORY_LIMIT`` = 100)
as the HTML mirror; the caller's own history only (ownership scoping by the
``user=request.user`` filter). Rate limiting: none — the HTML cabinet mirror has
none.
"""

import logging
from typing import Any

from django.core.paginator import Paginator
from django.http import HttpRequest, JsonResponse

from apps.core.utils.api_auth import login_required_api
from apps.search.models import SearchHistory

logger = logging.getLogger(__name__)

# Page cap, mirroring ``apps.cabinet.views.search_history._HISTORY_LIMIT``.
PER_PAGE = 100


@login_required_api
def search_history_view(request: HttpRequest) -> JsonResponse:
    """Return a page of the caller's recent search queries as a JSON envelope.

    Mirrors the HTML cabinet search-history list 1:1 (same ``user`` filter, same
    ``-created_at`` ordering, same 100-entry cap) with the standard pagination
    envelope instead of a rendered list. Session-only (A6).
    """
    entries = (
        SearchHistory.objects.filter(user=request.user)
        .order_by("-created_at")
        .values("query", "created_at")
    )

    paginator = Paginator(entries, PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    return JsonResponse(
        {
            "page": page_obj.number,
            "per_page": PER_PAGE,
            "total_count": paginator.count,
            "results_truncated": False,
            "results": [_serialize_entry(entry) for entry in page_obj.object_list],
            "has_next": page_obj.has_next(),
        }
    )


def _serialize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Serialize one history row into ``{query, created_at}`` (template fields)."""
    return {
        "query": entry["query"],
        "created_at": entry["created_at"].isoformat(),
    }
