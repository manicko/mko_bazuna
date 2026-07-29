"""
Seller trust dashboard view for Mko Bazuna.

Displays trust score, trust level badge, and daily aggregated metrics
for the authenticated seller. Requires login (not staff-only — sellers
view their own trust information).
"""

from __future__ import annotations

import logging

from apps.analytics.services.trust_analytics import (
    calculate_seller_trust_score,
    get_seller_daily_metrics,
    get_trust_level,
)
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

logger = logging.getLogger(__name__)


@login_required
def seller_trust_dashboard(request: HttpRequest) -> HttpResponse:
    """Trust-focused dashboard for sellers showing metrics and trust level.

    Computes the seller's trust score, resolves the corresponding
    TrustLevel badge, and fetches daily aggregated metrics for the
    seller's ads over the last 30 days.

    Args:
        request: HTTP request (authenticated user required).

    Returns:
        Rendered seller dashboard template with trust context.
    """
    score: float = calculate_seller_trust_score(request.user.id)
    level = get_trust_level(score)
    daily_metrics = get_seller_daily_metrics(request.user.id, days=30)

    # Aggregate daily metrics totals
    total_views = sum(int(m.views_count or 0) for m in daily_metrics)
    total_contacts = sum(int(m.contacts_count or 0) for m in daily_metrics)

    context: dict = {
        "trust_score": round(score, 1),
        "trust_level": level,
        "daily_metrics": daily_metrics,
        "total_views": total_views,
        "total_contacts": total_contacts,
    }

    return render(request, "analytics/seller_dashboard.html", context)