"""
JSON ad lifecycle action endpoints (S4.3) — plan §2.4 rows 7, 8 and 9.

Three session-authenticated writes sharing one pipeline and one shared service
tier:

- ``POST /api/v1/ads/{id}/archive/``    — row 7, ``archive_ad`` (S4.1)
- ``POST /api/v1/ads/{id}/reactivate/`` — row 8, ``reactivate_ad`` (S4.1)
- ``POST /api/v1/ads/{id}/delete/``     — row 9, ``delete_ad`` (S4.1)

Each one is the JSON sibling of the matching HTML action view
(:func:`apps.ads.views.edit.ad_archive`, :func:`apps.ads.views.edit.ad_reactivate`
and :func:`apps.ads.views.delete.ad_delete`) and runs the **same**
:mod:`apps.ads.services.lifecycle` state mechanics — ownership, the row lock,
``Ad.transition_to`` and, for reactivation, the ``auto_moderate`` decision in one
atomic block. No API-only business predicate is introduced.

Pipeline (fixed order, one branch per §2.5 taxonomy member):

1. **Identity** — ``login_required_api`` refuses an anonymous request with a 401
   ``unauthenticated`` problem and **no** ``WWW-Authenticate`` (identity before
   method, so an anonymous ``GET`` is 401, not 405).
2. **Method** — anything but ``POST`` is a 405 ``method_not_allowed`` problem
   carrying ``Allow: POST``.
3. **Rate limit** — the shared ``api_write`` namespace / ``API_WRITE`` budget
   (30 req / 60 s) is charged **before** the ad is resolved, mirroring the
   ``api_bulk`` write ordering: 429 ``rate_limited`` problem + ``Retry-After``.
   The whole class of writes shares the one namespace (plan Q4).
4. **Ad resolution + ownership** — a missing ad and a non-owned ad answer the
   **identical** uniform 404 ``not_found`` problem (CWE-209 — existence is never
   leaked). This mirrors the HTML views, which resolve ownership through the
   service's ``Http404`` / ``PermissionDenied``.
5. **Consent gate** — asserted through the shared
   :func:`apps.users.services.account_state.can_create_ad` seam, the same
   predicate the HTML views' ``_seller_may_create_ad`` wraps (auditor A14).
   Refusal is a 403 ``consent_required`` problem. **Delete is gate-free** by
   design (row 9).
6. **Transition** — the S4.1 service call, mapped to the §2.5 outcomes below.

Result → HTTP mapping (documented in ``docs/01-spec/api-surface.md``):

| Service result                               | HTTP                     |
|---|---|
| ``ArchiveResult(archived=True)``             | 200, ``archived_at`` set |
| ``ArchiveResult(archived=False)``            | 409 ``invalid_transition`` |
| ``ReactivateResult(attempted=True, passed=True)`` | 200, status ``published`` |
| ``ReactivateResult(attempted=True, passed=False)`` | 200, status ``on_moderation_failed`` |
| ``ReactivateResult(attempted=False)``        | 409 ``invalid_transition`` |
| ``DeleteResult(deleted=True)``               | 200, status ``deleted`` |
| ``DeleteResult(deleted=False)``              | 409 ``invalid_transition`` |

Every success body is the *post-action* ad state (``id``, ``outcome``, ``status``,
the lifecycle timestamps and the ad's own display fields), so a client never has
to re-read the detail endpoint to learn what happened.

Deliberate HTML-vs-API differences (documented in
``docs/01-spec/api-surface.md``):

- **Wrong status.** The HTML views are a silent no-op (redirect to the
  dashboard) when the ad is not in the status the action needs. The service
  reports that as ``archived=False`` / ``attempted=False``; these endpoints map
  it to a 409 ``invalid_transition`` problem, because a machine caller must not
  be told "done" for a request that committed nothing (§2.5).
- **Consent ordering.** The HTML ``ad_archive`` / ``ad_reactivate`` views assert
  consent **inside** the transaction that performs the transition (ownership ->
  consent -> action, one commit); these endpoints assert it **before** any
  service call, so a consent-refused request provably changes nothing (§2.5
  "consent BEFORE transition").
- **Lock timeout.** No new handling: the service lets ``OperationalError``
  propagate and the existing ``DbLockTimeoutMiddleware`` already renders a 503
  for the lifecycle paths (it names ``ad_archive`` / ``ad_reactivate`` /
  ``ad_delete``), exactly as the HTML flows are served today.

Row 9 says ``204`` for delete. A bare 204 is not re-retrievable machine state
(the same reasoning the S3.2/S3.5 writes recorded), so delete answers the same
200 post-action shape as its two siblings, with ``status: "deleted"`` and
``deleted_at``; the Q8 "confirmed state" clause is what this payload satisfies.

No CSRF exemption is applied: these writes use the middleware chain as-is and
are POST-only, like every other ``/api/v1/`` write.
"""

