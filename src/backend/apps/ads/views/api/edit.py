"""
JSON ad edit endpoint (S4.4) — ``POST /api/v1/ads/{id}/edit/`` (plan §2.4 row 6).

The JSON sibling of :func:`apps.ads.views.edit.ad_edit`. It consumes the **same**
shared edit-flow stack (:mod:`apps.ads.services.edit_flow`, S4.2) —
:func:`can_edit_ad`, :func:`apply_edit_payload` and the ``EditOutcome`` union —
so the five status branches, the frozen "price-only and direct-save never
funnel through ``submit_ad``" rule and the moderation re-entry behaviour cannot
drift between the surfaces. No API-only business predicate exists here.

Pipeline (fixed order, one branch per §2.5 taxonomy member):

1. **Identity** — ``login_required_api`` (401 ``unauthenticated``, no
   ``WWW-Authenticate``; identity before method).
2. **Method** — POST-only (405 ``method_not_allowed`` + ``Allow: POST``).
3. **Rate limit** — shared ``api_write`` / ``API_WRITE`` (429 ``rate_limited`` +
   ``Retry-After``), charged before the ad is resolved.
4. **Body (O-27)** — :class:`AdEditBody` validates the **same field set**
   :class:`~apps.ads.services.submission.AdEditInput` accepts (title,
   description, price_amount, price_currency) plus the ``reactivate`` flag, in
   snake_case, and is converted by :meth:`AdEditBody.to_edit_input` into the
   shared DTO. A malformed body or a failed body-level rule is a 422
   ``validation_failed`` problem; nothing is read from the ad or written.
5. **Resolution + ownership** — a missing ad and a **non-owned** ad answer the
   identical uniform 404 ``not_found`` problem (CWE-209).
6. **Consent** — the shared :func:`apps.users.services.account_state.can_create_ad`
   seam (auditor A14), the same predicate the HTML view's
   ``_seller_may_create_ad`` wraps → 403 ``consent_required``.
7. **Editability** — ``can_edit_ad`` (ownership was already proven, so this
   reduces to the affordance set ``EDIT_FORM_AVAILABLE_STATUSES``); an owner
   whose ad cannot be edited in its status answers 409 ``not_editable`` *before*
   any write.
8. **Transition** — ``apply_edit_payload`` under the HTML view's transaction +
   ``select_for_update`` lock, with the body's raw ``reactivate`` flag (the
   service derives the ``ARCHIVED`` conjunct, exactly as the HTML view relies
   on it).

Result → HTTP mapping (documented in ``docs/01-spec/api-surface.md``). The
service reports two orthogonal facts (``EditResult.outcome`` = which branch ran,
``EditResult.submission_outcome`` = what ``submit_ad`` said); success is
``submission_outcome is SubmitAdOutcome.PUBLISHED``, never the branch label:

| ``EditResult``                                        | HTTP |
|---|---|
| ``REACTIVATED`` / ``RESUBMITTED`` + ``PUBLISHED``     | 200 + post-edit ad state |
| ``REACTIVATED`` / ``RESUBMITTED`` + ``MODERATION_FAILED`` | 200 + state ``on_moderation_failed`` |
| ``REACTIVATED`` / ``RESUBMITTED`` + ``CONSENT_REQUIRED`` | 403 ``consent_required`` |
| ``REACTIVATED`` / ``RESUBMITTED`` + ``INVALID_TRANSITION`` | 409 ``invalid_transition`` |
| ``REACTIVATED`` / ``RESUBMITTED`` + ``DRAFT_GONE``    | 409 ``draft_gone`` |
| ``REACTIVATED`` / ``RESUBMITTED`` + ``PHOTO_UNAVAILABLE`` | 409 ``photo_unavailable`` |
| ``PRICE_UPDATED``                                     | 200 + post-edit ad state |
| ``DIRECT_SAVED``                                      | 200 + post-edit ad state |
| ``REFUSED`` (status-set refusal, no submission)       | 409 ``invalid_transition`` |

The four refusal rows reuse the ``submit_ad`` outcome tokens verbatim (declared
locally, never imported from ``apps.ads.views.api.submit`` — that would add an
R-F2 mirror edge). They are checked **before** the ``REFUSED`` row: the two are
mutually exclusive in practice (``REFUSED`` never calls ``submit_ad``, and the
submit branches always pass the affordance predicate), and the order keeps the
honest per-outcome mapping first.

``REFUSED`` is surfaced as ``invalid_transition`` rather than ``not_editable``
because by the time the service returns it the request's status **did** pass the
affordance predicate (an ``ARCHIVED`` ad edited without ``reactivate``): the
refusal is a state-machine shortfall, not the "this ad has no edit form" case
that §2.5 answers with ``not_editable``. Both tokens are the taxonomy's own; no
new token is minted.

A moderation failure is **not** an error: the payload was committed by
``submit_ad`` and the ad was parked as ``ON_MODERATION_FAILED`` (boundary rule
O-2a — a change *was* committed), so it is a 200 carrying the published
``errors`` strings and the parked status.

Deliberate HTML-vs-API differences (documented):

- **Refusal.** HTML renders the edit form with HTTP 200 and an error message
  for every non-``PUBLISHED`` submission outcome as well as for the status-set
  refusal (auditor A5); the API answers the 403/409 problems above.
- **Lock timeout.** HTML re-renders the form with the busy message; the API
  answers the 503 ``retryable`` problem with ``Retry-After: 30``, the documented
  exception for this route.
- **Consent ordering.** The HTML view asserts consent before its POST row lock
  (S4.2); the API asserts it here, and additionally maps ``submit_ad``'s own
  ``CONSENT_REQUIRED`` outcome to 403 (the consent race: consent withdrawn
  between this view's gate and ``submit_ad``'s re-read). The outcome is read
  from the returned ``EditResult`` — no request-time patching of the service.

No CSRF exemption is applied: this write uses the middleware chain as-is.
"""

