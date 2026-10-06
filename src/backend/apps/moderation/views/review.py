"""
Moderation review views for Mko Bazuna.

Views for admin-only moderation interface: review queue, approve, reject, ban, delete.
"""

import logging

from django.contrib import messages
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext
from django.views.decorators.http import require_POST

from apps.ads.models import Ad
from apps.core.enums import AdStatus, ApproveOutcome, CategoryRejectReason
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
    # The all-zero shape is reached by two producers with different causes (an
    # owner account that no longer exists, and a candidate set that did not
    # contain the row), so this sentence is deliberately cause-neutral: it must
    # not assert a specific cause that is false for one of them.
    BanRefusalReason.NOT_IN_TARGET_SET: (
        "The ban was not applied: the ad's owner was not among the accounts "
        "available to this action."
    ),
}

# The two-sided tier truth (``19-R8``), stated once on this surface so it does
# not become a fifth parallel refusal sentence: it is NOT a member of
# ``_BAN_REFUSAL_MESSAGES`` and is not repeated inside each of its four values.
# It is interpolated once at the refusal call site instead. The wording is
# identical to ``apps/ads/admin.py``'s ``BAN_TIER_ENFORCEMENT`` — same language
# on both operator surfaces — and is deliberately a duplicated literal: importing
# it would create a new app-to-app import edge (``moderation.views`` ->
# ``ads.admin``), mirroring the ``SKIPPED_BANNED_ROWS_PREFIX`` precedent.
# It states that a ban refuses login and publishing and is enforced in the
# Telegram bot tier, but does NOT revoke an existing web session (no per-request
# web gate for ``is_banned``, ``15-AUTHZ-001``); never claim a total lockout.
BAN_TIER_ENFORCEMENT = (
    "A ban refuses login and publishing, and is enforced in the Telegram bot; "
    "it does not revoke an existing web session, which keeps working until it "
    "expires."
)


def _review_context(
    ad: Ad,
    *,
    error: str | None = None,
    reason_category: str = "",
    reason_text: str = "",
) -> dict[str, object]:
    """Build the shared context for the moderation review page.

    ``moderation_review`` renders the bare one-key context; ``reject_ad``
    re-renders it with a translated error and the moderator's typed input
    preserved when the submitted ``reason_category`` is not a
    ``CategoryRejectReason`` member (Q2 ruling, 2026-10-03).
    """
    context: dict[str, object] = {"ad": ad}
    if error is not None:
        context["error"] = error
        context["reason_category"] = reason_category
        context["reason_text"] = reason_text
    return context


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

    return render(request, "admin/moderation/review.html", _review_context(ad))


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

        return redirect(reverse("admin:ads_ad_change", args=[ad_id]))


@require_POST
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

    raw_reason_category = request.POST.get("reason_category", "") or ""
    reason_text = (request.POST.get("reason_text") or "").strip()

    try:
        reason_category = CategoryRejectReason(raw_reason_category)
    except ValueError:
        ad = get_object_or_404(
            Ad.objects.select_related("user", "category", "city").prefetch_related(
                "images"
            ),
            id=ad_id,
            status__in=[AdStatus.ON_MODERATION, AdStatus.ON_MODERATION_FAILED],
        )
        return render(
            request,
            "admin/moderation/review.html",
            _review_context(
                ad,
                error=gettext(
                    "The reject reason is not valid. "
                    "Select one of the listed reasons and try again."
                ),
                reason_category=raw_reason_category,
                reason_text=reason_text,
            ),
        )

    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
        ad = get_object_or_404(
            Ad.objects.select_for_update(),
            id=ad_id,
            status__in=[AdStatus.ON_MODERATION, AdStatus.ON_MODERATION_FAILED],
        )
        reason = f"{reason_category.value}"
        if reason_text:
            reason = f"{reason_category.value}: {reason_text}"
        do_reject(ad, request.user.id, reason)

    logger.info("Admin %s rejected ad %s", request.user.id, ad_id)
    return redirect(
        f"{reverse('admin:ads_ad_changelist')}?status__exact=on_moderation"
    )


@require_POST
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
            messages.warning(
                request,
                f"{_BAN_REFUSAL_MESSAGES[outcome]} {BAN_TIER_ENFORCEMENT}",
            )
            logger.info(
                "Admin %s ban via ad %s not applied (%s)",
                request.user.id,
                ad_id,
                outcome,
            )

    return redirect(
        f"{reverse('admin:ads_ad_changelist')}?status__exact=on_moderation"
    )
