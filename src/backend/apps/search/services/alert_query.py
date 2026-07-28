"""
Alert query service for saved search matching.

Provides functions to find PUBLISHED ads matching a saved search's filters
(FTS query, city, category subtree, price range) and record notifications
to prevent duplicate alerts.
"""

import logging

from django.contrib.postgres.search import SearchQuery
from django.db.models import QuerySet

from apps.ads.models import Ad
from apps.categories.models import Category
from apps.core.enums import AdStatus
from apps.search.models import SavedSearch, SavedSearchNotification

logger = logging.getLogger(__name__)


def find_matching_ads(saved_search: SavedSearch) -> list[Ad]:
    """
    Find new PUBLISHED ads matching a saved search's filters.

    Applies the following filters when the corresponding field is set on the
    saved search:
        - FTS query via ``search_vector`` using websearch syntax
        - City exact match
        - Category subtree match (includes all descendants via MPTT)
        - Price range (min_price / max_price)

    Ads that have already been notified for this saved search (recorded in
    ``SavedSearchNotification``) are excluded.

    Args:
        saved_search: The saved search instance whose filters to apply.

    Returns:
        List of matching Ad instances (evaluated queryset).
    """
    queryset: QuerySet[Ad] = Ad.objects.filter(status=AdStatus.PUBLISHED)

    # FTS query search
    if saved_search.query:
        search_query = SearchQuery(
            saved_search.query,
            search_type="websearch",
            config="russian",
        )
        queryset = queryset.filter(search_vector=search_query)

    # City filter
    if saved_search.city_id:
        queryset = queryset.filter(city=saved_search.city)

    # Category filter with MPTT subtree expansion
    if saved_search.category_id:
        category = saved_search.category
        if category is not None:
            descendant_ids: list[int] = list(
                Category.objects.get(pk=category.pk)
                .get_descendants(include_self=True)
                .values_list("pk", flat=True)
            )
            queryset = queryset.filter(category_id__in=descendant_ids)

    # Price range filter
    if saved_search.min_price is not None:
        queryset = queryset.filter(price__gte=saved_search.min_price)
    if saved_search.max_price is not None:
        queryset = queryset.filter(price__lte=saved_search.max_price)

    # Exclude ads already notified for this saved search
    notified_ad_ids = (
        SavedSearchNotification.objects.filter(saved_search=saved_search)
        .values_list("ad_id", flat=True)
    )
    queryset = queryset.exclude(pk__in=notified_ad_ids)

    return list(queryset)


def record_notifications(saved_search: SavedSearch, ads: list[Ad]) -> int:
    """
    Bulk-create SavedSearchNotification records, skipping duplicates.

    Uses ``bulk_create`` with ``ignore_conflicts=True`` so that any
    (saved_search, ad) pair that already exists is silently skipped. The
    unique constraint on ``(saved_search, ad)`` prevents duplicates.

    Args:
        saved_search: The saved search that triggered the notification.
        ads: The matching ads to record notifications for.

    Returns:
        Number of notification records actually created.
    """
    notifications = [
        SavedSearchNotification(saved_search=saved_search, ad=ad)
        for ad in ads
    ]
    created = SavedSearchNotification.objects.bulk_create(
        notifications,
        ignore_conflicts=True,
    )
    count = len(created)
    if count:
        logger.info(
            "Recorded %d notifications for saved search %d",
            count,
            saved_search.pk,
        )
    return count