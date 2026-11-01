"""
JSON moderation single-action endpoints (S4.7) — plan §2.4 row 13.

Three staff-only writes sharing one pipeline and one shared service tier:

- ``POST /api/v1/moderation/approve/{id}/`` — ``admin_actions.approve_ad``
- ``POST /api/v1/moderation/reject/{id}/``  — ``admin_actions.reject_ad``
- ``POST /api/v1/moderation/ban/{id}/``     — ``admin_actions.ban_user_for_ad``

Each one is the JSON sibling of the matching HTML action view
(:func:`apps.moderation.views.review.approve_ad`, ``…reject_ad`` and
``…ban_user``) and calls the **same** :mod:`apps.moderation.admin_actions`
function inside the same ``transaction.atomic()`` + ``select_for_update()``
block, so the moderator action-log rows, the priority rows, the status
timestamps and the analytics events are identical by construction. No API-only
business predicate is introduced. ``admin_actions`` itself is untouched.

Pipeline (fixed order):

1. **Identity / method** — ``staff_required_api_problem(methods=("POST",))``
   answers an anonymous request with a 401 ``unauthenticated`` problem (identity
   before method), a non-staff request with a 403 ``forbidden`` problem, and any
   verb but ``POST`` with a 405 ``method_not_allowed`` problem carrying
   ``Allow: POST``. None carries a ``WWW-Authenticate`` challenge (09-API-010).
2. **Rate limit** — ``api_write`` / ``RateLimitBudget.API_WRITE`` (30 req / 60 s),
   the same namespace every other ``/api/v1/`` write spends (plan Q4), so a 429
   ``rate_limited`` problem + ``Retry-After`` is answered before any row is
   resolved. The frozen bulk endpoint (``api_bulk.py``) carries **no** limiter;
   the plan assigns the ``api_write`` namespace to every ``/api/v1/`` write, and
   doc §R-F2 / the change log record this deliberate posture delta (the bulk
   contract itself is untouched — it simply never uses the new namespace).
3. **Ad resolution** — a **missing** ad is the uniform 404 ``not_found`` problem
   (CWE-209) for every action.

Result → HTTP mapping (§2.5 / ``docs/01-spec/api-surface.md``):

| Outcome                                        | HTTP                                   |
|---|---|
| ``ApproveOutcome.PUBLISHED``                   | 200 ``{outcome: "published"}``          |
| ``ApproveOutcome.CRITERIA_REJECTED``           | 200 ``{outcome: "criteria_rejected"}`` (ad parked) |
| ``ApproveOutcome.TRANSITION_REFUSED``          | 409 ``transition_refused``              |
| reject committed                               | 200 ``{outcome: "rejected"}``           |
| already ``REJECTED``                           | 200 ``{outcome: "already_rejected"}`` (no-op, as HTML) |
| reject on a status without ``-> REJECTED``     | 409 ``invalid_transition``              |
| ban ``changed >= 1``                           | 200 ``{outcome: "banned", changed, …}`` |
| already banned                                 | 200 ``{outcome: "already_banned"}``     |
| ban refused (self / privileged / unknown owner)| 403 ``ban_refused`` (cause token only, no counts) |

Deliberate HTML-vs-API differences (documented in
``docs/01-spec/api-surface.md``):

- **Wrong status.** The HTML approve/reject views resolve through
  ``get_object_or_404(status__in={ON_MODERATION, ON_MODERATION_FAILED})`` and
  redirect with a warning when the service refuses; the JSON surface reports the
  refusal as the §2.5 taxonomy outcome (409 ``transition_refused`` /
  ``invalid_transition``) so a machine caller is never told "done" for a request
  that committed nothing. The **ban** HTML view resolves the ad without a status
  precondition, so the API does the same (the ban lever is on the account, not
  the ad).
- **Reason composition.** ``reject`` builds the audit reason exactly as the HTML
  view does — ``"<reason_category>"`` or ``"<reason_category>: <reason_text>"`` —
  from the same ``CategoryRejectReason`` vocabulary, so the stored
  ``ModeratorActionLog.reason`` (and therefore
  ``moderation_analytics.get_rejection_reasons``) matches.
- **Ban reason default.** The HTML view reads ``request.POST["ban_reason"]`` and
  falls back to ``"No reason provided"``; the body field ``ban_reason`` defaults
  to the same string.

No CSRF exemption is applied: these writes use the middleware chain as-is and are
POST-only, like every other ``/api/v1/`` write.
"""

