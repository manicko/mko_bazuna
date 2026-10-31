"""
JSON saved-search write endpoints (S3.4).

The write half of gap 16 (plan §2.4 row 16): ``POST /api/v1/saved-searches/``
(create) and ``POST /api/v1/saved-searches/{pk}/{toggle,edit,delete}/``. Each
endpoint is the JSON sibling of the matching HTML view and consumes the
**same** shared mutator stack (``apps.search.services.saved_searches``, S3.1) —
one journey for the modal, the cabinet management views and the API, with no
API-only business predicate.

**Mirrors (one module, two HTML mirrors).** The create endpoint mirrors
:func:`apps.search.views.save_search.save_search`; toggle/edit/delete mirror
:func:`apps.cabinet.views.saved_searches.saved_search_{toggle,edit,delete}`.
The plan's URL prefix (``saved-searches/``) is orthogonal to the module host, so
all four routes live in this one module; the two pairing rows are registered in
``apps/api/tests/test_import_rule.py`` accordingly (an API module may declare the
union of its mirrors' import edges — the harness checks each declared row).

**Auth (SESS).** ``login_required_api`` runs first on every operation: an
anonymous request answers a 401 ``unauthenticated`` problem (no
``WWW-Authenticate``) **before** the method gate, mirroring the frozen
``staff_required_api`` branch order (an anonymous ``POST`` is 401, not 405).

**Rate limit first.** Every operation charges the shared ``api_write`` namespace
(``RateLimitBudget.API_WRITE``) before parsing the body, answering a 429
``rate_limited`` problem with ``Retry-After`` when exhausted — identical to the
favorites toggle (S3.2) and the ``api_bulk`` ordering.

**Body DTO.** Create/edit validate a small Pydantic ``BaseInputModel``
(:class:`SavedSearchWriteInput`) whose field set mirrors
``apps.search.schemas.SavedSearchInput`` plus the raw ``query`` string, in
snake_case JSON. A malformed body answers a 422 ``validation_failed`` problem
built by ``validation_problem`` (Q6).

**Query cap.** The service's :func:`bound_query` refuses an over-long (redacted)
query with ``QueryTooLongError``; the HTML create view maps that to HTTP **400**
and stores nothing. This API mirrors that status: a 400 problem document with the
stable ``type="query_too_long"`` (§2.5: malformed → 400). The cabinet edit view
does **not** run the cap (it strips only), and neither does ``update_saved_search``
— so the update endpoint mirrors the edit view exactly and has no 400 path.

**Ownership → uniform 404.** A missing or non-owned ``pk`` makes the service
raise ``SavedSearch.DoesNotExist``; this module maps that to the uniform 404
problem (``type="not_found"``), identical to the HTML ``Http404`` refusal
(CWE-209 — a foreign row is indistinguishable from an absent one).

**Responses.** Create/edit/toggle return the mutated entity in the **same
serialization** the S2.7 list read uses
(:func:`apps.cabinet.views.api.saved_searches._serialize_saved_search`); the
``unsubscribe_token`` capability token is never exposed. Delete answers the Q8
**idempotent confirmed state** ``{"id": <pk>, "deleted": true}`` — the cleared
state is re-retrievable (the row is gone from the S2.7 list).

**No CSRF exemption** — the middleware chain is used as-is; writes are POST-only.
"""

import logging
from http import HTTPStatus
from typing import Final

from django.http import HttpRequest, JsonResponse
from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _
from pydantic import Field, ValidationError

from apps.cabinet.views.api.saved_searches import (
    _serialize_saved_search,
    saved_searches_list_view,
)
from apps.core.schemas import BaseInputModel
from apps.core.utils.api_auth import TYPE_METHOD_NOT_ALLOWED, login_required_api
from apps.core.utils.problem import (
    problem,
    rate_limited_problem,
    validation_problem,
)
from apps.search.models import SavedSearch
from apps.search.schemas import SavedSearchInput
from apps.search.services.rate_limit import RateLimitBudget, rate_limit_check
from apps.search.services.saved_searches import (
    QueryTooLongError,
    create_saved_search,
    delete_saved_search,
    toggle_saved_search,
    update_saved_search,
)

logger = logging.getLogger(__name__)

# Stable ASCII ``type`` tokens (never translated).
TYPE_NOT_FOUND: Final[str] = "not_found"
TYPE_QUERY_TOO_LONG: Final[str] = "query_too_long"

