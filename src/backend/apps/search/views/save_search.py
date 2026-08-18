"""
Saved-search create view (FT-002).

Authenticated-only POST target for the "Сохранить поиск" modal. Captures the
current query + optional city/category/price filters, creates an active
``SavedSearch`` for the request user (with their ``LANGUAGE_CODE``), and
returns an HTMX success fragment.
"""

import logging

from apps.search.models import SavedSearch
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

logger = logging.getLogger(__name__)


@login_required
def save_search(request: HttpRequest) -> HttpResponse:
    """
    Create a saved search from the modal form payload.

    Accepts ``POST`` with ``query`` and optional ``city_id``, ``category_id``,
    ``min_price``, ``max_price``. Creates a ``SavedSearch`` scoped to the
    request user (``is_active=True`` by default) and returns a success
    fragment that replaces the modal.

    Returns:
        The ``save_search_success.html`` fragment (or 405 for non-POST).
    """
    if request.method != "POST":
        return HttpResponse(status=405)

    query = (request.POST.get("query") or "").strip()

    def _int_or_none(name: str) -> int | None:
        raw = (request.POST.get(name) or "").strip()
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    saved_search = SavedSearch.objects.create(
        user=request.user,
        query=query or None,
        city_id=_int_or_none("city_id"),
        category_id=_int_or_none("category_id"),
        min_price=_int_or_none("min_price"),
        max_price=_int_or_none("max_price"),
        language=request.LANGUAGE_CODE or "bs",
        is_active=True,
    )
    logger.info("Saved search %s created for user %s", saved_search.pk, request.user.pk)

    return render(
        request,
        "search/partials/save_search_success.html",
        {"saved_search": saved_search},
    )
