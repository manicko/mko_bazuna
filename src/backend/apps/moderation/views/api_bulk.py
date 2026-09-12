"""
Bulk moderation actions API endpoint.

Provides JSON API for approving, rejecting, or flagging multiple ads at once.
"""

import logging
from typing import Final

from django.http import HttpRequest, JsonResponse
from pydantic import ValidationError

from apps.ads.models import Ad
from apps.core.enums import BulkModerationAction
from apps.moderation.admin_actions import approve_ad, reject_ad
from apps.moderation.schemas import BulkModerationRequest
from apps.moderation.services.priority import PriorityService
from apps.moderation.views.decorators import staff_required_api

logger = logging.getLogger(__name__)

MAX_BULK_ACTIONS: Final[int] = 100


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
    """
    try:
        payload = BulkModerationRequest.model_validate_json(request.body)
    except ValidationError:
        logger.warning("Invalid bulk moderation request body")
        return JsonResponse({"error": "Invalid request body"}, status=400)

    action_enum = payload.action
    ad_ids: list[int] = payload.selected_items
    reason: str = payload.reason

    if len(ad_ids) > MAX_BULK_ACTIONS:
        logger.warning(
            "Bulk moderation rejected: %d items exceeds max %d",
            len(ad_ids),
            MAX_BULK_ACTIONS,
        )
        return JsonResponse(
            {"error": f"selected_items exceeds maximum of {MAX_BULK_ACTIONS}"},
            status=400,
        )

    results: dict[str, object] = {"completed": 0, "errors": []}

    for ad_id in ad_ids:
        try:
            ad = Ad.objects.get(id=ad_id)
            if action_enum is BulkModerationAction.APPROVE:
                approve_ad(ad, request.user.id)
            elif action_enum is BulkModerationAction.REJECT:
                reject_ad(ad, request.user.id, reason)
            elif action_enum is BulkModerationAction.FLAG:
                PriorityService().calculate_and_save(ad)

            results["completed"] += 1  # type: ignore[operator]
        except Exception as e:
            logger.error("Bulk moderation failed for ad %s: %s", ad_id, e)
            errors = results.get("errors", [])
            errors.append({"id": ad_id, "error": "Processing failed"})
            results["errors"] = errors

    return JsonResponse(results)
