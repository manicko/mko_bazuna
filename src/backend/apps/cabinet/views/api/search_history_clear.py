"""
JSON search-history clear endpoint (S3.5).

The clear half of gap 18 (plan §2.4 row 18):
``POST /api/v1/search-history/clear/``. It is the JSON sibling of the HTML
cabinet clear :func:`apps.cabinet.views.search_history.search_history_clear` and
deletes **exactly** the same scope — the caller's whole ``SearchHistory`` set,
with no filter (the HTML view runs
``SearchHistory.objects.filter(user=request.user).delete()``). The logic is a
one-line inline query in the HTML view, so this module replicates it verbatim
rather than inventing a new service module (plan S3.5: "reuse the same
service/query the HTML uses").

**Auth (SESS).** ``login_required_api`` runs first: an anonymous request answers
a 401 ``unauthenticated`` problem (no ``WWW-Authenticate``) **before** the method
gate (A6 — the HTML mirror is ``@login_required``). The method gate is POST-only
(405 ``method_not_allowed`` problem with ``Allow: POST``).

**Rate limit first** — the shared ``api_write`` namespace /
``RateLimitBudget.API_WRITE`` budget, answering a 429 ``rate_limited`` problem
with ``Retry-After``.

**Idempotent confirmed state (Q8).** The endpoint is re-runnable: clearing an
already-empty history succeeds and returns the **same** confirmed machine state
``{"cleared": true, "remaining": 0}``. ``remaining`` is the caller's post-clear
row count, so it is a live confirmation the cleared state is re-retrievable (the
S2.7 ``GET /api/v1/search-history/`` read then reports ``total_count == 0``).
"""

import logging
from http import HTTPStatus
from typing import Final

from django.http import HttpRequest, JsonResponse
from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _

from apps.core.utils.api_auth import TYPE_METHOD_NOT_ALLOWED, login_required_api
from apps.core.utils.problem import problem, rate_limited_problem
from apps.search.models import SearchHistory
from apps.search.services.rate_limit import RateLimitBudget, rate_limit_check

logger = logging.getLogger(__name__)

# English msgid (cataloged in ``ru``/``bs``/``en`` in the stage i18n batch).
_DETAIL_METHOD_NOT_ALLOWED: Final[str | Promise] = _("Method not allowed.")

# The rate-limit namespace for every authenticated ``/api/v1/`` write. All
# writes share one key namespace (plan Q4/§2.3).
_RATE_LIMIT_NAMESPACE: Final[str] = "api_write"

# The only allowed method for this write endpoint.
_ALLOWED_METHODS: Final[tuple[str, ...]] = ("POST",)


@login_required_api
def search_history_clear_view(request: HttpRequest) -> JsonResponse:
    """``POST /api/v1/search-history/clear/`` — clear the caller's history.

    Deletes exactly what the HTML cabinet clear deletes (the caller's whole
    ``SearchHistory`` set, no filter) and answers the Q8 idempotent confirmed
    state ``{"cleared": true, "remaining": 0}``.
    """
    if request.method not in _ALLOWED_METHODS:
        response = problem(
            HTTPStatus.METHOD_NOT_ALLOWED,
            TYPE_METHOD_NOT_ALLOWED,
            _DETAIL_METHOD_NOT_ALLOWED,
        )
        response["Allow"] = ", ".join(_ALLOWED_METHODS)
        return response

    # Rate limit FIRST, before touching the DB, mirroring the other writes.
    if not rate_limit_check(
        request,
        namespace=_RATE_LIMIT_NAMESPACE,
        budget=RateLimitBudget.API_WRITE,
    ):
        return rate_limited_problem(RateLimitBudget.API_WRITE)

    # Same scope as the HTML clear (``search_history.py``): the caller's whole
    # history, no filter.
    deleted, _ = SearchHistory.objects.filter(user=request.user).delete()
    remaining = SearchHistory.objects.filter(user=request.user).count()

    logger.info("Cleared %d history entries for user %s", deleted, request.user.pk)
    return JsonResponse({"cleared": True, "remaining": remaining})


__all__ = ["search_history_clear_view"]
