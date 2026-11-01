"""
JSON submit-on-draft endpoint (S4.5) — ``POST /api/v1/ads/{id}/submit/``
(plan §2.4 row 5).

The JSON sibling of the bot's ``/post`` submit stage
(:func:`telegram_bot.handlers.ad_create.submit.process_preview`) and of the web
edit view's reactivation branch: it finalises an **existing** ``DRAFT`` through
the shared :func:`apps.ads.services.submission.submit_ad` service, so the
payload application, the ``DRAFT -> ON_MODERATION`` transition, the deferred
media promotion and ``auto_moderate`` (with its ``ModeratorActionLog`` /
``AnalyticsEvent`` side effects) cannot drift between the surfaces. No API-only
business predicate exists here.

**Dialog / photo staging stays bot-only (documented stance).** The plan row
caps this endpoint at "existing DRAFT; dialog/photo staging bot-only": the
multi-step dialog (title, description, price, photos...) is a Telegram FSM and
is not re-implemented over HTTP. Text, price, category, city and lookup fields
are taken from the stored DRAFT; the ``photos`` list is the DRAFT's existing
``AdImage`` rows converted to :class:`~apps.media.schemas.SubmittedPhoto` (their
bytes are already in permanent storage), so the identical ``submit_ad`` pipeline
(thumbnail capture, dedup, promotion plan) runs exactly as it does for the bot.

The O-14 pre-submission field check
-----------------------------------

The plan's error taxonomy has no field-inventory row, so this endpoint answers
the O-14 contract described in the S4.5 work item — *the DRAFT's readiness
inventory is returned as a structured payload so a machine can field-check
**before** the caller commits the submission* — by adding one optional body
flag:

- **``dry_run`` absent or ``false``** (the default) — the real submission
  through ``submit_ad``.
- **``dry_run: true``** — the inventory **only**. Nothing is written, no
  transition is attempted, no media is planned and moderation is never run: the
  response is the 200 (HTTP ``OK``) payload below.

Because a successful field check *is* a well-formed answer to the request, a
not-ready inventory is a 200, not a 4xx: no state change was requested (the
dry run asked for exactly this report) and the payload is the result. The
readiness failures that ``submit_ad`` would meet when the caller does commit
are still mapped to their taxonomy problems on the real submission
(``draft_gone`` / ``photo_unavailable`` / ``invalid_transition``, §2.5).

Readiness is computed from ``Ad.status`` and the stored field set, so the
inventory is a pure read:

- ``missing_fields`` — ``title`` (blank), ``description`` (blank),
  ``category`` (``category_id`` is null), ``city`` (``city_id`` is null),
  ``photos`` (no ``AdImage`` row). ``price`` is deliberately absent: ``0`` is
  a valid Free price (BR-03).
- ``over_media_sections.ad`` — ``{photo_count, min_photos, max_photos,
  has_over_media}``. The caps are the ones ``auto_moderate`` enforces
  (``ModerationCriteria.min_images`` / ``max_images``): the same numbers the
  reviewer's content check reads, so the inventory and the verdict agree.
- ``over_media_sections.section_cap_info`` — the moderation section those
  numbers belong to, so a later media limit in another section can be reported
  in the same shape without a payload change.
- ``ready`` — ``missing_fields`` empty **and** no over-media section.

Pipeline (fixed order, one branch per §2.5 taxonomy member):

1. **Identity** — ``login_required_api`` (401 ``unauthenticated``, no
   ``WWW-Authenticate``; identity before method).
2. **Method** — POST-only (405 ``method_not_allowed`` + ``Allow: POST``).
3. **Rate limit** — shared ``api_write`` / ``API_WRITE`` (429 ``rate_limited`` +
   ``Retry-After``), charged before the ad is resolved.
4. **Body** — :class:`SubmitBody` (``extra="forbid"``; the only accepted field
   is ``dry_run``). A malformed body is a 422 ``validation_failed`` problem.
5. **Resolution + ownership** — a missing ad and a **non-owned** ad answer the
   identical uniform 404 ``not_found`` problem (CWE-209).
6. **Consent** — the shared :func:`apps.users.services.account_state.can_create_ad`
   seam (auditor A14) **before** any transition → 403 ``consent_required``.
   ``submit_ad`` re-asserts the same predicate itself; its own
   ``CONSENT_REQUIRED`` outcome maps to the identical 403 (the consent race).
7. **Inventory** — a dry run answers here; a real submission continues only when
   ``ready`` and otherwise answers the 409 ``invalid_transition`` problem
   (nothing was written: the caller asked to commit an ad that cannot be
   submitted in its current state).
8. **Submit** — ``submit_ad`` on the DRAFT, mapped to the §2.5 outcome table.

Result → HTTP mapping (documented in ``docs/01-spec/api-surface.md``):

| Outcome / condition                     | HTTP                                          |
|---|---|
| ``dry_run`` (ready or not)              | 200 + inventory payload                       |
| ``PUBLISHED``                           | 200 ``{outcome: "published"}`` + post-submit state |
| ``MODERATION_FAILED``                   | 200 ``{outcome: "moderation_failed"}`` + parked state (``on_moderation_failed``), ``errors[]`` |
| ``INVALID_TRANSITION``                  | 409 ``invalid_transition``                    |
| ``DRAFT_GONE``                          | 409 ``draft_gone``                            |
| ``PHOTO_UNAVAILABLE``                   | 409 ``photo_unavailable``                     |
| ``CONSENT_REQUIRED``                    | 403 ``consent_required``                      |
| not-ready DRAFT, real submission        | 409 ``invalid_transition`` (+ inventory)      |
| lock timeout (SQLSTATE 55P03)           | 503 ``retryable`` + ``Retry-After``           |

A moderation failure is **not** an error: ``submit_ad`` committed the
submission and parked the ad as ``ON_MODERATION_FAILED`` (boundary rule O-2a),
so it is a 200 carrying the service's ``errors`` strings and the parked status.

Deliberate bot-vs-API differences (documented):

- **Content source.** The bot types the dialog into the FSM and submits the
  typed values; the API submits the values already stored on the DRAFT. Both
  funnel through the identical ``submit_ad`` call with the same field set.
- **Non-content failures.** The bot silently replaces the draft
  (``create_draft_ad``) and re-points its FSM; the API never creates ad rows
  (dialog staging is bot-only) and reports the taxonomy problem instead, leaving
  the DRAFT as it was.
- **Lock timeout.** The bot answers the busy message; the API answers the 503
  ``retryable`` problem with ``Retry-After``, like every other ``/api/v1/``
  write.

No CSRF exemption is applied: this write uses the middleware chain as-is.
"""

