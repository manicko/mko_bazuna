"""
JSON copy endpoint (S4.6) — ``POST /api/v1/ads/{id}/copy/`` (plan §2.4 row 10).

The JSON sibling of the bot's ``/copy <ad_id>`` command
(:func:`telegram_bot.handlers.ad_copy.cmd_copy`) and the first HTTP surface for
:func:`apps.ads.services.copy_service.copy_ad`. The service is called
**unchanged**: it is the only copy implementation (there is no HTML copy view),
so the endpoint owns no copy logic of its own — no new service was extracted
because none was inline in a view to begin with.

What a copy is (``copy_service.py``):

- a **new ``DRAFT``** owned by the caller, with the source's title /
  description in every language, ``original_language``, category, city,
  listing purpose, features and image rows (new rows, same storage keys — no
  file duplication);
- everything that belongs to the *source's* history is **reset** by not being
  copied: ``id``, ``status`` (``DRAFT``), the lifecycle timestamps
  (``published_at``, ``archived_at``, ``rejected_at``,
  ``moderation_failed_at``, ``deleted_at``), the price fields, the
  moderation/analytics history and the favorites;
- the **single-draft policy** applies exactly as in the bot flow: the caller's
  existing ``DRAFT`` (if any) is replaced by the copy inside the service's
  transaction, so the seller ends with exactly one in-progress draft.

Pipeline (fixed order, one branch per §2.5 taxonomy member):

1. **Identity** — ``login_required_api`` (401 ``unauthenticated``, no
   ``WWW-Authenticate``; identity before method).
2. **Method** — POST-only (405 ``method_not_allowed`` + ``Allow: POST``).
3. **Rate limit** — shared ``api_write`` / ``API_WRITE`` (429 ``rate_limited`` +
   ``Retry-After``), charged before the ad is resolved.
4. **Body** — :class:`CopyBody` declares **no** fields and ``extra="forbid"``
   rejects any key, so nothing a caller sends can influence the copy; an absent,
   empty or form-encoded body is accepted.
5. **Resolution + ownership** — a missing ad and a **non-owned** ad answer the
   identical uniform 404 ``not_found`` problem (CWE-209), the same answer the
   bot's ``/copy`` gives for "not yours" / "not found".
6. **Copy** — ``copy_ad``; a race between the ownership read and the service
   (the row was hard-deleted, or ownership changed) is mapped back onto the
   same uniform 404.
7. **Result** — 200 with the **new DRAFT's** state, including the source
   ``source_ad_id`` and the copied-field summary.

Result → HTTP mapping (documented in ``docs/01-spec/api-surface.md``):

| Condition                          | HTTP                                    |
|---|---|
| copy created                       | 200 + new DRAFT state (``id`` = new ad) |
| missing / non-owned / raced        | 404 ``not_found``                       |
| lock timeout (SQLSTATE 55P03)      | 503 ``retryable`` + ``Retry-After``     |

**Consent.** Row 10 names "max-ads + consent predicates as in the bot flow".
The bot's ``/copy`` applies **neither** at copy time: it asserts only a logged-in
``user_id`` and lets ``copy_ad`` create the draft; consent is enforced later,
when the draft is submitted (``submit_ad``'s create-time storage-consent gate,
06-PII-109), and ``max_ads_per_user`` is enforced by ``auto_moderate`` at that
same point. The endpoint therefore mirrors the bot exactly — **no consent or
max-ads gate here** — and a copy for a non-consented seller produces a DRAFT
that the submit endpoint will refuse with 403 ``consent_required``. Inventing a
stricter API-only gate would break the parity the plan requires.

A bare ``{ad_id}`` (the row's response sketch) is **superseded** by the same
200 post-action state shape every other ``/api/v1/ads/{id}/…`` write uses (S4.3
precedent): the new row's id is still there (``id``, plus ``source_ad_id``),
alongside the status and the copied-field summary, so a client never has to
re-read to learn what was created.

No CSRF exemption is applied: this write uses the middleware chain as-is.
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
from apps.ads.services.copy_service import copy_ad
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

logger = logging.getLogger(__name__)

# Stable ASCII ``type`` tokens (never translated); the same tokens the other
# ``/api/v1/ads/{id}/…`` writes emit.
TYPE_NOT_FOUND: Final[str] = "not_found"
TYPE_RETRYABLE: Final[str] = "retryable"

# English msgids for the detail strings (cataloged in ``ru``/``bs``/``en``;
# ``gettext_lazy`` defers resolution to render time).
_DETAIL_NOT_FOUND: Final[str | Promise] = _("Ad not found.")
_DETAIL_METHOD_NOT_ALLOWED: Final[str | Promise] = _("Method not allowed.")
_DETAIL_RETRYABLE: Final[str | Promise] = _(
    "The server is busy processing another change. Please try again shortly."
)

# Every authenticated ``/api/v1/`` write shares one key namespace (plan Q4).
_RATE_LIMIT_NAMESPACE: Final[str] = "api_write"

# The only allowed method for this write endpoint.
_ALLOWED_METHODS: Final[tuple[str, ...]] = ("POST",)

# Minimum lock_timeout (see DbLockTimeoutMiddleware).
_RETRY_AFTER_SECONDS: Final[str] = "30"

# The machine outcome token of a successful copy.
OUTCOME_COPIED: Final[str] = "copied"


class CopyBody(BaseInputModel):
    """Client-input DTO for the (optional) copy body.

    The plan row names no body field — a copy takes everything from the source
    ad — so an **absent or empty** body is valid. No field is declared, so
    ``extra="forbid"`` (from :class:`BaseInputModel`) rejects any key with a 422
    ``validation_failed`` problem: a caller cannot pass a title, a price or a
    target status and expect it to reach the copy.
    """


@login_required_api
def copy_view(request: HttpRequest, ad_id: int) -> JsonResponse:
    """``POST /api/v1/ads/{id}/copy/`` — copy the caller's own ad (row 10)."""
    if request.method not in _ALLOWED_METHODS:
        response = problem(
            HTTPStatus.METHOD_NOT_ALLOWED,
            TYPE_METHOD_NOT_ALLOWED,
            _DETAIL_METHOD_NOT_ALLOWED,
        )
        response["Allow"] = ", ".join(_ALLOWED_METHODS)
        return response

    # Rate limit before resolving the ad: the cost is charged even for a
    # request aimed at a missing id (api_bulk write ordering).
    if not rate_limit_check(
        request,
        namespace=_RATE_LIMIT_NAMESPACE,
        budget=RateLimitBudget.API_WRITE,
    ):
        return rate_limited_problem(RateLimitBudget.API_WRITE)

    body_refusal = _validate_optional_body(request)
    if body_refusal is not None:
        return body_refusal

    if not _owns_ad(ad_id, request.user.id):
        # Missing and non-owned ads answer the identical document (CWE-209).
        return problem(HTTPStatus.NOT_FOUND, TYPE_NOT_FOUND, _DETAIL_NOT_FOUND)

    return _copy(ad_id, request.user.id)


