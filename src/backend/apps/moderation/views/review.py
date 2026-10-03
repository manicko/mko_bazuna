"""
Moderation review views for Mko Bazuna.

Views for admin-only moderation interface: review queue, approve, reject, ban, delete.
"""

import logging

from django.contrib import messages
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.ads.models import Ad
from apps.core.enums import AdStatus, ApproveOutcome
from apps.moderation.admin_actions import BanRefusalReason, ban_refusal_reason
from apps.moderation.views.decorators import staff_required

logger = logging.getLogger(__name__)

# Fixed, stable moderator-facing sentences. The refusal text names the real
# rule and is never the caught exception's string (the escaping ValueError from
# auto_moderate's double-failure path is misleading).
_APPROVE_OUTCOME_MESSAGES: dict[ApproveOutcome, str] = {
    ApproveOutcome.CRITERIA_REJECTED: (
        "The ad did not pass auto-moderation and was not published."
    ),
    ApproveOutcome.TRANSITION_REFUSED: (
        "The ad could not be published: the ad's current status does not "
        "allow a transition to published."
    ),
}

# Fixed, stable moderator-facing sentences for a refused ban. Like
# ``_APPROVE_OUTCOME_MESSAGES`` these are English-only Python literals on a
# staff-only surface (no ``.po`` entry, no template change). Each names the real
# reason the target scope refused the ban.
#
# Honesty constraint (``19-R8``): the sentences must be truthful about tiers.
# ``is_banned`` refuses login and publishing, but it does NOT revoke an existing
# web session — the web tier has no per-request account-state gate
# (``15-AUTHZ-001``). So the copy never claims a total lockout.
_BAN_REFUSAL_MESSAGES: dict[BanRefusalReason, str] = {
    BanRefusalReason.SELF: (
        "The ban was not applied: the ad's owner is your own account."
    ),
    BanRefusalReason.PRIVILEGED: (
        "The ban was not applied: the ad's owner is a staff or superuser "
        "account you are not permitted to ban."
    ),
    BanRefusalReason.ALREADY_BANNED: (
        "The ban was not applied: the ad's owner was already banned."
    ),
    BanRefusalReason.NOT_IN_TARGET_SET: (
        "The ban was not applied: the ad's owner is outside the set of "
        "accounts you may ban."
    ),
}


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

    The approvable set is ``{ON_MODERATION, ON_MODERATION_FAILED}``, mirroring
    the reject view. A refusal from the state machine is surfaced as a message;
    the branch is on the returned outcome only (business logic does not live in
    the view body).

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
            status__in=[AdStatus.ON_MODERATION, AdStatus.ON_MODERATION_FAILED],
        )
        outcome = do_approve(ad, request.user.id)

        if outcome is ApproveOutcome.PUBLISHED:
            logger.info("Admin %s approved ad %s", request.user.id, ad_id)
        else:
            messages.warning(request, _APPROVE_OUTCOME_MESSAGES[outcome])
            logger.info(
                "Admin %s approval of ad %s not applied (%s)",
                request.user.id,
                ad_id,
                outcome,
            )

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
        result = ban_user_for_ad(
            ad,
            request.user.id,
            request.POST.get("ban_reason", "No reason provided") or "No reason provided",
        )

        if result.changed:
            logger.info("Admin %s banned user via ad %s", request.user.id, ad_id)
        else:
            outcome = ban_refusal_reason(result)
            messages.warning(request, _BAN_REFUSAL_MESSAGES[outcome])
            logger.info(
                "Admin %s ban via ad %s not applied (%s)",
                request.user.id,
                ad_id,
                outcome,
            )

    return redirect("/admin/ads/ad/?status__exact=on_moderation")