import logging
from http import HTTPStatus
from typing import Any, Final

from django.db import DatabaseError, transaction
from django.http import HttpRequest, JsonResponse
from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _
from pydantic import ValidationError

from apps.ads.models import Ad
from apps.core.enums import (
    AdStatus,
    ApproveOutcome,
    CategoryRejectReason,
    RateLimitBudget,
)
from apps.core.schemas import BaseInputModel
from apps.core.utils.api_auth import staff_required_api_problem
from apps.core.utils.db_lock_timeout import is_lock_timeout
from apps.core.utils.problem import (
    PROBLEM_CONTENT_TYPE,
    problem,
    rate_limited_problem,
    validation_problem,
)
from apps.moderation.admin_actions import (
    BanResult,
    approve_ad,
    ban_refusal_reason,
    ban_user_for_ad,
    reject_ad,
)
from apps.search.services.rate_limit import rate_limit_check

logger = logging.getLogger(__name__)

# Stable ASCII ``type`` tokens (never translated). ``not_found`` is the same
# token every other ``/api/v1/`` ad surface emits.
TYPE_NOT_FOUND: Final[str] = "not_found"
TYPE_TRANSITION_REFUSED: Final[str] = "transition_refused"
TYPE_INVALID_TRANSITION: Final[str] = "invalid_transition"
TYPE_BAN_REFUSED: Final[str] = "ban_refused"
TYPE_RETRYABLE: Final[str] = "retryable"

# English msgids (cataloged in the stage i18n batch; ``gettext_lazy`` defers
# resolution to render time so the document is translated for the request locale).
_DETAIL_NOT_FOUND: Final[str | Promise] = _("Ad not found.")
_DETAIL_APPROVE_REFUSED: Final[str | Promise] = _(
    "This ad cannot be published: its current status does not allow the "
    "transition to published."
)
_DETAIL_REJECT_REFUSED: Final[str | Promise] = _(
    "This ad cannot be rejected in its current status."
)
_DETAIL_BAN_REFUSED: Final[str | Promise] = _(
    "The ban was not applied to this ad's owner."
)
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

# The moderation statuses the HTML approve/reject lookups are restricted to.
_REVIEWABLE_STATUSES: Final[list[str]] = [
    AdStatus.ON_MODERATION,
    AdStatus.ON_MODERATION_FAILED,
]

# The HTML ban view's ``request.POST.get("ban_reason", "No reason provided")``
# default, kept byte-identical so the recorded audit reason matches.
_DEFAULT_BAN_REASON: Final[str] = "No reason provided"

# The §2.5 outcome tokens (machine vocabulary, never translated).
OUTCOME_PUBLISHED: Final[str] = ApproveOutcome.PUBLISHED.value
OUTCOME_CRITERIA_REJECTED: Final[str] = ApproveOutcome.CRITERIA_REJECTED.value
OUTCOME_REJECTED: Final[str] = "rejected"
OUTCOME_ALREADY_REJECTED: Final[str] = "already_rejected"
OUTCOME_BANNED: Final[str] = "banned"
OUTCOME_ALREADY_BANNED: Final[str] = "already_banned"


class RejectActionInput(BaseInputModel):
    """Client-input DTO for ``POST /api/v1/moderation/reject/{id}/``.

    The field set mirrors the HTML reject form the view reads:
    ``reason_category`` (a ``CategoryRejectReason`` value — the HTML view
    re-renders on an unknown value; here it is a 422) and ``reason_text`` (free
    text, optional, stripped, appended to the reason as the HTML view does).

    ``reason_text`` deliberately carries no length cap beyond the model's TEXT
    column: the audit writer applies the same redaction it applies to the HTML
    flow, and the HTML form has no cap either.
    """

    reason_category: CategoryRejectReason
    reason_text: str = ""

    def audit_reason(self) -> str:
        """Compose the audit reason exactly as ``moderation.views.review`` does."""
        text = self.reason_text.strip()
        if text:
            return f"{self.reason_category.value}: {text}"
        return self.reason_category.value


