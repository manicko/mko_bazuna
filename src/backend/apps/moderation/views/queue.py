"""
Moderation queue view — priority-based ad listing for moderators.

Displays the moderation queue with priority level filtering and
counts per priority level.
"""

import logging

from apps.moderation.services.priority import PriorityService
from apps.moderation.views.decorators import staff_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

logger = logging.getLogger(__name__)


@staff_required
def moderation_queue(request: HttpRequest) -> HttpResponse:
    """Display moderation queue with priority filtering.

    Supports ?priority=high|medium|low|all query parameter.
    Shows count of ads in each priority bucket.
    """
    priority = request.GET.get("priority", "all")
    service = PriorityService()

    ads = service.get_queued_ads(
        priority_filter=None if priority == "all" else priority,
    )

    all_counts = service.get_priority_counts()

    return render(request, "admin/moderation/queue.html", {
        "ads": ads,
        "selected_priority": priority,
        "priority_counts": all_counts,
    })