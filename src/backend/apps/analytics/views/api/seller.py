"""
JSON seller-trust-dashboard read — ``GET /api/v1/trust/seller/``.

The read-only JSON mirror of
:func:`apps.analytics.views.seller_dashboard.seller_trust_dashboard`: it computes
the seller's trust score with the **same** service tier
(``calculate_seller_trust_score`` + ``get_trust_level`` +
``get_seller_daily_metrics`` from ``apps/analytics/services/trust_analytics.py``)
over the **same** 30-day window and answers with the structured fields the
dashboard template renders — the rounded score, the trust level, the daily
metrics rows, and the aggregated view/contact totals — instead of a rendered page.

**Host:** the endpoint is hosted in ``apps/analytics`` (plan A3) but its URL keeps
the ``trust/`` prefix (plan S2.6: *"URLs keep the trust prefix… prefix orthogonal
to module host"*).

**Auth:** session (SESS), mirroring the HTML mirror's ``@login_required`` — an
anonymous request is refused by ``login_required_api`` with a 401
``unauthenticated`` problem and **no** ``WWW-Authenticate`` header (09-API-010).
Rate limiting mirrors the HTML dashboard, which has **none**.
"""

import logging
from http import HTTPStatus
from typing import Any

from django.http import HttpRequest, JsonResponse

from apps.analytics.services.trust_analytics import (
    calculate_seller_trust_score,
    get_seller_daily_metrics,
    get_trust_level,
)
from apps.core.utils.api_auth import TYPE_METHOD_NOT_ALLOWED, login_required_api
from apps.core.utils.problem import problem

logger = logging.getLogger(__name__)

# The HTML dashboard aggregates the seller's daily metrics over a fixed 30-day
# window (``get_seller_daily_metrics(request.user.id, days=30)``).
DAYS: int = 30


@login_required_api
def seller_dashboard_view(request: HttpRequest) -> JsonResponse:
    """Return the seller's trust score, level, daily metrics and totals.

    Mirrors the HTML ``seller_trust_dashboard`` 1:1: the score comes from
    ``calculate_seller_trust_score``, the level from ``get_trust_level``, the
    daily rows from ``get_seller_daily_metrics(..., days=30)``, and the totals are
    the same sums of the daily rows the view computes (``total_views`` /
    ``total_contacts``). The score is rounded to one decimal exactly as the view
    does.

    The GET-only method gate is inline: ``login_required_api`` (outermost) runs the
    identity check first, so an anonymous POST is a 401, not a 405; an
    authenticated non-GET request is refused with a 405 ``method_not_allowed``
    problem document carrying ``Allow: GET`` (plan §2.5 taxonomy).
    """
    if request.method != "GET":
        response = problem(
            HTTPStatus.METHOD_NOT_ALLOWED,
            TYPE_METHOD_NOT_ALLOWED,
            "Method not allowed.",
        )
        response["Allow"] = "GET"
        return response

    score: float = calculate_seller_trust_score(request.user.id)
    level = get_trust_level(score)
    daily_metrics = get_seller_daily_metrics(request.user.id, days=DAYS)

    total_views = sum(int(m.views_count or 0) for m in daily_metrics)
    total_contacts = sum(int(m.contacts_count or 0) for m in daily_metrics)

    return JsonResponse(
        {
            "trust_score": round(score, 1),
            "trust_level": level.value,
            "daily_metrics": [_serialize_daily_metric(m) for m in daily_metrics],
            "total_views": total_views,
            "total_contacts": total_contacts,
        }
    )


def _serialize_daily_metric(metric: Any) -> dict[str, Any]:
    """Serialize one ``DailyAdMetrics`` row into the dashboard row shape.

    Keys map the fields the seller-dashboard template renders for each daily
    row: the date, the owning ad, the view/contact counts and the optional
    trust/response-time values.
    """
    return {
        "date": metric.date.isoformat(),
        "ad_id": metric.ad_id,
        "views_count": metric.views_count,
        "contacts_count": metric.contacts_count,
        "trust_score": metric.trust_score,
        "avg_response_time": metric.avg_response_time,
    }