class BanActionInput(BaseInputModel):
    """Client-input DTO for ``POST /api/v1/moderation/ban/{id}/``.

    ``ban_reason`` mirrors the HTML ``ban_reason`` form field and defaults to
    the same ``"No reason provided"`` the HTML view falls back to.
    """

    ban_reason: str = _DEFAULT_BAN_REASON


class ApproveActionInput(BaseInputModel):
    """Client-input DTO for ``POST /api/v1/moderation/approve/{id}/``.

    The plan row names no field for approve (the service takes only the ad and
    the moderator), so an **absent or empty** body is valid. A supplied body
    carries **no** declared field, so ``extra="forbid"`` rejects any key with a
    422 ``validation_failed`` problem.
    """


@staff_required_api_problem(methods=_ALLOWED_METHODS)
def approve_view(request: HttpRequest, ad_id: int) -> JsonResponse:
    """``POST /api/v1/moderation/approve/{id}/`` — approve an ad (row 13)."""
    early = _preflight_only(request, ad_id, ApproveActionInput, optional_body=True)
    if early is not None:
        return early

    def _execute(ad: Ad) -> JsonResponse:
        outcome = approve_ad(ad, request.user.id)
        if outcome is ApproveOutcome.TRANSITION_REFUSED:
            return problem(
                HTTPStatus.CONFLICT,
                TYPE_TRANSITION_REFUSED,
                _DETAIL_APPROVE_REFUSED,
            )
        return JsonResponse(_action_payload(ad_id, outcome.value))

    return _run_action(ad_id, _execute)


@staff_required_api_problem(methods=_ALLOWED_METHODS)
def reject_view(request: HttpRequest, ad_id: int) -> JsonResponse:
    """``POST /api/v1/moderation/reject/{id}/`` — reject an ad (row 13)."""
    body, early = _preflight(request, ad_id, RejectActionInput)
    if early is not None:
        return early
    # The reject DTO's ``reason_category`` is required, so a bodyless request
    # has already been refused with a 422 by the pre-flight above.
    assert body is not None, "reject body is required"
    reason = body.audit_reason()

    def _execute(ad: Ad) -> JsonResponse:
        if ad.status in _REVIEWABLE_STATUSES:
            # ``-> REJECTED`` is allowed from exactly this pair (the transition
            # matrix), so the service call below cannot be refused here.
            reject_ad(ad, request.user.id, reason)
            return JsonResponse(_action_payload(ad_id, OUTCOME_REJECTED))
        if ad.status == AdStatus.REJECTED:
            # ``admin_actions.reject_ad`` is a documented no-op on an already
            # rejected ad; the JSON surface reports that terminal state
            # explicitly instead of pretending a new rejection happened. The
            # service is deliberately NOT called, exactly as it does nothing.
            return JsonResponse(_action_payload(ad_id, OUTCOME_ALREADY_REJECTED))
        # Every other status has no ``-> REJECTED`` edge (the HTML view's
        # 404 lookup excludes it; the bulk endpoint reports it per-id). The
        # JSON surface answers the §2.5 state-machine token instead.
        return problem(
            HTTPStatus.CONFLICT, TYPE_INVALID_TRANSITION, _DETAIL_REJECT_REFUSED
        )

    return _run_action(ad_id, _execute)


@staff_required_api_problem(methods=_ALLOWED_METHODS)
def ban_view(request: HttpRequest, ad_id: int) -> JsonResponse:
    """``POST /api/v1/moderation/ban/{id}/`` — ban the ad's owner (row 13)."""
    body, early = _preflight(request, ad_id, BanActionInput, optional_body=True)
    if early is not None:
        return early
    payload = body if body is not None else BanActionInput()

    def _execute(ad: Ad) -> JsonResponse:
        result = ban_user_for_ad(ad, request.user.id, payload.ban_reason)
        return _ban_response(ad_id, result)

    return _run_action(ad_id, _execute)


