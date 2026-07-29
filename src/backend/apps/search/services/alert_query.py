"""
Alert query service for saved search matching.

Provides functions to find PUBLISHED ads matching a saved search's filters
(FTS query, city, category subtree, price range) and record notifications
to prevent duplicate alerts.

Reuses FTS patterns from the web search view with Bosnian-to-Russian
translation, SearchRank ordering, and Efficient Exists/OuterRef dedup.
"""

import logging
from typing import cast

from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db.models import Exists, OuterRef, QuerySet

from apps.ads.models import Ad
from apps.categories.models import Category
from apps.core.enums import AdStatus
from apps.search.models import SavedSearch, SavedSearchNotification
from apps.search.services.query_translator import translate_query_bs_to_ru

logger = logging.getLogger(__name__)


def find_matching_ads(saved_search: SavedSearch) -> list[Ad]:
    """
    Find newly published ads matching a saved search.

    Applies FTS query (with Bosnian-to-Russian translation), category
    subtree, city, and price filters.  Matches are ranked by relevance
    and capped at 10 per digest.  Ads already notified via
    ``SavedSearchNotification`` are excluded via a correlated NOT EXISTS
    subquery for efficiency.

    Args:
        saved_search: The SavedSearch to match against.

    Returns:
        List of matching Ad objects (max 10), ordered by relevance.
    """
    queryset: QuerySet[Ad] = (
        Ad.objects.filter(status=AdStatus.PUBLISHED)
        .select_related("category", "city")
    )

    # Apply FTS query with Bosnian-to-Russian translation
    if saved_search.query:
        translated_query = translate_query_bs_to_ru(saved_search.query)

        search_query = SearchQuery(
            translated_query,
            search_type="websearch",
            config="russian",
        )
        queryset = queryset.annotate(
            rank=SearchRank("search_vector", search_query),
        ).filter(
            search_vector=search_query,
        ).order_by("-rank")

    # Apply city filter if specified
    if saved_search.city_id:
        queryset = queryset.filter(city_id=saved_search.city_id)

    # Apply category filter with subtree support
    if saved_search.category_id:
        category = saved_search.category
        if category is not None:
            descendant_ids: list[int] = list(
                Category.objects.get(pk=category.pk)
                .get_descendants(include_self=True)
                .values_list("pk", flat=True)
            )
            queryset = queryset.filter(category_id__in=descendant_ids)

    # Apply price range filters
    if saved_search.min_price is not None:
        queryset = queryset.filter(price__gte=saved_search.min_price)
    if saved_search.max_price is not None:
        queryset = queryset.filter(price__lte=saved_search.max_price)

    # Exclude ads already notified (efficient correlated NOT EXISTS subquery)
    notified_ads = SavedSearchNotification.objects.filter(
        saved_search=saved_search,
        ad_id=OuterRef("pk"),
    )
    queryset = queryset.filter(~Exists(notified_ads))

    return cast(list[Ad], list(queryset[:10]))


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
        Number of notification records passed in (not necessarily created).
    """
    notifications = [
        SavedSearchNotification(saved_search=saved_search, ad=ad)
        for ad in ads
    ]
    SavedSearchNotification.objects.bulk_create(
        notifications,
        ignore_conflicts=True,
    )
    count = len(ads)
    if count:
        logger.info(
            "Recorded %d notifications for saved search %d",
            count,
            saved_search.pk,
        )
    return count