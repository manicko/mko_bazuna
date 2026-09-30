"""
Saved-search alert delivery-state contract (03-DB-007).

The single place the delivery contract lives. It imports neither
``immediate_alerts`` nor ``send_alerts`` so there is no import cycle between the
module that defines the contract and the two paths that apply it.

A ``SavedSearchNotification`` row is an ATTEMPT RECORD; ``delivered_at`` is the
RECEIPT. Both delivery paths exclude a pair from matching only when
``delivered_at IS NOT NULL``, and both call ``mark_delivered`` after a
successful send. ``NULL`` therefore means "recorded but not delivered" and the
pair stays eligible — which is what turns a failed or skipped send into a
retry instead of a permanent loss.
"""

import logging
from datetime import datetime
from enum import StrEnum

from apps.search.models import SavedSearchNotification

logger = logging.getLogger(__name__)


class DeliveryOutcome(StrEnum):
    """Log-record vocabulary for the outcome of a ``mark_delivered`` call.

    Not a database column: the delivered state is binary-by-nullness, and
    storing a second state column would duplicate it. These values name the two
    observable outcomes in log records only.
    """

    DELIVERED = "delivered"
    SKIPPED_ALREADY_DELIVERED = "skipped-already-delivered"


def mark_delivered(
    saved_search_id: int, ad_id: int, *, sent_at: datetime
) -> bool:
    """Record the delivery receipt for one ``(saved_search_id, ad_id)`` pair.

    Issues exactly one conditional statement in autocommit, with no
    ``transaction.atomic()`` and no advisory lock. It is idempotent:

    * returns ``True`` when THIS call recorded the delivery (it updated the
      previously-undelivered row);
    * returns ``False`` when the row was already marked — a concurrent tick won
      the race. That is the duplicate DETECTOR, not a duplicate preventer, so it
      is logged at WARNING with the ``(saved_search_id, ad_id)`` pair.

    Args:
        saved_search_id: Primary key of the saved search.
        ad_id: Primary key of the ad.
        sent_at: The timestamp to record as the delivery receipt.

    Returns:
        ``True`` if this call recorded the delivery, ``False`` if it was a no-op.
    """
    updated = SavedSearchNotification.objects.filter(
        saved_search_id=saved_search_id,
        ad_id=ad_id,
        delivered_at__isnull=True,
    ).update(delivered_at=sent_at)

    if updated:
        return True

    logger.warning(
        "Alert delivery already delivered for saved_search_id=%s ad_id=%s (%s)",
        saved_search_id,
        ad_id,
        DeliveryOutcome.SKIPPED_ALREADY_DELIVERED,
    )
    return False