import logging
from http import HTTPStatus
from typing import Any, Final

from django.db import DatabaseError
from django.http import HttpRequest, JsonResponse
from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _
from pydantic import ValidationError

from apps.ads.models import Ad
from apps.ads.services.lifecycle import (
    DeleteResult,
    archive_ad,
    delete_ad,
    reactivate_ad,
)
from apps.core.enums import RateLimitBudget
from apps.core.schemas import BaseInputModel
from apps.core.utils.api_auth import TYPE_METHOD_NOT_ALLOWED, login_required_api
from apps.core.utils.db_lock_timeout import is_lock_timeout
from apps.core.utils.problem import (
    problem,
    rate_limited_problem,
    validation_problem,
)
from apps.search.services.rate_limit import rate_limit_check
from apps.users.services.account_state import can_create_ad

logger = logging.getLogger(__name__)

# Stable ASCII ``type`` tokens (never translated). ``not_found`` is the same
# token the ad-detail and favorites endpoints already emit for a missing /
# invisible ad.
TYPE_NOT_FOUND: Final[str] = "not_found"
TYPE_CONSENT_REQUIRED: Final[str] = "consent_required"
TYPE_INVALID_TRANSITION: Final[str] = "invalid_transition"
TYPE_RETRYABLE: Final[str] = "retryable"

# English msgids for the detail strings (cataloged in ``ru``/``bs``/``en`` in the
# stage i18n batch; ``gettext_lazy`` defers resolution to render time).
_DETAIL_NOT_FOUND: Final[str | Promise] = _("Ad not found.")
_DETAIL_METHOD_NOT_ALLOWED: Final[str | Promise] = _("Method not allowed.")
_DETAIL_CONSENT_REQUIRED: Final[str | Promise] = _(
    "To manage ads, please accept the personal data storage consent first."
)
_DETAIL_ARCHIVE_REFUSED: Final[str | Promise] = _(
    "This ad cannot be archived in its current status."
)
_DETAIL_REACTIVATE_REFUSED: Final[str | Promise] = _(
    "This ad cannot be reactivated in its current status."
)
_DETAIL_DELETE_REFUSED: Final[str | Promise] = _("This ad is already deleted.")
_DETAIL_RETRYABLE: Final[str | Promise] = _(
    "The server is busy processing another change. Please try again shortly."
)

# Every authenticated ``/api/v1/`` write shares one key namespace (plan Q4).
_RATE_LIMIT_NAMESPACE: Final[str] = "api_write"

# The only allowed method for these write endpoints.
_ALLOWED_METHODS: Final[tuple[str, ...]] = ("POST",)

# Minimum lock_timeout (see DbLockTimeoutMiddleware); a client retry after this
# window cannot land inside the same contention.
_RETRY_AFTER_SECONDS: Final[str] = "30"

# The §2.5 outcome tokens (``EditOutcome``-style machine vocabulary).
OUTCOME_ARCHIVED: Final[str] = "archived"
OUTCOME_REACTIVATED: Final[str] = "reactivated"
OUTCOME_MODERATION_FAILED: Final[str] = "moderation_failed"
OUTCOME_DELETED: Final[str] = "deleted"