def _preflight_only(
    request: HttpRequest,
    ad_id: int,
    dto: type[BaseInputModel],
    *,
    optional_body: bool = False,
) -> JsonResponse | None:
    """Run :func:`_preflight` for an action that carries no body field."""
    _, refusal = _preflight(request, ad_id, dto, optional_body=optional_body)
    return refusal


def _preflight[InputT: BaseInputModel](
    request: HttpRequest,
    ad_id: int,
    dto: type[InputT],
    *,
    optional_body: bool = False,
) -> tuple[InputT | None, JsonResponse | None]:
    """Rate limit, validate the body and resolve the ad, in that order.

    Returns ``(payload, refusal)``: exactly one of the two is meaningful — a
    JSON problem response when the stage refuses, or the validated DTO (``None``
    for an optional-body action that sent no body). The payload defaults are
    supplied by the caller so a bodyless approve/ban still reaches the service
    with the HTML flow's own defaults.

    ``optional_body`` marks the actions whose plan row names no body field: an
    absent or empty body is accepted as-is. For the field-carrying reject action
    an empty body is the same 422 the HTML form's missing ``reason_category``
    would be.
    """
    # Rate limit before resolving the ad (api_bulk write ordering): the cost is
    # charged even for a request aimed at a missing id.
    if not rate_limit_check(
        request,
        namespace=_RATE_LIMIT_NAMESPACE,
        budget=RateLimitBudget.API_WRITE,
    ):
        return None, rate_limited_problem(RateLimitBudget.API_WRITE)

    refusal, payload = _validate_body(request, dto, optional_body=optional_body)
    if refusal is not None:
        return None, refusal

    if not Ad.objects.filter(id=ad_id).exists():
        # A missing ad answers the uniform 404 before any status mapping, so the
        # action endpoints never distinguish "absent" from "not actionable".
        return None, problem(HTTPStatus.NOT_FOUND, TYPE_NOT_FOUND, _DETAIL_NOT_FOUND)
    return payload, None


def _validate_body[InputT: BaseInputModel](
    request: HttpRequest,
    dto: type[InputT],
    *,
    optional_body: bool,
) -> tuple[JsonResponse | None, InputT | None]:
    """Validate the body against *dto*, returning a 422 problem on failure.

    Content-Type is lenient per the API contract: the body is parsed as JSON
    regardless of the header (``api_bulk.py:74`` norm), so a form post and a
    JSON body are both accepted.
    """
    body = request.body.strip()
    if not body and optional_body:
        return None, None
    try:
        payload = dto.model_validate_json(body or b"{}")
    except ValidationError as exc:
        logger.warning("Invalid moderation action request body: %s", exc)
        return validation_problem(exc), None
    return None, payload


def _run_action(
    ad_id: int,
    call: Any,
) -> JsonResponse:
    """Lock the ad row, run *call* inside one atomic block, map its failures.

    Mirrors the HTML views' ``transaction.atomic()`` + ``select_for_update()``
    around the service call, so the read-then-write is serialized exactly as the
    HTML flow serializes it. A row hard-deleted between the pre-flight and the
    lock answers the same uniform 404; a lock timeout answers the 503
    ``retryable`` problem; any other failure is logged and answered as 503 so
    the JSON surface never returns an HTML error page.
    """
    try:
        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
            ad = Ad.objects.select_for_update().get(id=ad_id)
            return call(ad)
    except Ad.DoesNotExist:
        return problem(HTTPStatus.NOT_FOUND, TYPE_NOT_FOUND, _DETAIL_NOT_FOUND)
    except DatabaseError as exc:
        if not is_lock_timeout(exc):
            raise
        logger.warning(
            "Lock timeout on moderation action for ad %s (SQLSTATE 55P03)", ad_id
        )
        return _retryable_response()
    except Exception:
        # A genuinely unexpected failure (auto_moderate lets a non-DB error
        # escape after parking the ad, set_rejected a broken audit write). The
        # HTML views surface it to Django's 500 handler; the JSON surface
        # answers the generic 503 ``retryable`` problem instead of an HTML error
        # page and never discloses the exception text (CWE-209).
        logger.exception("Moderation action failed for ad %s", ad_id)
        return _retryable_response()