# English msgids for the detail strings (cataloged in ``ru``/``bs``/``en`` in the
# stage i18n batch; ``gettext_lazy`` defers resolution so the text is translated
# for the active request locale while English stays the msgid).
_DETAIL_NOT_FOUND: Final[str | Promise] = _("Saved search not found.")
_DETAIL_METHOD_NOT_ALLOWED: Final[str | Promise] = _("Method not allowed.")
_DETAIL_QUERY_TOO_LONG: Final[str | Promise] = _("Search query is too long.")

# The rate-limit namespace for every authenticated ``/api/v1/`` write. All
# writes share one key namespace (plan Q4/§2.3).
_RATE_LIMIT_NAMESPACE: Final[str] = "api_write"

# The only allowed method for these write endpoints.
_ALLOWED_METHODS: Final[tuple[str, ...]] = ("POST",)


class SavedSearchWriteInput(BaseInputModel):
    """Client-input DTO for the saved-search create/edit body.

    Field set mirrors ``apps.search.schemas.SavedSearchInput`` (the shared
    filter boundary the HTML views use) plus the raw ``query`` string, in
    snake_case JSON. ``extra="forbid"`` (from :class:`BaseInputModel`) rejects
    unknown keys so a misspelled field fails fast with a 422.

    ``query`` defaults to ``""`` so a create with only filters is legal (the
    HTML modal posts ``query`` optionally); the service bounds/redacts it. The
    filter coercion (blank/unparseable → ``None``, ``ge=0`` prices) is delegated
    to ``SavedSearchInput`` in :meth:`to_filters` to reuse that boundary exactly.
    """

    query: str = ""
    city_id: int | None = None
    category_id: int | None = None
    min_price: int | None = Field(default=None, ge=0)
    max_price: int | None = Field(default=None, ge=0)

    def to_filters(self) -> SavedSearchInput:
        """Build the shared ``SavedSearchInput`` filter DTO from this body.

        Reusing the shared boundary keeps the API and HTML coercion semantics
        (blank/unparseable → ``None``, non-negative prices) byte-identical.
        """
        return SavedSearchInput(
            city_id=self.city_id,
            category_id=self.category_id,
            min_price=self.min_price,
            max_price=self.max_price,
        )


def _method_not_allowed() -> JsonResponse:
    """Return the 405 problem document with an ``Allow: POST`` header."""
    response = problem(
        HTTPStatus.METHOD_NOT_ALLOWED,
        TYPE_METHOD_NOT_ALLOWED,
        _DETAIL_METHOD_NOT_ALLOWED,
    )
    response["Allow"] = ", ".join(_ALLOWED_METHODS)
    return response


def _rate_limited_response(request: HttpRequest) -> JsonResponse | None:
    """Charge the shared write budget; return a 429 problem when exhausted."""
    if not rate_limit_check(
        request,
        namespace=_RATE_LIMIT_NAMESPACE,
        budget=RateLimitBudget.API_WRITE,
    ):
        return rate_limited_problem(RateLimitBudget.API_WRITE)
    return None


def _parse_write_body(request: HttpRequest) -> SavedSearchWriteInput | JsonResponse:
    """Validate the create/edit body; return a 422 problem on failure."""
    try:
        return SavedSearchWriteInput.model_validate_json(request.body)
    except ValidationError as exc:
        logger.warning("Invalid saved-search write body: %s", exc)
        return validation_problem(exc)


@login_required_api
def saved_searches_collection_view(request: HttpRequest) -> JsonResponse:
    """``/api/v1/saved-searches/`` — GET list / POST create (plan row 16).

    The plan defines one collection URL carrying both verbs (``GET/POST
    /api/v1/saved-searches/``). One route cannot hold two views in Django's URL
    resolver, so this thin dispatcher delegates GET to the S2.7 read
    (:func:`saved_searches_list_view`) and POST to
    :func:`saved_search_create_view`. ``login_required_api`` is applied here so
    an anonymous request of either verb answers the 401 problem **before** the
    method branch (identity before method, mirroring the frozen decorator).
    """
    if request.method == "GET":
        return saved_searches_list_view(request)
    return saved_search_create_view(request)