import logging
from decimal import Decimal, InvalidOperation
from http import HTTPStatus
from typing import Any, Final

from django.db import DatabaseError, transaction
from django.http import HttpRequest, JsonResponse
from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _
from pydantic import Field, ValidationError, field_validator

from apps.ads.models import Ad
from apps.ads.services.edit_flow import (
    EditOutcome,
    apply_edit_payload,
    can_edit_ad,
)
from apps.ads.services.submission import (
    AdEditInput,
    SubmitAdOutcome,
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
from apps.currencies.enums import CurrencyCode
from apps.search.services.rate_limit import rate_limit_check
from apps.users.services.account_state import can_create_ad

logger = logging.getLogger(__name__)

# Stable ASCII ``type`` tokens (never translated).
TYPE_NOT_FOUND: Final[str] = "not_found"
TYPE_CONSENT_REQUIRED: Final[str] = "consent_required"
TYPE_NOT_EDITABLE: Final[str] = "not_editable"
TYPE_INVALID_TRANSITION: Final[str] = "invalid_transition"
TYPE_DRAFT_GONE: Final[str] = "draft_gone"
TYPE_PHOTO_UNAVAILABLE: Final[str] = "photo_unavailable"

# English msgids for the detail strings (cataloged in ``ru``/``bs``/``en`` in the
# stage i18n batch; ``gettext_lazy`` defers resolution to render time).
_DETAIL_NOT_FOUND: Final[str | Promise] = _("Ad not found.")
_DETAIL_METHOD_NOT_ALLOWED: Final[str | Promise] = _("Method not allowed.")
_DETAIL_CONSENT_REQUIRED: Final[str | Promise] = _(
    "To manage ads, please accept the personal data storage consent first."
)
_DETAIL_NOT_EDITABLE: Final[str | Promise] = _(
    "This ad cannot be edited in its current status."
)
_DETAIL_INVALID_TRANSITION: Final[str | Promise] = _(
    "The ad cannot take that edit in its current status."
)
_DETAIL_DRAFT_GONE: Final[str | Promise] = _(
    "The draft no longer exists. Please start a new ad."
)
_DETAIL_PHOTO_UNAVAILABLE: Final[str | Promise] = _(
    "One of the photos is no longer available. Please upload it again."
)

# Every authenticated ``/api/v1/`` write shares one key namespace (plan Q4).
_RATE_LIMIT_NAMESPACE: Final[str] = "api_write"

# The only allowed method for this write endpoint.
_ALLOWED_METHODS: Final[tuple[str, ...]] = ("POST",)

# Truthy form values (the HTML form posts ``reactivate=1``; a JSON body posts a
# real boolean). Anything else non-falsy is truthy, as ``if request.POST.get``
# treated it in the HTML view.
_FALSEY_STRINGS: Final[frozenset[str]] = frozenset({"", "0", "false", "no", "off"})


class AdEditBody(BaseInputModel):
    """Client-input DTO for the edit body (O-27).

    The field set is exactly the one :class:`AdEditInput` accepts — ``title``,
    ``description``, ``price_amount``, ``price_currency`` — in snake_case JSON,
    plus the ``reactivate`` flag the HTML form carries as a separate POST key.

    The O-27 parity rules encoded here:

    - **The edit request repeats all fields.** Every field defaults to the value
      its HTML form element sends when blank, so an omitted field means the
      empty value, never "leave unchanged": text → ``""``, price → ``"0"``
      (Free). This is the single most important O-27 rule — a partial body must
      not silently become a partial update.
    - **The currency tuple is ``price_currency`` ``CurrencyCode``-or-absent.**
      An absent/blank value means "keep the ad's stored currency" (the
      ``resolve_edit_currency`` fallback). A value outside the enum is a 422 —
      a machine caller's typo'd currency can never be swallowed by the HTML
      form's ``except ValueError: pass`` fallback.
    - **``price_amount`` is a non-negative decimal.** A string is parsed exactly
      as the HTML form parses it (blank/unparseable → Free), so the string and
      number forms agree; a negative price is a 422 (a state the HTML form
      cannot express through its validator, and one no edit should commit).

    ``extra="forbid"`` (from :class:`BaseInputModel`) makes a misspelled or
    unexpected key a 422 instead of a silently ignored field.
    """

    title: str = ""
    description: str = ""
    # ``Any`` so the ``before`` validator owns coercion (blank → Free, string and
    # number forms agree) instead of Pydantic's own strict parse rejecting the
    # forms ``AdEditInput`` deliberately tolerates.
    price_amount: Any = Decimal("0")
    price_currency: str | None = None
    reactivate: bool = Field(default=False)

    @field_validator("title", "description", mode="before")
    @classmethod
    def _strip_text(cls, v: Any) -> str:
        """Strip surrounding whitespace and coerce ``None`` to the empty string."""
        if v is None:
            return ""
        return str(v).strip()

    @field_validator("price_amount", mode="before")
    @classmethod
    def _coerce_price_amount(cls, v: Any) -> Decimal:
        """Blank / unparseable price → ``Decimal("0")`` (Free), as HTML does."""
        if v is None or v == "":
            return Decimal("0")
        try:
            parsed = Decimal(str(v))
        except (InvalidOperation, ValueError):
            return Decimal("0")
        if parsed < 0:
            raise ValueError("price_amount must not be negative")
        return parsed

    @field_validator("price_currency", mode="before")
    @classmethod
    def _coerce_currency(cls, v: Any) -> str:
        """Normalize blank to ``""``; anything else is validated in ``to_edit_input``."""
        if v is None or v == "":
            return ""
        return str(v).strip().upper()

    @field_validator("reactivate", mode="before")
    @classmethod
    def _coerce_reactivate(cls, v: Any) -> bool:
        """Accept a real boolean or the HTML form's truthy string."""
        if v is None:
            return False
        if isinstance(v, str):
            return v.strip().lower() not in _FALSEY_STRINGS
        return bool(v)

    def to_edit_input(self) -> AdEditInput:
        """Build the shared :class:`AdEditInput` this body describes.

        The conversion is deliberate so the API body and the HTML POST land on
        the **same** DTO: the text fields are already coerced, and the currency
        string is resolved to a :class:`CurrencyCode` (or ``None``) here — the
        one place a bad currency is reported.

        Raises:
            ValueError: The currency is not a member of ``CurrencyCode``.
        """
        currency: CurrencyCode | None = None
        if self.price_currency:
            currency = CurrencyCode(self.price_currency)
        return AdEditInput(
            title=self.title,
            description=self.description,
            price_amount=self.price_amount,
            price_currency=currency,
        )


@login_required_api
def edit_view(request: HttpRequest, ad_id: int) -> JsonResponse:
    """``POST /api/v1/ads/{id}/edit/`` — apply an edit payload (plan row 6)."""
    if request.method not in _ALLOWED_METHODS:
        response = problem(
            HTTPStatus.METHOD_NOT_ALLOWED,
            TYPE_METHOD_NOT_ALLOWED,
            _DETAIL_METHOD_NOT_ALLOWED,
        )
        response["Allow"] = ", ".join(_ALLOWED_METHODS)
        return response

    if not rate_limit_check(
        request,
        namespace=_RATE_LIMIT_NAMESPACE,
        budget=RateLimitBudget.API_WRITE,
    ):
        return rate_limited_problem(RateLimitBudget.API_WRITE)

    parsed = _parse_body(request)
    if isinstance(parsed, JsonResponse):
        return parsed
    body = parsed

    ad = Ad.objects.select_related("category", "city").filter(id=ad_id).first()
    if ad is None or ad.user_id != request.user.id:
        # Missing and non-owned ads answer the identical document (CWE-209).
        return problem(HTTPStatus.NOT_FOUND, TYPE_NOT_FOUND, _DETAIL_NOT_FOUND)

    if not can_create_ad(request.user):
        logger.warning(
            "User %s refused ad %s edit: storage consent required",
            request.user.id,
            ad_id,
        )
        return problem(
            HTTPStatus.FORBIDDEN, TYPE_CONSENT_REQUIRED, _DETAIL_CONSENT_REQUIRED
        )

    if not can_edit_ad(ad, request.user.id):
        return problem(HTTPStatus.CONFLICT, TYPE_NOT_EDITABLE, _DETAIL_NOT_EDITABLE)

    return _apply(ad, body)


def _parse_body(request: HttpRequest) -> AdEditBody | JsonResponse:
    """Validate the edit body; return the DTO or a 422 problem document.

    A JSON object is validated field-by-field and its currency resolved through
    :meth:`AdEditBody.to_edit_input`. A form-encoded body (the content type the
    HTML edit form sends) is converted through :meth:`AdEditBody.model_validate`
    so both shapes land on the same DTO.

    Every body-level failure is a 422 ``validation_failed`` problem carrying the
    standard sanitized ``errors`` envelope — a currency outside the enum and a
    non-JSON body included, so no caller can reach the write path with a value
    the DTO did not accept.
    """
    try:
        if request.content_type == "application/json":
            body = AdEditBody.model_validate_json(request.body)
        else:
            body = AdEditBody.model_validate(
                {key: request.POST.get(key) for key in request.POST}
            )
        body.to_edit_input()
    except ValidationError as exc:
        logger.warning("Invalid ad edit request body: %s", exc)
        return validation_problem(exc)
    except ValueError as exc:
        # ``to_edit_input`` refused the currency, or the body was not JSON (the
        # JSON decode error is a ``ValueError``). Report a 422 in the standard
        # envelope, never a silent currency change.
        logger.warning("Invalid ad edit body: %s", exc)
        return _body_validation_problem(str(exc))
    return body

def _body_validation_problem(message: str) -> JsonResponse:
    """Build a 422 ``validation_failed`` problem for a non-Pydantic body error.

    Reuses :func:`problem` (never a hand-built document) with the stable
    ``validation_failed`` token, and carries the same ``errors`` list shape the
    Pydantic path produces (``{type, loc, msg}`` per entry) so a client parses
    one envelope for every 422.
    """
    from django.utils.translation import gettext as _t

    from apps.core.utils.problem import (
        TYPE_VALIDATION_FAILED,
        _problem_response,
    )

    return _problem_response(
        HTTPStatus.UNPROCESSABLE_ENTITY,
        {
            "type": TYPE_VALIDATION_FAILED,
            "title": HTTPStatus.UNPROCESSABLE_ENTITY.phrase,
            "status": HTTPStatus.UNPROCESSABLE_ENTITY,
            "detail": _t("Request body failed validation."),
            "errors": [
                {"type": "value_error", "loc": ["body"], "msg": message}
            ],
        },
    )


def _apply(ad: Ad, body: AdEditBody) -> JsonResponse:
    """Lock the ad and apply the payload through the shared edit-flow service.

    Mirrors ``ad_edit``'s POST block: ``transaction.atomic()`` +
    ``select_for_update()`` and the body's raw ``reactivate`` flag (the service
    derives the ``ARCHIVED`` conjunct). The typed :class:`EditResult` is read
    directly — no request-time patching of the service. A lock timeout keeps the
    03-DB-004 boundary and is answered as the 503 ``retryable`` problem (this
    route has a JSON error surface where the HTML route re-renders a form).
    """
    try:
        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]  # django-stubs not installed; Atomic lacks CM stubs
            locked = Ad.objects.select_for_update().get(id=ad.id)
            result = apply_edit_payload(locked, body.to_edit_input(), body.reactivate)
    except Ad.DoesNotExist:
        # Raced with a hard delete between the pre-flight fetch and the lock.
        return problem(HTTPStatus.NOT_FOUND, TYPE_NOT_FOUND, _DETAIL_NOT_FOUND)
    except DatabaseError as exc:
        if not is_lock_timeout(exc):
            raise
        logger.warning("Lock timeout editing ad %s (SQLSTATE 55P03)", ad.id)
        return _retryable_response()

    # Submit-time refusals first: the service carries ``submit_ad``'s outcome
    # verbatim, so each one maps to its own §2.5 problem (the same table
    # ``apps.ads.views.api.submit`` uses, spelled locally).
    submission = result.submission_outcome
    if submission is SubmitAdOutcome.CONSENT_REQUIRED:
        # The consent race (S4.2 drift): ``submit_ad`` re-read the account and
        # found consent withdrawn between this view's gate and that re-read.
        logger.warning("Ad %s edit refused: consent required at submit time", ad.id)
        return problem(
            HTTPStatus.FORBIDDEN, TYPE_CONSENT_REQUIRED, _DETAIL_CONSENT_REQUIRED
        )
    if submission is SubmitAdOutcome.INVALID_TRANSITION:
        logger.info("Ad %s edit refused by submit_ad: invalid transition", ad.id)
        return problem(
            HTTPStatus.CONFLICT, TYPE_INVALID_TRANSITION, _DETAIL_INVALID_TRANSITION
        )
    if submission is SubmitAdOutcome.DRAFT_GONE:
        logger.info("Ad %s edit refused by submit_ad: draft gone", ad.id)
        return problem(HTTPStatus.CONFLICT, TYPE_DRAFT_GONE, _DETAIL_DRAFT_GONE)
    if submission is SubmitAdOutcome.PHOTO_UNAVAILABLE:
        logger.info("Ad %s edit refused by submit_ad: photo unavailable", ad.id)
        return problem(
            HTTPStatus.CONFLICT, TYPE_PHOTO_UNAVAILABLE, _DETAIL_PHOTO_UNAVAILABLE
        )

    if result.outcome is EditOutcome.REFUSED:
        # No field was written: the status passed the affordance check but the
        # branch table has no write for it (ARCHIVED without ``reactivate``).
        logger.info("Ad %s edit refused by the service branch table", ad.id)
        return problem(
            HTTPStatus.CONFLICT, TYPE_INVALID_TRANSITION, _DETAIL_INVALID_TRANSITION
        )

    moderation_failed = submission is SubmitAdOutcome.MODERATION_FAILED
    if moderation_failed:
        # ``submit_ad`` committed the payload and parked the ad
        # (ON_MODERATION_FAILED); still a 200 (O-2a) — the verdict rides in the
        # state and in ``errors``.
        logger.info("Ad %s failed re-moderation after edit", ad.id)

    return JsonResponse(
        _serialize_edit_state(
            ad.id,
            result.outcome,
            moderation_failed,
            result.errors,
        )
    )


