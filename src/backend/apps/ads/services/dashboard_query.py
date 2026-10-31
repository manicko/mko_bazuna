"""
Seller dashboard grouping queries.

Extracted verbatim from ``apps.ads.views.dashboard`` (API-parity S2.2) so that
the HTML dashboard and the future ``GET /api/v1/dashboard/`` endpoint consume
one shared, request-free grouping stack instead of two hand-built queries.

Contract: request-free, returns ORM objects (the project's service contract).
The function takes the seller id and returns the grouped querysets the view
iterates; it carries no view/HTTP coupling and no consent logic. The
create-time storage-consent gate (``_seller_may_create_ad``) deliberately
stays in the view (auditor A14): this module never imports it, and never
imports ``apps.users.services.account_state.can_create_ad`` — the later S2.3
endpoint re-asserts consent through that shared seam at its own boundary.
"""

import logging

from django.db.models import QuerySet

from apps.ads.models import Ad
from apps.core.enums import AdStatus

logger = logging.getLogger(__name__)


def ads_by_status(user_id: int) -> dict[AdStatus, QuerySet[Ad]]:
    """Group the seller's ads by status for the dashboard.

    Returns one queryset per dashboard status, in the same key order the view
    rendered before the extraction:

        - PUBLISHED: live ads visible to buyers (prefetch images)
        - ON_MODERATION: pending review
        - ON_MODERATION_FAILED: failed auto-check
        - ARCHIVED: auto- or manually archived (prefetch images)
        - REJECTED: manually rejected by a moderator

    Each group keeps the exact ``.select_related("category", "city")`` (and,
    for PUBLISHED / ARCHIVED, ``.prefetch_related("images")``) this surface
    used, so template rendering issues the same queries as before.
    """
    return {
        AdStatus.PUBLISHED: Ad.objects.filter(
            user_id=user_id, status=AdStatus.PUBLISHED
        )
        .prefetch_related("images")
        .select_related("category", "city"),
        AdStatus.ON_MODERATION: Ad.objects.filter(
            user_id=user_id, status=AdStatus.ON_MODERATION
        ).select_related("category", "city"),
        AdStatus.ON_MODERATION_FAILED: Ad.objects.filter(
            user_id=user_id, status=AdStatus.ON_MODERATION_FAILED
        ).select_related("category", "city"),
        AdStatus.ARCHIVED: Ad.objects.filter(
            user_id=user_id, status=AdStatus.ARCHIVED
        )
        .prefetch_related("images")
        .select_related("category", "city"),
        AdStatus.REJECTED: Ad.objects.filter(
            user_id=user_id, status=AdStatus.REJECTED
        ).select_related("category", "city"),
    }
