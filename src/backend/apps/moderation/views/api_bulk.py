"""
Bulk moderation actions API endpoint.

Provides JSON API for approving, rejecting, or flagging multiple ads at once.
"""

import logging
from typing import Final

from django.db import transaction
from django.http import HttpRequest, JsonResponse
from pydantic import ValidationError

from apps.ads.models import Ad
from apps.core.enums import (
    ApproveOutcome,
    BulkModerationAction,
    BulkModerationError,
)
from apps.core.utils.sanitize import pydantic_errors_json
from apps.moderation.admin_actions import approve_ad, reject_ad
from apps.moderation.schemas import BulkModerationRequest
from apps.moderation.services.exceptions import MaxAdsExceeded
from apps.moderation.services.priority import PriorityService
from apps.moderation.views.decorators import staff_required_api

logger = logging.getLogger(__name__)

MAX_BULK_ACTIONS: Final[int] = 100


def _append_error(
    results: dict[str, object],
    ad_id: int,
    error: BulkModerationError,
) -> None:
    """Append one per-id error entry, preserving the response shape.

    The error string is always one of ``BulkModerationError``'s stable values;
    no exception text ever reaches the client.
    """
    errors = results.get("errors", [])
    errors.append({"id": ad_id, "error": error.value})
    results["errors"] = errors


@staff_required_api
def bulk_moderation_action(request: HttpRequest) -> JsonResponse:
    """Handle bulk moderation actions (approve, reject, flag) via JSON POST.

    Request body:
        {
            "action": "approve" | "reject" | "flag",
            "selected_items": [1, 2, 3, ...],
            "reason": "Optional reason for rejection"
        }

    Response:
        {
            "completed": 3,
            "errors": [{"id": 5, "error": "..."}]
        }

    Each ad is processed in its own ``transaction.atomic()`` with
    ``select_for_update()`` on that one row, ids are visited in ascending
    primary-key order (deterministic lock order, matching ``bulk_approve``), and
    a failure on one ad never rolls back or aborts the rest — that per-ad
    isolation is what the response shape already promises. ``completed`` counts
    only ads that were actually acted upon. Duplicate ids are deduplicated
    before processing, so each ad is counted once; ``MAX_BULK_ACTIONS`` bounds
    the unique-id count.
    """
    try:
        payload = BulkModerationRequest.model_validate_json(request.body)
    except ValidationError as exc:
        logger.warning("Invalid bulk moderation request body: %s", exc)
        return JsonResponse(
            {"error": "Invalid request body", "errors": pydantic_errors_json(exc)},
            status=422,
        )

    action_enum = payload.action
    # Deduplicate: a repeated id is a client artifact, and processing it twice
    # would re-lock, re-transition and double-count one ad. The cap applies to
    # the deduplicated list because it bounds the actual per-row cost, not the
    # raw payload length.
    ad_ids: list[int] = sorted(set(payload.selected_items))
    reason: str = payload.reason

    if len(ad_ids) > MAX_BULK_ACTIONS:
        logger.warning(
            "Bulk moderation rejected: %d unique items exceeds max %d",
            len(ad_ids),
            MAX_BULK_ACTIONS,
        )
        return JsonResponse(
            {"error": f"selected_items exceeds maximum of {MAX_BULK_ACTIONS}"},
            status=400,
        )

    results: dict[str, object] = {"completed": 0, "errors": []}

    # Ascending pk order makes the per-row lock acquisition order deterministic,
    # matching bulk_approve's documented rationale (no deadlock between
    # concurrent bulk writers locking overlapping rows). The list is already
    # deduplicated and sorted, so each ad is processed and counted exactly once.
    for ad_id in ad_ids:
        try:
            with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
                # Lock this single row for the duration of the per-ad work. The
                # batch is deliberately NOT all-or-nothing; each iteration
                # commits or rolls back on its own.
                ad = Ad.objects.select_for_update().get(id=ad_id)
                if action_enum is BulkModerationAction.APPROVE:
                    outcome = approve_ad(ad, request.user.id)
                    if outcome is ApproveOutcome.CRITERIA_REJECTED:
                        _append_error(
                            results,
                            ad_id,
                            BulkModerationError.CRITERIA_REJECTED,
                        )
                        continue
                    if outcome is ApproveOutcome.TRANSITION_REFUSED:
                        _append_error(
                            results,
                            ad_id,
                            BulkModerationError.TRANSITION_REFUSED,
                        )
                        continue
                elif action_enum is BulkModerationAction.REJECT:
                    reject_ad(ad, request.user.id, reason)
                elif action_enum is BulkModerationAction.FLAG:
                    # calculate_and_save now runs inside this per-ad
                    # transaction (it previously ran outside any transaction).
                    PriorityService().calculate_and_save(ad)

            results["completed"] += 1  # type: ignore[operator]
        except Ad.DoesNotExist:
            # The row was absent at lock time or hard-deleted mid-transaction.
            logger.warning(
                "Bulk moderation: ad %s no longer exists", ad_id
            )
            _append_error(results, ad_id, BulkModerationError.AD_NOT_FOUND)
        except MaxAdsExceeded as exc:
            # A business outcome, not a system fault: the user reached the
            # active-ads cap. Log at WARNING with the structured fields.
            logger.warning(
                "Bulk moderation: ad %s skipped, user %s reached max %s "
                "active ads (current_count=%s)",
                ad_id,
                exc.user_id,
                exc.limit,
                exc.current_count,
            )
            _append_error(results, ad_id, BulkModerationError.MAX_ADS_EXCEEDED)
        except ValueError:
            # The state machine refused the transition: ordinary user input
            # (e.g. bulk-rejecting an ARCHIVED ad). Log at WARNING, never
            # ERROR, and report a specific outcome — never the exception text
            # (same information-disclosure discipline as AD-012).
            logger.warning(
                "Bulk moderation: ad %s refused by the state machine", ad_id
            )
            _append_error(
                results, ad_id, BulkModerationError.INVALID_TRANSITION
            )
        except Exception:
            # A genuinely unexpected (infra/DB) failure. Keep the generic,
            # non-leaking string, but log loudly so an infra failure is never a
            # silent 200.
            logger.exception("Bulk moderation failed for ad %s", ad_id)
            _append_error(
                results, ad_id, BulkModerationError.PROCESSING_FAILED
            )

    return JsonResponse(results)
