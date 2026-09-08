"""
Analytics event recording service for Mko Bazuna.

Provides a single transaction-transparent entry point for persisting
``AnalyticsEvent`` rows from views. Recording failures must never break the
request lifecycle, so all persistence errors are caught, logged, and
swallowed. This function performs NO ``transaction.atomic()`` so it remains
transparent to the caller's transaction boundary.
"""

import logging

from apps.analytics.models import AnalyticsEvent
from apps.core.enums import AdSource, AnalyticsEventType

logger = logging.getLogger(__name__)


def record_event(
    event_type: AnalyticsEventType,
    user_id: int | None = None,
    *,
    ad_id: int | None = None,
    source: AdSource | None = None,
) -> AnalyticsEvent | None:
    """Persist an analytics event, never raising on failure.

    The single INSERT is the only query issued on the success path, keeping
    the ad-detail render budget (see ``test_ad_detail_queries._QUERY_BOUND``)
    within scope. On any persistence error the exception is logged (with
    traceback) and ``None`` is returned so callers can continue unaffected.

    Args:
        event_type: The analytics event type to record.
        user_id: Optional user ID (nullable FK: buyer may be anonymous,
            seller via ``ad.user_id``).
        ad_id: Optional ad ID (keyword-only, nullable FK for non-ad events).
        source: Optional event origin (keyword-only; ``None`` = production,
            ``"seed"`` = seed-generated).

    Returns:
        The persisted ``AnalyticsEvent`` instance, or ``None`` if recording
        failed.
    """
    try:
        return AnalyticsEvent.objects.create(
            event_type=event_type,
            user_id=user_id,
            ad_id=ad_id,
            source=source,
        )
    except Exception:  # noqa: BLE001 — analytics must never break the request
        logger.exception(
            "Failed to record analytics event %s (user_id=%s, ad_id=%s, source=%s)",
            event_type,
            user_id,
            ad_id,
            source,
        )
        return None
