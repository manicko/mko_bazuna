"""
Moderation review views for Mko Bazuna.

Views for admin-only moderation interface: review queue, approve, reject, ban, delete.
"""

import logging

from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.ads.models import Ad
from apps.core.enums import AdStatus
from apps.moderation.views.decorators import staff_required

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

    Delegates to approve_ad → auto_moderate, which validates the ad
    against ModerationCriteria. If the ad passes, it is published; if it
    fails, it is set to ON_MODERATION_FAILED. Redirects to the admin
    change page regardless (no 500 on auto-moderation failure).

    Args:
        request: HTTP request
        ad_id: The ad ID to approve

    Returns:
        Redirect to the admin ad change page.
    """
    from apps.moderation.admin_actions import approve_ad as do_approve

    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
        ad = get_object_or_404(
            Ad.objects.select_for_update(),
            id=ad_id,
            status=AdStatus.ON_MODERATION,
        )
        do_approve(ad, request.user.id)

        logger.info("Admin %s approved ad %s", request.user.id, ad_id)

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

    if request.method != "POST":
        return redirect(f"/admin/ads/ad/{ad_id}/change/")

    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
        ad = get_object_or_404(
            Ad.objects.select_for_update(),
            id=ad_id,
            status__in=[AdStatus.ON_MODERATION, AdStatus.ON_MODERATION_FAILED],
        )
        # Build reason from category + text
        reason_category = request.POST.get("reason_category", "") or ""
        reason_text = (request.POST.get("reason_text") or "").strip()

        # Combine for internal record
        reason = f"{reason_category}"
        if reason_text:
            reason = f"{reason_category}: {reason_text}"

        do_reject(ad, request.user.id, reason)

    logger.info("Admin %s rejected ad %s", request.user.id, ad_id)

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

    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
        ad = get_object_or_404(
            Ad.objects.select_for_update(),
            id=ad_id,
        )
        ban_user_for_ad(
            ad,
            request.user.id,
            request.POST.get("ban_reason", "No reason provided") or "No reason provided",
        )

    logger.info("Admin %s banned user via ad %s", request.user.id, ad_id)

    return redirect("/admin/ads/ad/?status__exact=on_moderation")
