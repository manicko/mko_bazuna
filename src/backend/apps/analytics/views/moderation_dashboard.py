"""
Moderation analytics dashboard view for Mko Bazuna.

Staff-only view that displays aggregated moderation statistics including
approve/reject/flag counts, pending queue size, moderator performance
metrics, and rejection reason distribution.
"""

from __future__ import annotations

import logging

from apps.analytics.services.moderation_analytics import (
    ModerationStats,
    get_moderation_stats,
    get_moderator_performance,
    get_pending_queue_size,
    get_rejection_reasons,
)
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render

logger = logging.getLogger(__name__)


def _staff_required(view_func):
    """Decorator to require staff or superuser access."""

    def wrapper(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if not (request.user.is_staff or request.user.is_superuser):
            raise Http404("Not found")
        return view_func(request, *args, **kwargs)

    return wrapper


@_staff_required
def moderation_analytics(request: HttpRequest) -> HttpResponse:
    """Staff dashboard showing moderation analytics and statistics.

    Aggregates moderation events over the last 30 days and displays
    approval/rejection/flagging rates, pending queue, moderator
    performance, and rejection reason breakdowns.

    Args:
        request: HTTP request (staff user required).

    Returns:
        Rendered moderation analytics template with stats context.
    """
    days: int = 30
    stats: ModerationStats = get_moderation_stats(days=days)
    queue_size: int = get_pending_queue_size()
    performance = get_moderator_performance(days=days)
    reasons: dict[str, int] = get_rejection_reasons(days=days)

    context: dict = {
        "stats": stats,
        "pending_queue_size": queue_size,
        "moderator_performance": performance,
        "rejection_reasons": reasons,
        "days": days,
    }

    return render(request, "analytics/moderation_dashboard.html", context)