import logging
from decimal import Decimal
from http import HTTPStatus
from pathlib import Path
from typing import Any, Final

from django.conf import settings
from django.db import DatabaseError
from django.http import HttpRequest, JsonResponse
from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _
from pydantic import ValidationError, field_validator

from apps.ads.models import Ad
from apps.ads.services.submission import (
    SubmitAdInput,
    SubmitAdOutcome,
    SubmitAdResult,
    media_caps,
    submit_ad,
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
from apps.media.schemas import SubmittedPhoto
from apps.media.services.hash_service import FileHashService
from apps.search.services.rate_limit import rate_limit_check
from apps.users.services.account_state import can_create_ad

logger = logging.getLogger(__name__)

# Stable ASCII ``type`` tokens (never translated). The first three are the same
# tokens the edit / lifecycle endpoints emit; the remaining three are the §2.5
# state-machine family for submission.
TYPE_NOT_FOUND: Final[str] = "not_found"
TYPE_CONSENT_REQUIRED: Final[str] = "consent_required"
TYPE_INVALID_TRANSITION: Final[str] = "invalid_transition"
TYPE_DRAFT_GONE: Final[str] = "draft_gone"
TYPE_PHOTO_UNAVAILABLE: Final[str] = "photo_unavailable"
TYPE_RETRYABLE: Final[str] = "retryable"

# English msgids for the detail strings (cataloged in ``ru``/``bs``/``en`` in
# the stage i18n batch; ``gettext_lazy`` defers resolution to render time).
_DETAIL_NOT_FOUND: Final[str | Promise] = _("Ad not found.")
_DETAIL_METHOD_NOT_ALLOWED: Final[str | Promise] = _("Method not allowed.")
_DETAIL_CONSENT_REQUIRED: Final[str | Promise] = _(
    "To manage ads, please accept the personal data storage consent first."
)
_DETAIL_NOT_READY: Final[str | Promise] = _(
    "This ad cannot be submitted: the field check reports missing or over-cap "
    "content."
)
_DETAIL_DRAFT_GONE: Final[str | Promise] = _(
    "The draft no longer exists. Please start a new ad."
)
_DETAIL_PHOTO_UNAVAILABLE: Final[str | Promise] = _(
    "One of the photos is no longer available. Please upload it again."
)
_DETAIL_INVALID_TRANSITION: Final[str | Promise] = _(
    "This ad cannot be submitted in its current status."
)
_DETAIL_RETRYABLE: Final[str | Promise] = _(
    "The server is busy processing another change. Please try again shortly."
)

# Every authenticated ``/api/v1/`` write shares one key namespace (plan Q4).
_RATE_LIMIT_NAMESPACE: Final[str] = "api_write"

# The only allowed method for this write endpoint.
_ALLOWED_METHODS: Final[tuple[str, ...]] = ("POST",)

# Minimum lock_timeout (see DbLockTimeoutMiddleware); a client retry after this
# window cannot land inside the same contention.
_RETRY_AFTER_SECONDS: Final[str] = "30"

# The moderation section the media caps belong to (``auto_moderate``'s
# ``min_images`` / ``max_images`` pair).
MEDIA_SECTION: Final[str] = "media"

# Readiness keys, in report order.
FIELD_TITLE: Final[str] = "title"
FIELD_DESCRIPTION: Final[str] = "description"
FIELD_CATEGORY: Final[str] = "category"
FIELD_CITY: Final[str] = "city"
FIELD_PHOTOS: Final[str] = "photos"


class SubmitBody(BaseInputModel):
    """Client-input DTO for the (optional) submit body.

    The plan row names no body field — the submission takes everything from the
    stored DRAFT — so an **absent or empty** body is valid. The one accepted key
    is ``dry_run`` (the O-14 pre-submission field check); any other key is a 422
    ``validation_failed`` problem thanks to ``extra="forbid"``, so a caller
    cannot smuggle a title, a price or a target status into the submission.
    """

    dry_run: bool = False

    @field_validator("dry_run", mode="before")
    @classmethod
    def _coerce_dry_run(cls, v: Any) -> bool:
        """Accept ``None``/absent as ``False`` and the usual truthy spellings."""
        if v is None:
            return False
        if isinstance(v, str):
            return v.strip().lower() not in {"", "0", "false", "no", "off"}
        return bool(v)


@login_required_api
def submit_view(request: HttpRequest, ad_id: int) -> JsonResponse:
    """``POST /api/v1/ads/{id}/submit/`` — submit the caller's DRAFT (row 5)."""
    early = _preflight(request, ad_id)
    if isinstance(early, JsonResponse):
        return early
    body, ad = early

    if not can_create_ad(request.user):
        logger.warning(
            "User %s refused ad %s submission: storage consent required",
            request.user.id,
            ad_id,
        )
        return problem(
            HTTPStatus.FORBIDDEN, TYPE_CONSENT_REQUIRED, _DETAIL_CONSENT_REQUIRED
        )

    inventory = _field_check(ad)
    if body.dry_run:
        return JsonResponse(inventory)

    if not inventory["ready"]:
        # Nothing was written: the DRAFT cannot be submitted as stored. The
        # inventory rides along so the caller can fix exactly what is listed.
        logger.info("Ad %s submission refused by the field check", ad_id)
        response = problem(
            HTTPStatus.CONFLICT, TYPE_INVALID_TRANSITION, _DETAIL_NOT_READY
        )
        return _with_inventory(response, inventory)

    return _submit(ad, request.user.id)


def _build_input(ad: Ad, user_id: int) -> SubmitAdInput:
    """Build the shared :class:`SubmitAdInput` from the persisted DRAFT.

    Every value comes from the row, so the API submits exactly what the
    seller's dialog already stored — the bot's typed FSM values and this
    DTO are the same field set by construction. ``photos`` is the DRAFT's
    existing ``AdImage`` set (bytes already in permanent storage), which keeps
    the service's thumbnail/dedup/promotion pipeline running unchanged.

    ``price_currency`` is passed as the stored string; :class:`SubmitAdInput`
    coerces a ``StrEnum`` member at DTO construction, and the column is only
    ever written from ``CurrencyCode``, so re-coercing here would be redundant.

    **Photos are pre-digested so re-submitting a stored DRAFT is a no-op.**
    The bot always submits photos that were *just* uploaded to ``staging/``
    (its digest is captured from the staged bytes); a persisted DRAFT's photos
    are already permanent rows. Offering each row's own key with that row's
    stored digest makes ``AdImageService.create_or_skip`` find the existing
    row and return it, instead of inserting a second one at the same
    ``(ad, position)``. The digest is the row's persisted ``sha256`` (falling
    back to the file's digest when it was never stored) — reading the file
    instead would compare a live hash against an older stored one and create a
    duplicate. A missing file still surfaces as ``PHOTO_UNAVAILABLE`` from the
    staging plan / thumbnail read, so this changes no outcome, only whether the
    existing image set is recognised.
    """
    photos = [
        SubmittedPhoto(
            storage_key=image.image,
            telegram_file_id=image.telegram_file_id,
            position=image.position,
            thumbnail_small=image.thumbnail_small,
            thumbnail_medium=image.thumbnail_medium,
            thumbnail_large=image.thumbnail_large,
            sha256=image.sha256 or _disk_digest(image.image),
        )
        for image in ad.images.all().order_by("position")
    ]
    return SubmitAdInput(
        ad_id=ad.id,
        title_ru=ad.title,
        desc_ru=ad.description,
        title_bs=ad.title_bs or "",
        desc_bs=ad.description_bs or "",
        title_en=ad.title_en or "",
        desc_en=ad.description_en or "",
        original_language=ad.original_language,
        category_id=ad.category_id,
        city_id=ad.city_id,
        price_amount=ad.price_amount if ad.price_amount is not None else Decimal("0"),
        price_currency=ad.price_currency,
        photos=photos,
        user_id=user_id,
        listing_purpose_id=ad.listing_purpose_id,
        feature_ids=list(ad.features.values_list("id", flat=True)),
        listing_condition_id=ad.listing_condition_id,
    )


def _disk_digest(key: str) -> str | None:
    """Return the SHA-256 of a stored photo's bytes, or ``None`` when absent.

    Only a fallback for a row whose ``sha256`` was never persisted (rows created
    by tooling that bypassed ``AdImageService``); a missing file is not this
    helper's business — ``submit_ad`` reports that as ``PHOTO_UNAVAILABLE``.
    """
    path = Path(str(settings.MEDIA_ROOT)) / key
    if not path.exists():
        return None
    return FileHashService.calculate_sha256(str(path))


def _preflight(
    request: HttpRequest, ad_id: int
) -> JsonResponse | tuple[SubmitBody, Ad]:
    """Run method gate, rate limit, body validation and ownership, in order.

    Returns the refusal response when a stage refuses, or the validated body
    paired with the owned ad when the request may proceed.
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

    parsed = _parse_body(request)
    if isinstance(parsed, JsonResponse):
        return parsed

    ad = _owned_ad(ad_id, request.user.id)
    if ad is None:
        # Missing and non-owned ads answer the identical document (CWE-209).
        return problem(HTTPStatus.NOT_FOUND, TYPE_NOT_FOUND, _DETAIL_NOT_FOUND)

    return parsed, ad


def _parse_body(request: HttpRequest) -> SubmitBody | JsonResponse:
    """Validate the optional body; return the DTO or a 422 problem document.

    An empty body means "submit for real" (the plan row declares no field). A
    JSON object is validated strictly; any other content type carries no
    declared form field and is accepted as the empty body, exactly as the
    lifecycle endpoints treat a form post.
    """
    raw = request.body.strip()
    if not raw:
        return SubmitBody()
    content_type = (request.content_type or "").lower()
    if content_type != "application/json":
        return SubmitBody()
    try:
        return SubmitBody.model_validate_json(raw)
    except ValidationError as exc:
        logger.warning("Invalid ad submit request body: %s", exc)
        return validation_problem(exc)


def _owned_ad(ad_id: int, user_id: int) -> Ad | None:
    """Return the ad when it exists and belongs to *user_id*, else ``None``."""
    ad = (
        Ad.objects.select_related("category", "city")
        .prefetch_related("images")
        .filter(id=ad_id)
        .first()
    )
    if ad is None or ad.user_id != user_id:
        return None
    return ad


def _field_check(ad: Ad) -> dict[str, Any]:
    """Build the O-14 readiness inventory of *ad* without writing anything.

    Pure read: the stored field set, the image rows and the moderation media
    caps decide the report. The reported ``status`` lets the caller see a
    non-``DRAFT`` source; a real submission of such an ad is refused by the
    state machine and maps to ``invalid_transition``.
    """
    min_photos, max_photos = _media_caps()
    photo_count = ad.images.count()

    missing: list[str] = []
    if not (ad.title or "").strip():
        missing.append(FIELD_TITLE)
    if not (ad.description or "").strip():
        missing.append(FIELD_DESCRIPTION)
    if ad.category_id is None:
        missing.append(FIELD_CATEGORY)
    if ad.city_id is None:
        missing.append(FIELD_CITY)
    if photo_count == 0:
        missing.append(FIELD_PHOTOS)

    has_over_media = photo_count > max_photos

    return {
        "ad_id": ad.id,
        "status": ad.status,
        "ready": not missing and not has_over_media,
        "missing_fields": missing,
        "over_media_sections": {
            # Per-section verdicts, keyed by section name (``ad`` is the ad's
            # own media section).
            "ad": has_over_media,
            "has_over_media": has_over_media,
            # The counts those verdicts were computed from, so the caller can
            # report "N of M photos" without a second read.
            "section_cap_info": {
                "section": MEDIA_SECTION,
                "photo_count": photo_count,
                "min_photos": min_photos,
                "max_photos": max_photos,
            },
        },
    }


def _media_caps() -> tuple[int, int]:
    """Return the moderation media caps ``(min_images, max_images)``.

    Delegates to :func:`apps.ads.services.submission.media_caps`, the same
    numbers ``submit_ad``'s moderation pass enforces, so the inventory and the
    verdict can never disagree about the photo budget.
    """
    return media_caps()


def _with_inventory(
    response: JsonResponse, inventory: dict[str, Any]
) -> JsonResponse:
    """Attach the field-check inventory to a problem document.

    The body stays a well-formed RFC 9457 document (``type``/``title``/
    ``status``/``detail``) plus one extension member, so a client that only
    reads the standard members is unaffected while a field-checking client can
    act on the inventory.
    """
    import json

    body = json.loads(response.content)
    body["inventory"] = inventory
    payload = json.dumps(body).encode()
    response.content = payload
    response["Content-Length"] = str(len(payload))
    return response


def _submit(ad: Ad, user_id: int) -> JsonResponse:
    """Run ``submit_ad`` on the stored DRAFT and map its outcome.

    ``submit_ad`` opens its own ``transaction.atomic()`` and row lock, so the
    endpoint stays a thin adapter: it builds the DTO from the persisted DRAFT
    (:func:`_build_input`) and calls the very same service the bot's
    ``process_preview`` calls. The service re-reads the row under its own lock,
    which is why the inventory that gated this call is recomputed by it rather
    than trusted from the pre-flight read. A lock timeout keeps the 03-DB-004
    boundary; any other escaping exception rolls the service back (the ad stays
    DRAFT, the safe state) and is answered as the 503 ``retryable`` problem.
    """
    try:
        result = submit_ad(_build_input(ad, user_id))
    except DatabaseError as exc:
        if not is_lock_timeout(exc):
            raise
        logger.warning("Lock timeout submitting ad %s (SQLSTATE 55P03)", ad.id)
        return _retryable_response()
    except Exception:
        logger.exception("Submission failed for ad %s", ad.id)
        return _retryable_response()

    if result.outcome is SubmitAdOutcome.CONSENT_REQUIRED:
        return problem(
            HTTPStatus.FORBIDDEN, TYPE_CONSENT_REQUIRED, _DETAIL_CONSENT_REQUIRED
        )

    refusal = _refusal(result.outcome)
    if refusal is not None:
        return refusal

    return JsonResponse(_serialize_submit_state(ad.id, result))


def _refusal(outcome: SubmitAdOutcome) -> JsonResponse | None:
    """Map a non-success ``SubmitAdOutcome`` to its §2.5 problem, else ``None``."""
    table: dict[SubmitAdOutcome, tuple[int, str, str | Promise]] = {
        SubmitAdOutcome.INVALID_TRANSITION: (
            HTTPStatus.CONFLICT,
            TYPE_INVALID_TRANSITION,
            _DETAIL_INVALID_TRANSITION,
        ),
        SubmitAdOutcome.DRAFT_GONE: (
            HTTPStatus.CONFLICT,
            TYPE_DRAFT_GONE,
            _DETAIL_DRAFT_GONE,
        ),
        SubmitAdOutcome.PHOTO_UNAVAILABLE: (
            HTTPStatus.CONFLICT,
            TYPE_PHOTO_UNAVAILABLE,
            _DETAIL_PHOTO_UNAVAILABLE,
        ),
    }
    entry = table.get(outcome)
    if entry is None:
        return None
    status, type_token, detail = entry
    return problem(status, type_token, detail)


def _retryable_response() -> JsonResponse:
    """Return a 503 ``retryable`` problem with a ``Retry-After`` header."""
    response = problem(HTTPStatus.SERVICE_UNAVAILABLE, TYPE_RETRYABLE, _DETAIL_RETRYABLE)
    response["Retry-After"] = _RETRY_AFTER_SECONDS
    return response


def _serialize_submit_state(ad_id: int, result: SubmitAdResult) -> dict[str, Any]:
    """Serialize the post-submit ad state plus the outcome and moderation block.

    Re-reads the row so the payload reports exactly what ``submit_ad``
    committed (``published`` with ``published_at``, or the parked
    ``on_moderation_failed`` with its timestamp).
    """
    ad = Ad.objects.select_related("category", "city").get(id=ad_id)
    return {
        "id": ad.id,
        "outcome": result.outcome.value,
        "moderation_failed": result.outcome is SubmitAdOutcome.MODERATION_FAILED,
        "errors": [str(error) for error in result.errors],
        "status": ad.status,
        "title": ad.get_title(),
        "description": ad.get_description(),
        "price": str(ad.price_amount) if ad.price_amount is not None else None,
        "currency": ad.price_currency,
        "city": _named(ad.city),
        "category": _named(ad.category),
        "published_at": _iso(ad.published_at),
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
    "FIELD_CATEGORY",
    "FIELD_CITY",
    "FIELD_DESCRIPTION",
    "FIELD_PHOTOS",
    "FIELD_TITLE",
    "MEDIA_SECTION",
    "TYPE_CONSENT_REQUIRED",
    "TYPE_DRAFT_GONE",
    "TYPE_INVALID_TRANSITION",
    "TYPE_NOT_FOUND",
    "TYPE_PHOTO_UNAVAILABLE",
    "TYPE_RETRYABLE",
    "SubmitBody",
    "submit_view",
]
