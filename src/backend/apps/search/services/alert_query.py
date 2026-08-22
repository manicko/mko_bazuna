"""
Alert query service for saved search matching.

Provides functions to find PUBLISHED ads matching a saved search's filters
(FTS query, city, category subtree, price range) and record notifications
to prevent duplicate alerts.

Reuses FTS patterns from the web search view. The saved search's persisted
``language`` picks the matching per-language vector + FTS config (no query
translation), with SearchRank ordering and Efficient Exists/OuterRef dedup.
"""

import logging
from typing import cast

from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db.models import Exists, F, OuterRef, QuerySet

from apps.ads.models import Ad
from apps.categories.models import Category
from apps.core.enums import AdStatus, LanguageLocale
from apps.search.models import SavedSearch, SavedSearchNotification

logger = logging.getLogger(__name__)


def find_matching_ads(saved_search: SavedSearch) -> list[Ad]:
    """
    Find newly published ads matching a saved search.

    Applies an FTS query (searched in the saved search's language via
    ``saved_search.language``, no translation), category subtree, city, and
    price filters.  Matches are ranked by relevance and capped at 10 per
    digest.  Ads already notified via ``SavedSearchNotification`` are
    excluded via a correlated NOT EXISTS subquery for efficiency.

    Args:
        saved_search: The SavedSearch to match against.

    Returns:
        List of matching Ad objects (max 10), ordered by relevance.
    """
    queryset: QuerySet[Ad] = (
        Ad.objects.filter(status=AdStatus.PUBLISHED)
        .select_related("category", "city")
    )

    # Apply FTS query in the saved search's persisted language (no translation)
    if saved_search.query:
        locale = LanguageLocale.from_code(
            saved_search.language,
            fallback=LanguageLocale.RUSSIAN,
        )
        vector_field = locale.fts_vector_field
        config = locale.fts_config

        search_query = SearchQuery(
            saved_search.query,
            search_type="websearch",
            config=config,
        )
        queryset = queryset.annotate(
            rank=SearchRank(F(vector_field), search_query),
        ).filter(
            **{vector_field: search_query},
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

    # Apply price range filters (min/max are EUR-equivalent, WR-04/PO-04)
    if saved_search.min_price is not None:
        queryset = queryset.filter(price_normalized_eur__gte=saved_search.min_price)
    if saved_search.max_price is not None:
        queryset = queryset.filter(price_normalized_eur__lte=saved_search.max_price)

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


def find_matching_saved_searches(ad: Ad) -> list[SavedSearch]:
    """
    Find active saved searches whose filters match a given PUBLISHED ad.

    This is the ad-centric inverse of ``find_matching_ads``: per saved search
    it applies the language-aware FTS query against the *ad's own vector*,
    a city filter, a category-subtree filter, and a price range. Used by the
    near-real-time publish-time delivery (AL-001).

    Only ``is_active=True`` searches are considered (reuses the
    ``IX_saved_searches_user_active`` index). Membership in a category subtree
    is tested via the ad's ``category_id``.

    Args:
        ad: A PUBLISHED Ad to match saved searches against.

    Returns:
        List of active SavedSearch objects matching the ad.
    """
    candidates = SavedSearch.objects.filter(is_active=True).select_related(
        "user", "city", "category"
    )

    matches: list[SavedSearch] = []
    for saved_search in candidates:
        if not _ad_matches_saved_search(ad, saved_search):
            continue
        matches.append(saved_search)

    return matches


def _ad_matches_saved_search(ad: Ad, saved_search: SavedSearch) -> bool:
    """Return True when ``ad`` satisfies all of ``saved_search``'s filters."""
    # City filter
    if saved_search.city_id and saved_search.city_id != ad.city_id:
        return False

    # Price range filter (EUR-normalized value, WR-04/PO-04)
    if saved_search.min_price is not None:
        if ad.price_normalized_eur is None or ad.price_normalized_eur < saved_search.min_price:
            return False
    if saved_search.max_price is not None:
        if ad.price_normalized_eur is None or ad.price_normalized_eur > saved_search.max_price:
            return False

    # Category-subtree filter
    if saved_search.category_id and not _ad_in_category_subtree(
        ad, saved_search.category_id
    ):
        return False

    # Language-aware FTS query against the ad's own vector
    if saved_search.query and not _ad_matches_vector(ad, saved_search):
        return False

    return True


def _ad_in_category_subtree(ad: Ad, category_id: int) -> bool:
    """Return True when the ad's category is inside the given subtree."""
    descendant_ids = list(
        Category.objects.get(pk=category_id)
        .get_descendants(include_self=True)
        .values_list("pk", flat=True)
    )
    return ad.category_id in descendant_ids


def _ad_matches_vector(ad: Ad, saved_search: SavedSearch) -> bool:
    """Return True when the saved search's FTS query matches the ad's vector.

    The query is searched against the vector for the saved search's persisted
    ``language`` (falling back to Russian), reusing the FTS config/field
    selection pattern from ``find_matching_ads``.
    """
    locale = LanguageLocale.from_code(
        saved_search.language,
        fallback=LanguageLocale.RUSSIAN,
    )
    search_query = SearchQuery(
        saved_search.query,
        search_type="websearch",
        config=locale.fts_config,
    )
    return Ad.objects.filter(
        pk=ad.pk,
        **{locale.fts_vector_field: search_query},
    ).exists()