class LifecycleActionInput(BaseInputModel):
    """Client-input DTO for the (optional) lifecycle action body.

    All three endpoints are verb-on-the-URL actions: the plan rows name no body
    field, so an **absent or empty** body is valid and accepted as-is. When a
    body *is* supplied it must be a JSON object and it carries **no** declared
    fields, so ``extra="forbid"`` (from :class:`BaseInputModel`) rejects any key
    with a 422 ``validation_failed`` problem instead of silently ignoring a
    caller's mistaken assumption that it can pass, say, a reason or a target
    status.
    """


@login_required_api
def archive_view(request: HttpRequest, ad_id: int) -> JsonResponse:
    """``POST /api/v1/ads/{id}/archive/`` — archive the caller's own ad (row 7).

    Auth: SESS + owner + **consent** (row 7, mirroring ``ad_archive``).
    """
    early = _preflight(request, ad_id)
    if early is not None:
        return early

    consent_refusal = _consent_refusal(request, ad_id)
    if consent_refusal is not None:
        return consent_refusal

    return _run_transition(
        ad_id,
        lambda: archive_ad(ad_id, request.user.id),
        _map_archive_result,
    )


@login_required_api
def reactivate_view(request: HttpRequest, ad_id: int) -> JsonResponse:
    """``POST /api/v1/ads/{id}/reactivate/`` — reactivate an archived ad (row 8).

    Auth: SESS + owner + consent. A failed content check is **not** an error: it
    commits the ad as ``ON_MODERATION_FAILED`` (hidden pending human review),
    which is a well-formed terminal outcome and answers 200 with that state.
    """
    early = _preflight(request, ad_id)
    if early is not None:
        return early

    consent_refusal = _consent_refusal(request, ad_id)
    if consent_refusal is not None:
        return consent_refusal

    return _run_transition(
        ad_id,
        lambda: reactivate_ad(ad_id, request.user.id),
        _map_reactivate_result,
    )


@login_required_api
def delete_view(request: HttpRequest, ad_id: int) -> JsonResponse:
    """``POST /api/v1/ads/{id}/delete/`` — soft-delete the caller's own ad (row 9).

    Auth: SESS + owner only — the delete flow is **gate-free** by design (no
    consent / audience predicate), exactly as ``apps.ads.views.delete``.
    """
    early = _preflight(request, ad_id)
    if early is not None:
        return early

    return _run_transition(
        ad_id,
        lambda: delete_ad(ad_id, request.user.id),
        _map_delete_result,
    )


def _preflight(request: HttpRequest, ad_id: int) -> JsonResponse | None:
    """Run method gate, rate limit, body validation and ownership, in order.

    Returns the refusal response when a stage refuses, or ``None`` when the
    request may proceed to the consent gate / transition.
    """
    if request.method not in _ALLOWED_METHODS:
        response = problem(
            HTTPStatus.METHOD_NOT_ALLOWED,
            TYPE_METHOD_NOT_ALLOWED,
            _DETAIL_METHOD_NOT_ALLOWED,
        )
        response["Allow"] = ", ".join(_ALLOWED_METHODS)
        return response

    # Rate limit before resolving the ad (api_bulk write ordering): the cost is
    # charged even for a request aimed at a missing id.
    if not rate_limit_check(
        request,
        namespace=_RATE_LIMIT_NAMESPACE,
        budget=RateLimitBudget.API_WRITE,
    ):
        return rate_limited_problem(RateLimitBudget.API_WRITE)

    body_refusal = _validate_optional_body(request)
    if body_refusal is not None:
        return body_refusal

    return _ownership_refusal(ad_id, request.user.id)


