"""
Moderation review views for Mko Bazuna.

Views for admin-only moderation interface: review queue, approve, reject, ban, delete.
"""

import logging

from apps.ads.models import Ad
from apps.core.enums import AdStatus
from apps.moderation.services.exceptions import MaxAdsExceeded
from apps.moderation.views.decorators import staff_required
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)


@staff_required
def moderation_review(request: HttpRequest, ad_id: int) -> HttpResponse:
    """
    Detail view for reviewing an ad in moderation queue.

    Shows ad details with photo grid, metadata, and moderation action buttons.
    Accessible only to staff/superuser.

    Args:
        request: HTTP request
        ad_id: The ad ID to review

    Returns:
        Rendered review template or 404
    """
    ad = get_object_or_404(
        Ad.objects.select_related("user", "category", "city").prefetch_related(
            "images"
        ),
        id=ad_id,
        status__in=[AdStatus.ON_MODERATION, AdStatus.ON_MODERATION_FAILED],
    )

    context = {
        "ad": ad,
    }

    return render(request, "admin/moderation/review.html", context)


@require_POST
@staff_required
def approve_ad(request: HttpRequest, ad_id: int) -> HttpResponse:
    """
    Approve an ad for publication (POST only).

    If the ad owner has reached ``max_ads_per_user``, the ad stays in
    ``ON_MODERATION`` and the user is redirected back to the review page
    with an error message (no 500).

    Args:
        request: HTTP request
        ad_id: The ad ID to approve

    Returns:
        Redirect to admin ad change page on success, or back to the
        review page with an error message when the user's active-ads
        cap is exceeded.
    """
    from apps.moderation.admin_actions import approve_ad as do_approve

    ad = get_object_or_404(Ad, id=ad_id, status=AdStatus.ON_MODERATION)
    try:
        do_approve(ad, request.user.id)
    except MaxAdsExceeded as exc:
        logger.warning(
            "Approve skipped for ad %s: user %s reached max %s active "
            "ads (current_count=%s)",
            ad_id,
            exc.user_id,
            exc.limit,
            exc.current_count,
        )
        messages.error(
            request,
            _(
                "Cannot approve: the ad owner has reached the maximum number of active ads."
            ),
        )
        return redirect(reverse("moderation:review", kwargs={"ad_id": ad_id}))

    logger.info(f"Admin {request.user.id} approved ad {ad_id}")

    return redirect(f"/admin/ads/ad/{ad_id}/change/")


@staff_required
def reject_ad(request: HttpRequest, ad_id: int) -> HttpResponse:
    """
    Reject an ad with reason (POST only).

    Args:
        request: HTTP request with reason_category and reason_text
        ad_id: The ad ID to reject

    Returns:
        Redirect to admin ad list
    """
    from apps.moderation.admin_actions import reject_ad as do_reject

    ad = get_object_or_404(
        Ad,
        id=ad_id,
        status__in=[AdStatus.ON_MODERATION, AdStatus.ON_MODERATION_FAILED],
    )

    if request.method != "POST":
        return redirect(f"/admin/ads/ad/{ad_id}/change/")

    # Build reason from category + text
    reason_category = request.POST.get("reason_category", "") or ""
    reason_text = (request.POST.get("reason_text") or "").strip()

    # Combine for internal record
    reason = f"{reason_category}"
    if reason_text:
        reason = f"{reason_category}: {reason_text}"

    do_reject(ad, request.user.id, reason)
    logger.info(f"Admin {request.user.id} rejected ad {ad_id}")

    return redirect("/admin/ads/ad/?status__exact=on_moderation")


@staff_required
def ban_user(request: HttpRequest, ad_id: int) -> HttpResponse:
    """
    Ban user who posted the ad (POST only).

    Args:
        request: HTTP request with ban_reason
        ad_id: The ad ID (used to identify user)

    Returns:
        Redirect to admin ad list
    """
    from apps.moderation.admin_actions import ban_user_for_ad

    if request.method != "POST":
        return redirect(f"/admin/ads/ad/{ad_id}/change/")

    ad = get_object_or_404(Ad, id=ad_id)
    ban_user_for_ad(
        ad,
        request.user.id,
        request.POST.get("ban_reason", "No reason provided") or "No reason provided",
    )
    logger.info(f"Admin {request.user.id} banned user via ad {ad_id}")

    return redirect("/admin/ads/ad/?status__exact=on_moderation")
