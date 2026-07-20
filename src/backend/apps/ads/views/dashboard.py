"""
Seller dashboard views for Mko Bazuna.

Lists seller's ads grouped by status for management actions.
Requires authentication via Telegram login.
"""

import logging

from apps.ads.models import Ad
from apps.core.enums import AdStatus
from apps.users.views.consent import is_consent_given
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

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
            AdStatus.PUBLISHED: "Published",
            AdStatus.ON_MODERATION: "On Moderation",
            AdStatus.ON_MODERATION_FAILED: "Failed Moderation",
            AdStatus.ARCHIVED: "Archived",
            AdStatus.REJECTED: "Rejected",
        },
        "consent_shown": is_consent_given(request),
    }

    return render(request, "ads/dashboard.html", context)