def _validate_optional_body(request: HttpRequest) -> JsonResponse | None:
    """Accept an absent / empty / non-JSON body; reject a malformed JSON object.

    Same switch as the lifecycle actions: Django's test client and a browser
    form post ``application/x-www-form-urlencoded`` (accepted, nothing read),
    while a JSON body is validated strictly against a DTO with no fields.
    """
    raw = request.body.strip()
    if not raw:
        return None
    if (request.content_type or "").lower() != "application/json":
        return None
    try:
        CopyBody.model_validate_json(raw)
    except ValidationError as exc:
        logger.warning("Invalid ad copy request body: %s", exc)
        return validation_problem(exc)
    return None


def _owns_ad(ad_id: int, user_id: int) -> bool:
    """Return ``True`` when *ad_id* exists and belongs to *user_id*.

    Only the two identifying columns are read: the copy service re-reads the
    source under its own transaction, so this pre-flight must not become a
    second source of truth.
    """
    return (
        Ad.objects.filter(id=ad_id, user_id=user_id).exists()
    )


def _copy(ad_id: int, user_id: int) -> JsonResponse:
    """Run ``copy_ad`` and serialize the new DRAFT; map its exceptions."""
    try:
        new_ad = copy_ad(ad_id, user_id)
    except Ad.DoesNotExist:
        # Raced with a hard delete between the ownership read and the service.
        return problem(HTTPStatus.NOT_FOUND, TYPE_NOT_FOUND, _DETAIL_NOT_FOUND)
    except PermissionError:
        # Ownership changed in the same race: the same uniform 404, never a 403
        # distinguishable from "does not exist" (CWE-209).
        return problem(HTTPStatus.NOT_FOUND, TYPE_NOT_FOUND, _DETAIL_NOT_FOUND)
    except DatabaseError as exc:
        if not is_lock_timeout(exc):
            raise
        logger.warning("Lock timeout copying ad %s (SQLSTATE 55P03)", ad_id)
        return _retryable_response()

    return JsonResponse(_serialize_copy_state(ad_id, new_ad.id))


def _retryable_response() -> JsonResponse:
    """Return a 503 ``retryable`` problem with a ``Retry-After`` header."""
    response = problem(HTTPStatus.SERVICE_UNAVAILABLE, TYPE_RETRYABLE, _DETAIL_RETRYABLE)
    response["Retry-After"] = _RETRY_AFTER_SECONDS
    return response


def _serialize_copy_state(source_ad_id: int, new_ad_id: int) -> dict[str, Any]:
    """Serialize the NEW DRAFT plus the copied-field summary.

    Re-reads the new row so the payload reports exactly what the service
    committed. ``copied`` lists the field *groups* a copy preserves, which is
    also the contract a client can rely on; ``reset`` lists what a copy
    deliberately does not carry over from the source's history.
    """
    ad = Ad.objects.select_related("category", "city").get(id=new_ad_id)
    return {
        "id": ad.id,
        "source_ad_id": source_ad_id,
        "outcome": OUTCOME_COPIED,
        "status": ad.status,
        "title": ad.get_title(),
        "description": ad.get_description(),
        "price": str(ad.price_amount) if ad.price_amount is not None else None,
        "currency": ad.price_currency,
        "city": _named(ad.city),
        "category": _named(ad.category),
        "photo_count": ad.images.count(),
        "feature_count": ad.features.count(),
        "copied": [
            "title",
            "description",
            "languages",
            "category",
            "city",
            "listing_purpose",
            "features",
            "photos",
        ],
        "reset": [
            "id",
            "status",
            "price",
            "published_at",
            "archived_at",
            "rejected_at",
            "moderation_failed_at",
            "deleted_at",
        ],
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
    "OUTCOME_COPIED",
    "TYPE_NOT_FOUND",
    "TYPE_RETRYABLE",
    "CopyBody",
    "copy_view",
]