@login_required_api
def saved_search_create_view(request: HttpRequest) -> JsonResponse:
    """``POST /api/v1/saved-searches/`` — create an active saved search.

    Mirrors :func:`apps.search.views.save_search.save_search`: the same shared
    :func:`create_saved_search` service, the same ``LANGUAGE_CODE`` argument and
    the same over-cap refusal (HTML 400 → this 400 ``query_too_long`` problem).
    """
    if request.method not in _ALLOWED_METHODS:
        return _method_not_allowed()

    limited = _rate_limited_response(request)
    if limited is not None:
        return limited

    parsed = _parse_write_body(request)
    if isinstance(parsed, JsonResponse):
        return parsed

    try:
        saved_search = create_saved_search(
            request.user,
            query=parsed.query,
            filters=parsed.to_filters(),
            language=request.LANGUAGE_CODE,
        )
    except QueryTooLongError as exc:
        # HTML parity: the create view refuses an over-cap query with HTTP 400
        # and stores nothing (08-SRCH-011).
        logger.warning(
            "Refused over-cap saved-search query for user %s: %s chars (08-SRCH-011)",
            request.user.pk,
            exc.length,
        )
        return problem(HTTPStatus.BAD_REQUEST, TYPE_QUERY_TOO_LONG, _DETAIL_QUERY_TOO_LONG)

    return JsonResponse(_serialize_saved_search(saved_search, request.LANGUAGE_CODE))


@login_required_api
def saved_search_edit_view(request: HttpRequest, pk: int) -> JsonResponse:
    """``POST /api/v1/saved-searches/{pk}/edit/`` — update a saved search.

    Mirrors :func:`apps.cabinet.views.saved_searches.saved_search_edit`'s POST
    branch: the same shared :func:`update_saved_search` service and the same
    ``LANGUAGE_CODE`` argument. A missing/non-owned ``pk`` is the uniform 404.
    The edit view does not run the query cap, so neither does this endpoint.
    """
    if request.method not in _ALLOWED_METHODS:
        return _method_not_allowed()

    limited = _rate_limited_response(request)
    if limited is not None:
        return limited

    parsed = _parse_write_body(request)
    if isinstance(parsed, JsonResponse):
        return parsed

    try:
        saved_search = update_saved_search(
            request.user,
            pk,
            query=parsed.query,
            filters=parsed.to_filters(),
            language=request.LANGUAGE_CODE,
        )
    except SavedSearch.DoesNotExist:
        return problem(HTTPStatus.NOT_FOUND, TYPE_NOT_FOUND, _DETAIL_NOT_FOUND)

    return JsonResponse(_serialize_saved_search(saved_search, request.LANGUAGE_CODE))


@login_required_api
def saved_search_toggle_view(request: HttpRequest, pk: int) -> JsonResponse:
    """``POST /api/v1/saved-searches/{pk}/toggle/`` — flip ``is_active``.

    Mirrors :func:`apps.cabinet.views.saved_searches.saved_search_toggle`: the
    same shared :func:`toggle_saved_search` service (disable ≠ delete — D9). The
    toggle is idempotent per the plan row 16 (each call flips the stored state).
    """
    if request.method not in _ALLOWED_METHODS:
        return _method_not_allowed()

    limited = _rate_limited_response(request)
    if limited is not None:
        return limited

    try:
        saved_search = toggle_saved_search(request.user, pk)
    except SavedSearch.DoesNotExist:
        return problem(HTTPStatus.NOT_FOUND, TYPE_NOT_FOUND, _DETAIL_NOT_FOUND)

    return JsonResponse(_serialize_saved_search(saved_search, request.LANGUAGE_CODE))


@login_required_api
def saved_search_delete_view(request: HttpRequest, pk: int) -> JsonResponse:
    """``POST /api/v1/saved-searches/{pk}/delete/`` — delete the row.

    Mirrors :func:`apps.cabinet.views.saved_searches.saved_search_delete`: the
    same shared :func:`delete_saved_search` service (removal, distinct from
    disable — D9). Answers the Q8 idempotent confirmed state
    ``{"id": <pk>, "deleted": true}``; the cleared state is re-retrievable (the
    row is gone from the S2.7 list).
    """
    if request.method not in _ALLOWED_METHODS:
        return _method_not_allowed()

    limited = _rate_limited_response(request)
    if limited is not None:
        return limited

    try:
        delete_saved_search(request.user, pk)
    except SavedSearch.DoesNotExist:
        return problem(HTTPStatus.NOT_FOUND, TYPE_NOT_FOUND, _DETAIL_NOT_FOUND)

    return JsonResponse({"id": pk, "deleted": True})


__all__ = [
    "TYPE_NOT_FOUND",
    "TYPE_QUERY_TOO_LONG",
    "SavedSearchWriteInput",
    "saved_search_create_view",
    "saved_search_delete_view",
    "saved_search_edit_view",
    "saved_search_toggle_view",
    "saved_searches_collection_view",
]
