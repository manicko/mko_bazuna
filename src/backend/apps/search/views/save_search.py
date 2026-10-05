"""
Saved-search create view (FT-002).

Authenticated-only POST target for the "Сохранить поиск" modal. Captures the
current query + optional city/category/price filters, creates an active
``SavedSearch`` for the request user (with their ``LANGUAGE_CODE``), and
returns an HTMX success fragment.
"""

import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import render

from apps.core.enums import LanguageLocale
from apps.core.utils.sanitize import redact_free_text
from apps.search.models import SavedSearch

logger = logging.getLogger(__name__)

# The persisted ``SavedSearch.query`` column bound; values over this are refused
# at the boundary rather than silently truncated (08-SRCH-011).
_QUERY_MAX_LENGTH = 200


@login_required
def save_search(request: HttpRequest) -> HttpResponse:
    """
    Create a saved search from the modal form payload.

    Accepts ``POST`` with ``query`` and optional ``city_id``, ``category_id``,
    ``min_price``, ``max_price``. The query is PII-redacted before persistence
    (masking phones, e-mails and multi-word names) and then bounded: a value
    over ``_QUERY_MAX_LENGTH`` is refused with HTTP 400 and nothing is stored.
    Redaction never lengthens a value, so it can never turn a legal query into
    an over-cap one.

    ``redact_free_text`` is used rather than ``redact_search_query`` because the
    latter truncates to 100 characters, which would silently change what the
    saved search matches and contradict the ``max_length=200`` column bound this
    view enforces (08-SRCH-011).

    Returns:
        The ``save_search_success.html`` fragment (or 405 for non-POST, 400 for
        an over-cap query).
    """
    if request.method != "POST":
        return HttpResponse(status=405)

    query = redact_free_text((request.POST.get("query") or "").strip())
    if len(query) > _QUERY_MAX_LENGTH:
        logger.warning(
            "Refused over-cap saved-search query for user %s: %s chars > %s (08-SRCH-011)",
            request.user.pk,
            len(query),
            _QUERY_MAX_LENGTH,
        )
        return HttpResponseBadRequest()

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
        language=request.LANGUAGE_CODE or LanguageLocale.BOSNIAN.value,
        is_active=True,
    )
    logger.info("Saved search %s created for user %s", saved_search.pk, request.user.pk)

    return render(
        request,
        "search/partials/save_search_success.html",
        {"saved_search": saved_search},
    )
