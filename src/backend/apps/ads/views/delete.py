"""
Seller ad delete view for Mko Bazuna.

Implements US-S6 self-delete ad flow:
    - Seller can delete ONLY own ads
    - Status set to DELETED, hidden immediately from public
    - Wrong-owner returns 403 Forbidden
    - Physical cleanup deferred to Phase 4 sweeps

The transition itself lives in the shared lifecycle service (S4.1) so the
future ``/api/v1/ads/{id}/delete/`` endpoint runs the same state mechanics.
This flow is deliberately gate-free: no consent or audience check applies.
"""

import logging

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.ads.services.lifecycle import delete_ad

logger = logging.getLogger(__name__)


@require_POST
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
    try:
        delete_ad(ad_id, request.user.id)
    except PermissionDenied:
        return HttpResponseForbidden(_("You do not have permission to delete this ad."))

    return redirect("ads:dashboard")
