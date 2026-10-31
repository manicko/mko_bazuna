"""
JSON moderation-trust-dashboard read — ``GET /api/v1/trust/moderation/``.

The read-only JSON mirror of
:func:`apps.analytics.views.moderation_dashboard.moderation_analytics`: it
aggregates with the **same** service tier
(``get_moderation_stats`` + ``get_pending_queue_size`` +
``get_moderator_performance`` + ``get_rejection_reasons`` from
``apps/analytics/services/moderation_analytics.py``) over the **same** 30-day
window and answers with the structured fields the dashboard template renders —
the stats block, the pending-queue size, the per-moderator performance rows, the
rejection-reason distribution, and the window length — instead of a rendered page.

**Host:** the endpoint is hosted in ``apps/analytics`` (plan A3) but its URL keeps
the ``trust/`` prefix (plan S2.6: *"URLs keep the trust prefix… prefix orthogonal
to module host"*).

**Auth:** staff, mirroring the HTML mirror's ``@staff_required`` audience — but as
problem documents via ``staff_required_api_problem`` (the HTML decorator raises an
HTML 404): anonymous → 401 ``unauthenticated``, non-staff → 403 ``forbidden``,
wrong method → 405 ``method_not_allowed``; none carries a ``WWW-Authenticate``
challenge (09-API-010). Rate limiting mirrors the HTML dashboard, which has
**none**.
"""

import logging
from typing import Any

from django.http import HttpRequest, JsonResponse

from apps.analytics.services.moderation_analytics import (
    get_moderation_stats,
    get_moderator_performance,
    get_pending_queue_size,
    get_rejection_reasons,
)
from apps.core.utils.api_auth import staff_required_api_problem

logger = logging.getLogger(__name__)

# The HTML dashboard aggregates moderation events over a fixed 30-day window.
DAYS: int = 30


@staff_required_api_problem
def moderation_dashboard_view(request: HttpRequest) -> JsonResponse:
    """Return the moderation analytics block the staff dashboard renders.

    Mirrors the HTML ``moderation_analytics`` 1:1: ``get_moderation_stats``,
    ``get_pending_queue_size``, ``get_moderator_performance`` and
    ``get_rejection_reasons`` are called with the same ``days=30`` window, and the
    response keys (``stats`` / ``pending_queue_size`` / ``moderator_performance`` /
    ``rejection_reasons`` / ``days``) match the dashboard context.
    """
    days: int = DAYS
    stats = get_moderation_stats(days=days)
    queue_size: int = get_pending_queue_size()
    performance = get_moderator_performance(days=days)
    reasons = get_rejection_reasons(days=days)

    return JsonResponse(
        {
            "stats": dict(stats),
            "pending_queue_size": queue_size,
            "moderator_performance": [_as_dict(row) for row in performance],
            "rejection_reasons": dict(reasons),
            "days": days,
        }
    )


def _as_dict(row: Any) -> dict[str, Any]:
    """Return a plain ``dict`` for a ``TypedDict`` performance row.

    ``get_moderator_performance`` returns ``ModeratorPerformance`` ``TypedDict``
    instances, which are already plain dicts at runtime; the cast keeps the
    serializer explicit and type-stable for the JSON response.
    """
    return dict(row)
