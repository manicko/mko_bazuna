"""
Seller ad delete view for Mko Bazuna.

Implements US-S6 self-delete ad flow:
    - Seller can delete ONLY own ads
    - Status set to DELETED, hidden immediately from public
    - Wrong-owner returns 403 Forbidden
    - Physical cleanup deferred to Phase 4 sweeps
"""

import logging

from apps.ads.models import Ad
from apps.core.enums import AdStatus
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)


@login_required
def ad_delete(request: HttpRequest, ad_id: int) -> HttpResponse:
    """
    Delete an ad by setting its status to DELETED.

    Seller self-delete action. Ad is immediately hidden from public listings.
    Physical cleanup is deferred to Phase 4 archive/delete sweeps.

    Args:
        request: HTTP request (authenticated user required)
        ad_id: The ad ID to delete

    Returns:
        Redirect to dashboard or 403 Forbidden if unauthorized
    """
    ad = get_object_or_404(Ad, id=ad_id)

    # Authorization check: must own the ad
    if ad.user_id != request.user.id:
        logger.warning(
            f"User {request.user.id} attempted to delete ad {ad_id} owned by {ad.user_id}"
        )
        return HttpResponseForbidden(_("You do not have permission to delete this ad."))

    # Transition to DELETED (transition_to handles deleted_at timestamp)
    if ad.status != AdStatus.DELETED:
        ad.transition_to(AdStatus.DELETED)
        logger.info(f"Ad {ad_id} deleted by user {request.user.id}")

    return redirect("ads:dashboard")