def _validate_optional_body(request: HttpRequest) -> JsonResponse | None:
    """Accept an absent / empty / non-JSON body; reject a malformed JSON object.

    Django's test client (and a browser form POST) sends
    ``application/x-www-form-urlencoded``, so the body is parsed through a small
    explicit switch rather than blindly as JSON (the lenient Content-Type clause
    of the API contract applies to bodies that *are* JSON):

    - **empty** — nothing to validate; the plan rows carry no body field, so the
      action proceeds.
    - **``application/json``** — validated strictly: a non-object, an array or an
      undeclared key is a 422 ``validation_failed`` problem.
    - **any other content type** — an HTML form post; the plan rows declare no
      form field, so it is accepted as the empty body. Nothing in the form is
      ever read, so no caller-supplied value can influence the action.
    """
    body = request.body.strip()
    if not body:
        return None
    content_type = (request.content_type or "").lower()
    if content_type != "application/json":
        return None
    try:
        LifecycleActionInput.model_validate_json(body)
    except ValidationError as exc:
        logger.warning("Invalid lifecycle action request body: %s", exc)
        return validation_problem(exc)
    return None


def _ownership_refusal(ad_id: int, user_id: int) -> JsonResponse | None:
    """Return the uniform 404 for a missing or non-owned ad, else ``None``.

    Ownership is resolved before any gate or write so a non-owner learns
    nothing about the ad's existence or status (CWE-209). ``select_related``
    keeps the post-action serialization free of extra queries.
    """
    ad = Ad.objects.select_related("category", "city").filter(id=ad_id).first()
    if ad is None or ad.user_id != user_id:
        return problem(HTTPStatus.NOT_FOUND, TYPE_NOT_FOUND, _DETAIL_NOT_FOUND)
    return None


def _consent_refusal(request: HttpRequest, ad_id: int) -> JsonResponse | None:
    """Return the 403 ``consent_required`` problem when consent is absent.

    The gate is the shared :func:`can_create_ad` predicate (A14) — the same
    rule ``ad_archive`` / ``ad_reactivate`` consult through
    ``_seller_may_create_ad``. It runs **before** the service call, so a
    consent-refused request provably leaves the ad untouched (the HTML views
    assert it later in the flow; the API's ordering is the stricter taxonomy
    order — §2.5).
    """
    if can_create_ad(request.user):
        return None
    logger.warning(
        "User %s refused ad %s lifecycle action: storage consent required",
        request.user.id,
        ad_id,
    )
    return problem(
        HTTPStatus.FORBIDDEN, TYPE_CONSENT_REQUIRED, _DETAIL_CONSENT_REQUIRED
    )


def _run_transition(
    ad_id: int,
    call: Any,
    mapper: Any,
) -> JsonResponse:
    """Call a lifecycle service function and map its result to a response.

    The service speaks the project's exceptions: ``Http404`` for a missing row
    and ``PermissionDenied`` for a non-owner (both already resolved by the
    ownership pre-flight, but a concurrent delete can still surface the 404).
    A lock timeout propagates to ``DbLockTimeoutMiddleware``, which answers the
    503; every other failure that the service lets through is rendered here as
    the 503 ``retryable`` problem so the JSON surface never answers HTML.
    """
    from django.core.exceptions import PermissionDenied
    from django.http import Http404

    try:
        result = call()
    except Http404:
        return problem(HTTPStatus.NOT_FOUND, TYPE_NOT_FOUND, _DETAIL_NOT_FOUND)
    except PermissionDenied:
        return problem(HTTPStatus.NOT_FOUND, TYPE_NOT_FOUND, _DETAIL_NOT_FOUND)
    except DatabaseError as exc:
        if is_lock_timeout(exc):
            logger.warning(
                "Lock timeout on lifecycle action for ad %s (SQLSTATE 55P03)", ad_id
            )
            return _retryable_response()
        raise
    except Exception:
        # ``auto_moderate`` raising a non-database error rolls the transition
        # back (the ad stays ARCHIVED, the safe state) — the HTML view reports
        # it as a dashboard message; the JSON surface reports the transient
        # condition instead of a bare 500.
        logger.exception("Lifecycle action failed for ad %s", ad_id)
        return _retryable_response()

    refusal = mapper(result)
    if refusal is not None:
        return refusal
    return JsonResponse(_serialize_action_state(ad_id, result))


