"""
Bulk moderation actions API endpoint.

Provides JSON API for approving, rejecting, or flagging multiple ads at once.
"""

import json
import logging

from apps.ads.models import Ad
from apps.moderation.admin_actions import approve_ad, reject_ad
from apps.moderation.services.priority import PriorityService
from apps.moderation.views.decorators import staff_required_api
from django.http import HttpRequest, JsonResponse

logger = logging.getLogger(__name__)


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
    data = json.loads(request.body)
    action = data.get("action", "")
    ad_ids: list[int] = data.get("selected_items", [])
    reason: str = data.get("reason", "")

    results: dict[str, object] = {"completed": 0, "errors": []}

    for ad_id in ad_ids:
        try:
            ad = Ad.objects.get(id=ad_id)
            if action == "approve":
                approve_ad(ad, request.user.id)
            elif action == "reject":
                reject_ad(ad, request.user.id, reason)
            elif action == "flag":
                PriorityService().calculate_and_save(ad)
            else:
                raise ValueError(f"Unknown action: {action}")

            results["completed"] += 1  # type: ignore[operator]
        except Exception as e:
            errors = results.get("errors", [])
            errors.append({"id": ad_id, "error": str(e)})
            results["errors"] = errors  # type: ignore[assignment]

    return JsonResponse(results)