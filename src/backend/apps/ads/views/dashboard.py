"""
Seller dashboard views for Mko Bazuna.

Lists seller's ads grouped by status for management actions.
Requires authentication via Telegram login.
"""

import logging

from apps.ads.models import Ad
from apps.core.enums import AdStatus
from apps.core.enums import TimeRange
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from apps.analytics.services.seller_stats import SellerStats

logger = logging.getLogger(__name__)


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    """
    Seller dashboard listing ads grouped by status.

    Groups ads into:
        - PUBLISHED: Live ads visible to buyers
        - ON_MODERATION: Pending review
        - ON_MODERATION_FAILED: Failed auto-check
        - ARCHIVED: Auto-archived or manually archived
        - REJECTED: Manually rejected by moderator

    Args:
        request: HTTP request (authenticated user required)

    Returns:
        Rendered dashboard template with grouped ads
    """
    # Parse time range filter from request
    selected_range_value = request.GET.get("time_range", TimeRange.ALL_TIME.value)
    try:
        time_range = TimeRange(selected_range_value)
    except ValueError:
        time_range = TimeRange.ALL_TIME

    # Compute seller stats
    seller_stats = SellerStats(request.user.id).get_stats(time_range)

    # Build per-ad lookup dict for efficient template rendering
    per_ad_stats_dict: dict[int, dict] = {}
    for row in seller_stats.get("per_ad_stats", []):
        ad_id = row.get("ad_id")
        if ad_id is not None:
            per_ad_stats_dict[ad_id] = row

    # Fetch all ads for the current user, grouped by status
    ads_by_status = {
        AdStatus.PUBLISHED: Ad.objects.filter(
            user_id=request.user.id, status=AdStatus.PUBLISHED
        ).prefetch_related("images").select_related("category", "city"),
        AdStatus.ON_MODERATION: Ad.objects.filter(
            user_id=request.user.id, status=AdStatus.ON_MODERATION
        ).select_related("category", "city"),
        AdStatus.ON_MODERATION_FAILED: Ad.objects.filter(
            user_id=request.user.id, status=AdStatus.ON_MODERATION_FAILED
        ).select_related("category", "city"),
        AdStatus.ARCHIVED: Ad.objects.filter(
            user_id=request.user.id, status=AdStatus.ARCHIVED
        ).prefetch_related("images").select_related("category", "city"),
        AdStatus.REJECTED: Ad.objects.filter(
            user_id=request.user.id, status=AdStatus.REJECTED
        ).select_related("category", "city"),
    }

    context = {
        "ads_by_status": ads_by_status,
        "status_labels": {
            AdStatus.PUBLISHED: _("Published"),
            AdStatus.ON_MODERATION: _("On Moderation"),
            AdStatus.ON_MODERATION_FAILED: _("Failed Moderation"),
            AdStatus.ARCHIVED: _("Archived"),
            AdStatus.REJECTED: _("Rejected"),
        },
        "seller_stats": seller_stats,
        "per_ad_stats_dict": per_ad_stats_dict,
        "selected_time_range": time_range.value,
        "time_range_options": TimeRange.choices(),
    }

    return render(request, "ads/dashboard.html", context)