def _retryable_response() -> JsonResponse:
    """Return the 503 ``retryable`` problem with ``Retry-After``."""
    from apps.core.utils.problem import problem as _problem

    response = _problem(
        HTTPStatus.SERVICE_UNAVAILABLE,
        "retryable",
        _(
            "The server is busy processing another change. Please try again shortly."
        ),
    )
    response["Retry-After"] = "30"
    return response


def _serialize_edit_state(
    ad_id: int,
    outcome: EditOutcome,
    moderation_failed: bool,
    errors: tuple[str, ...],
) -> dict[str, Any]:
    """Serialize the post-edit ad state plus the outcome and moderation block.

    Re-reads the row so the payload reports exactly what the service committed
    (a price-only edit resets ``published_at``; a text edit leaves it untouched
    and moves the ad to ``ON_MODERATION``; a direct save keeps the status).
    """
    ad = Ad.objects.select_related("category", "city").get(id=ad_id)
    return {
        "id": ad.id,
        "outcome": outcome.value,
        "moderation_failed": moderation_failed,
        "errors": list(errors),
        "status": ad.status,
        "title": ad.get_title(),
        "description": ad.get_description(),
        "price": str(ad.price_amount) if ad.price_amount is not None else None,
        "currency": ad.price_currency,
        "city": _named(ad.city),
        "category": _named(ad.category),
        "published_at": _iso(ad.published_at),
        "archived_at": _iso(ad.archived_at),
        "moderation_failed_at": _iso(ad.moderation_failed_at),
        "updated_at": _iso(ad.updated_at),
    }


def _iso(value: Any) -> str | None:
    """Return an ISO-8601 string for an optional datetime."""
    return value.isoformat() if value else None


def _named(obj: Any) -> dict[str, Any] | None:
    """Return ``{"slug", "name"}`` for an optional related object, else ``None``."""
    if obj is None:
        return None
    return {"slug": obj.slug, "name": str(obj.name)}


__all__ = [
    "TYPE_CONSENT_REQUIRED",
    "TYPE_DRAFT_GONE",
    "TYPE_INVALID_TRANSITION",
    "TYPE_NOT_EDITABLE",
    "TYPE_NOT_FOUND",
    "TYPE_PHOTO_UNAVAILABLE",
    "AdEditBody",
    "edit_view",
]