def _retryable_response() -> JsonResponse:
    """Return a 503 ``retryable`` problem with a ``Retry-After`` header."""
    response = problem(
        HTTPStatus.SERVICE_UNAVAILABLE, TYPE_RETRYABLE, _DETAIL_RETRYABLE
    )
    response["Retry-After"] = _RETRY_AFTER_SECONDS
    return response


def _ban_response(ad_id: int, result: BanResult) -> JsonResponse:
    """Map a ``BanResult`` to the §2.5 response (counts or a cause token).

    ``changed >= 1`` is the performed ban (200 with the counts, exactly the
    §2.5 "ban idempotent for agents" shape); an already-banned owner is the
    200 ``already_banned`` no-op; any other zero-change outcome is a refusal
    (self / privileged / owner account gone) answered as 403 ``ban_refused``
    with only the stable ``BanRefusalReason`` token — never the skip counts, so
    no privileged-row count is leaked.
    """
    if result.changed or result.already_in_state:
        outcome = OUTCOME_BANNED if result.changed else OUTCOME_ALREADY_BANNED
        return JsonResponse(
            _action_payload(
                ad_id,
                outcome,
                changed=result.changed,
                already_in_state=result.already_in_state,
            )
        )
    refusal = ban_refusal_reason(result)
    logger.info("Moderation API ban refused for ad %s (%s)", ad_id, refusal)
    return JsonResponse(
        {
            "type": TYPE_BAN_REFUSED,
            "title": str(HTTPStatus.FORBIDDEN.phrase),
            "status": int(HTTPStatus.FORBIDDEN),
            "detail": _DETAIL_BAN_REFUSED,
            "cause": refusal.value,
        },
        status=HTTPStatus.FORBIDDEN,
        content_type=PROBLEM_CONTENT_TYPE,
    )


def _action_payload(ad_id: int, outcome: str, **extra: Any) -> dict[str, Any]:
    """Serialize the post-action ad state plus the outcome token.

    Re-reads the row so the payload carries exactly what the service committed
    (status and every moderation timestamp); the display fields match the
    listings serializer shape (D4), mirroring the lifecycle actions payload.
    """
    ad = Ad.objects.select_related("category", "city").get(id=ad_id)
    payload: dict[str, Any] = {
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
        "rejected_at": _iso(ad.rejected_at),
        "deleted_at": _iso(ad.deleted_at),
        "updated_at": _iso(ad.updated_at),
    }
    payload.update(extra)
    return payload


def _iso(value: Any) -> str | None:
    """Return an ISO-8601 string for an optional datetime."""
    return value.isoformat() if value else None


def _named(obj: Any) -> dict[str, Any] | None:
    """Return ``{"slug", "name"}`` for an optional related object, else ``None``."""
    if obj is None:
        return None
    return {"slug": obj.slug, "name": str(obj.name)}


__all__ = [
    "OUTCOME_ALREADY_BANNED",
    "OUTCOME_ALREADY_REJECTED",
    "OUTCOME_BANNED",
    "OUTCOME_CRITERIA_REJECTED",
    "OUTCOME_PUBLISHED",
    "OUTCOME_REJECTED",
    "TYPE_BAN_REFUSED",
    "TYPE_INVALID_TRANSITION",
    "TYPE_NOT_FOUND",
    "TYPE_RETRYABLE",
    "TYPE_TRANSITION_REFUSED",
    "ApproveActionInput",
    "BanActionInput",
    "RejectActionInput",
    "approve_view",
    "ban_view",
    "reject_view",
]
