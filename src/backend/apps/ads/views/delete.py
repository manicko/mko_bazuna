"""
Seller ad delete view for Mko Bazuna.

Implements US-S6 self-delete ad flow:
    - Seller can delete ONLY own ads
    - Status set to DELETED, hidden immediately from public
    - Wrong-owner returns 403 Forbidden
    - Physical cleanup deferred to Phase 4 sweeps

This view owns the transaction, the row lock and the authorization: it opens
``transaction.atomic()``, fetches the ad under ``select_for_update()`` and
refuses a non-owner, and the shared lifecycle service applies the
``-> DELETED`` transition to that locked row. This flow is deliberately
gate-free: no consent or audience check applies.
"""

import logging

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.ads.models import Ad
from apps.ads.services.lifecycle import delete_ad
from apps.ads.views.edit import _ownership_refused_forbidden

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
        Redirect to dashboard, 403 Forbidden if unauthorized, or 404 if the
        ad does not exist
    """
    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]  # django-stubs not installed; Atomic lacks CM stubs
        ad = get_object_or_404(Ad.objects.select_for_update(), id=ad_id)

        if ad.user_id != request.user.id:
            return _ownership_refused_forbidden(
                _("You do not have permission to delete this ad."),
                "delete",
                ad_id,
                request.user.id,
            )

        delete_ad(ad)

    return redirect("ads:dashboard")
