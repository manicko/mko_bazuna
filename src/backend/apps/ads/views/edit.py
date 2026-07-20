"""
Seller ad edit views for Mko Bazuna.

Implements US-S5/S7 edit flow with zone C2 hide-on-text-edit behavior:
    - Text edits (title/description): PUBLISHED -> ON_MODERATION, immediately hidden
    - Price/photo edits: save immediately, status stays PUBLISHED
    - Mixed edits follow text rule (re-moderation)
    - Reactivate (ARCHIVED -> PUBLISHED): text re-checked, hidden until pass
"""

import logging

from apps.ads.models import Ad
from apps.core.enums import AdStatus
from apps.moderation.services.auto_moderation import auto_moderate
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

logger = logging.getLogger(__name__)


def _text_fields_changed(request: HttpRequest, ad: Ad) -> bool:
    """
    Check if text fields (title/description) were changed in the request.

    Args:
        request: HTTP request with POST data
        ad: The ad being edited

    Returns:
        True if title or description was changed, False otherwise
    """
    new_title = (request.POST.get("title") or "").strip()
    new_description = (request.POST.get("description") or "").strip()

    # Check if either field changed (compare with current values)
    return new_title != ad.title or new_description != ad.description


@login_required
def ad_edit(request: HttpRequest, ad_id: int) -> HttpResponse:
    """
    Edit view for seller's own ads.

    Behavior by status and field type:
        - PUBLISHED + text edit: -> ON_MODERATION, immediately hidden
        - PUBLISHED + price/photo edit: stays PUBLISHED, public within 5s
        - PUBLISHED + mixed edit: follows text rule
        - ARCHIVED + reactivate: text re-checked, hidden until pass
        - Other statuses: direct save (ON_MODERATION, ON_MODERATION_FAILED)

    Args:
        request: HTTP request (authenticated user required)
        ad_id: The ad ID to edit

    Returns:
        Rendered edit form or redirect after save
    """
    ad = get_object_or_404(Ad, id=ad_id)

    # Authorization check: must own the ad (returns 403 Forbidden)
    if ad.user_id != request.user.id:
        logger.warning(
            f"User {request.user.id} attempted to edit ad {ad_id} owned by {ad.user_id}"
        )
        return HttpResponseForbidden("You do not have permission to edit this ad.")

    if request.method == "GET":
        # Prefetch images for the edit template
        ad = Ad.objects.prefetch_related("images").get(id=ad_id)
        context = {
            "ad": ad,
        }
        return render(request, "ads/edit.html", context)

    # POST: process edit
    # Determine if this is a reactivation request
    is_reactivation = ad.status == AdStatus.ARCHIVED and request.POST.get("reactivate")

    # Get form data - use empty string defaults to ensure non-None values
    new_title = (request.POST.get("title") or "").strip()
    new_description = (request.POST.get("description") or "").strip()
    new_price = request.POST.get("price")

    # Parse price
    price_value = None
    if new_price:
        try:
            price_value = int(new_price)
        except ValueError:
            pass

    # Determine edit type
    has_text_change = _text_fields_changed(request, ad)

    if is_reactivation:
        # Reactivation: update fields then run moderation check
        ad.title = new_title
        ad.description = new_description
        if price_value is not None:
            ad.price = price_value
        ad.save(update_fields=["title", "description", "price"])

        # Transition to ON_MODERATION (clears archived_at via transition_to)
        ad.transition_to(AdStatus.ON_MODERATION)

        # Run auto-moderation check
        passed = auto_moderate(ad)

        if passed:
            # Auto-moderate sets status to PUBLISHED and published_at
            return redirect("ads:dashboard")
        else:
            # Moderation failed - stay on edit page with error
            ad = Ad.objects.prefetch_related("images").get(id=ad_id)
            return render(
                request,
                "ads/edit.html",
                {"ad": ad, "error": "Ad failed moderation checks"},
            )

    elif ad.status == AdStatus.PUBLISHED:
        # Zone C2: Text edit -> ON_MODERATION, hidden immediately
        # Price/photo edit -> stays PUBLISHED
        # Mixed edit -> follows text rule
        if has_text_change:
            # Text edit: go to moderation
            ad.title = new_title
            ad.description = new_description
            if price_value is not None:
                ad.price = price_value
            ad.save(update_fields=["title", "description", "price", "updated_at"])

            # Use transition_to for status change to ON_MODERATION
            ad.transition_to(AdStatus.ON_MODERATION)
            logger.info(f"Ad {ad_id} text edited, moved to ON_MODERATION")
        else:
            # Price/photo only edit: stay published
            ad.price = price_value
            ad.save(update_fields=["price", "updated_at"])
            logger.info(f"Ad {ad_id} price/photo edited, stays PUBLISHED")

        return redirect("ads:dashboard")

    else:
        # Other statuses (ON_MODERATION, ON_MODERATION_FAILED): direct save
        ad.title = new_title
        ad.description = new_description
        if price_value is not None:
            ad.price = price_value
        ad.save(update_fields=["title", "description", "price", "updated_at"])
        logger.info(f"Ad {ad_id} edited in status {ad.status}")

        return redirect("ads:dashboard")


@login_required
def ad_archive(request: HttpRequest, ad_id: int) -> HttpResponse:
    """
    Archive an ad (PUBLISHED -> ARCHIVED).

    Manual archive action for sellers. Does not require moderation.

    Args:
        request: HTTP request (authenticated user required)
        ad_id: The ad ID to archive

    Returns:
        Redirect to dashboard or 403 Forbidden if unauthorized
    """
    ad = get_object_or_404(Ad, id=ad_id)

    # Authorization check
    if ad.user_id != request.user.id:
        logger.warning(
            f"User {request.user.id} attempted to archive ad {ad_id} owned by {ad.user_id}"
        )
        return HttpResponseForbidden("You do not have permission to archive this ad.")

    if ad.status == AdStatus.PUBLISHED:
        ad.transition_to(AdStatus.ARCHIVED)
        logger.info(f"Ad {ad_id} archived by user {request.user.id}")

    return redirect("ads:dashboard")


@login_required
def ad_reactivate(request: HttpRequest, ad_id: int) -> HttpResponse:
    """
    Reactivate an archived ad (ARCHIVED -> PUBLISHED or ON_MODERATION).

    Text is re-checked via auto-moderation. Ad is immediately hidden
    until moderation passes.

    Args:
        request: HTTP request (authenticated user required)
        ad_id: The ad ID to reactivate

    Returns:
        Redirect to dashboard or 403 Forbidden if unauthorized
    """
    ad = get_object_or_404(Ad, id=ad_id)

    # Authorization check
    if ad.user_id != request.user.id:
        logger.warning(
            f"User {request.user.id} attempted to reactivate ad {ad_id} owned by {ad.user_id}"
        )
        return HttpResponseForbidden("You do not have permission to reactivate this ad.")

    if ad.status == AdStatus.ARCHIVED:
        # Update status to ON_MODERATION for re-check (transition_to clears archived_at)
        ad.transition_to(AdStatus.ON_MODERATION)

        # Run auto-moderation check
        auto_moderate(ad)

        logger.info(f"Ad {ad_id} reactivation initiated by user {request.user.id}")

    return redirect("ads:dashboard")