def _retryable_response() -> JsonResponse:
    """Return a 503 ``retryable`` problem with a ``Retry-After`` header."""
    response = problem(HTTPStatus.SERVICE_UNAVAILABLE, TYPE_RETRYABLE, _DETAIL_RETRYABLE)
    response["Retry-After"] = _RETRY_AFTER_SECONDS
    return response


def _map_archive_result(result: DeleteResult) -> JsonResponse | None:
    """409 ``invalid_transition`` when the ad was not PUBLISHED, else ``None``."""
    if not result.archived:
        return problem(
            HTTPStatus.CONFLICT, TYPE_INVALID_TRANSITION, _DETAIL_ARCHIVE_REFUSED
        )
    return None


def _map_reactivate_result(result: Any) -> JsonResponse | None:
    """409 ``invalid_transition`` when the ad was not ARCHIVED, else ``None``.

    ``attempted=True`` is a success for **both** moderation verdicts: a pass
    publishes the ad, a fail parks it as ``ON_MODERATION_FAILED``. The verdict
    travels in the body's ``outcome`` field, never as a 4xx (boundary rule O-2a:
    a failed check still committed a state change).
    """
    if not result.attempted:
        return problem(
            HTTPStatus.CONFLICT, TYPE_INVALID_TRANSITION, _DETAIL_REACTIVATE_REFUSED
        )
    return None


def _map_delete_result(result: Any) -> JsonResponse | None:
    """409 ``invalid_transition`` for an already-DELETED ad, else ``None``."""
    if not result.deleted:
        return problem(
            HTTPStatus.CONFLICT, TYPE_INVALID_TRANSITION, _DETAIL_DELETE_REFUSED
        )
    return None


def _serialize_action_state(ad_id: int, result: Any) -> dict[str, Any]:
    """Serialize the post-action ad state for a successful lifecycle action.

    Re-reads the row so the payload carries exactly what ``Ad.transition_to``
    (and, for reactivation, ``auto_moderate``) committed — never a stale local
    copy. The display fields match the listings/dashboard serializer shape (D4);
    the lifecycle block names the action, its outcome token and every lifecycle
    timestamp so the three endpoints answer one consistent shape.
    """
    ad = Ad.objects.select_related("category", "city").get(id=ad_id)
    outcome = _outcome_token(result)
    return {
        "id": ad.id,
        "outcome": outcome,
        "status": ad.status,
        "title": ad.get_title(),
        "price": str(ad.price_amount) if ad.price_amount is not None else None,
        "currency": ad.price_currency,
        "city": _named(ad.city),
        "category": _named(ad.category),
        "published_at": _iso(ad.published_at),
        "archived_at": _iso(ad.archived_at),
        "moderation_failed_at": _iso(ad.moderation_failed_at),
        "deleted_at": _iso(ad.deleted_at),
        "updated_at": _iso(ad.updated_at),
    }


def _outcome_token(result: Any) -> str:
    """Map a lifecycle service result to its machine outcome token."""
    if isinstance(result, DeleteResult):
        return OUTCOME_DELETED
    if hasattr(result, "archived"):
        return OUTCOME_ARCHIVED
    # ReactivateResult: ``passed`` is True (published), False (parked) or None.
    return OUTCOME_REACTIVATED if result.passed else OUTCOME_MODERATION_FAILED


def _iso(value: Any) -> str | None:
    """Return an ISO-8601 string for an optional datetime."""
    return value.isoformat() if value else None


def _named(obj: Any) -> dict[str, Any] | None:
    """Return ``{"slug", "name"}`` for an optional related object, else ``None``."""
    if obj is None:
        return None
    return {"slug": obj.slug, "name": str(obj.name)}


__all__ = [
    "OUTCOME_ARCHIVED",
    "OUTCOME_DELETED",
    "OUTCOME_MODERATION_FAILED",
    "OUTCOME_REACTIVATED",
    "TYPE_CONSENT_REQUIRED",
    "TYPE_INVALID_TRANSITION",
    "TYPE_NOT_FOUND",
    "TYPE_RETRYABLE",
    "LifecycleActionInput",
    "archive_view",
    "delete_view",
    "reactivate_view",
]
