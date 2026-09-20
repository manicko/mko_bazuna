"""
Signal handlers for search cache invalidation.

Bumps the content-freshness version whenever an ad changes in a way that
could affect the buyer-visible PUBLISHED search result set:

- **status transitions** — any change that adds/removes an ad from search
  results (e.g. DRAFT→PUBLISHED, PUBLISHED→ARCHIVED/DELETED).
- **content edits** — title, description, category, city, price, listing
  purpose, or published_at changes that alter what or how ads match.
- **feature M2M edits** — adding or removing features on a visible ad.

The version counter is embedded in every cache key built by
``build_search_cache_key``, so a single ``cache.incr`` makes all stale
entries unreachable without a global prefix wipe.

Best-effort: the invalidation runs outside the DB transaction's critical
path (signals fire after commit).  A cache backend failure is caught
and logged — the DB save has already committed.
"""

import logging

from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver

from apps.ads.models import Ad
from apps.core.enums import AdStatus
from apps.search.services.cache import bump_search_version

logger = logging.getLogger(__name__)

# Buyer-visible statuses whose transitions affect the PUBLISHED search
# result set.  Used when ``update_fields`` is None (full save / create)
# to decide whether the ad could appear in buyers' search results.
_SEARCH_RESULT_AFFECTING_STATUSES = frozenset(
    {AdStatus.PUBLISHED, AdStatus.ARCHIVED, AdStatus.DELETED}
)

# Model fields whose changes (via ``update_fields``) also affect search
# results.  When a targeted ``save(update_fields=...)`` touches any of
# these, the search content version is bumped.
_SEARCH_RELEVANT_FIELDS = frozenset(
    {
        "status",
        "title",
        "title_en",
        "title_bs",
        "description",
        "description_en",
        "description_bs",
        "category",
        "city",
        "price_amount",
        "price_normalized_eur",
        "listing_purpose",
        "listing_condition",
        "published_at",
    }
)


@receiver(post_save, sender=Ad)
def bump_search_cache_on_ad_change(sender, instance: Ad, **kwargs):  # type: ignore[no-untyped-def]
    """Bump the search content version when an ad's status or content changes.

    Two cases:

    - **Full save** (``update_fields`` is None, e.g. ``Ad.objects.create`` or
      a save without ``update_fields``): bump when the ad is currently
      buyer-visible (status in PUBLISHED / ARCHIVED / DELETED).
    - **Targeted save** (``update_fields`` set): bump only when any field
      in :data:`_SEARCH_RELEVANT_FIELDS` is among the updated fields.

    Best-effort: cache failures are caught and logged.
    """
    update_fields = kwargs.get("update_fields")

    if update_fields is None:
        # Full save / create — check whether the ad is buyer-visible.
        if instance.status not in _SEARCH_RESULT_AFFECTING_STATUSES:
            return
    else:
        # Targeted update — only bump for search-relevant fields.
        if not any(field in _SEARCH_RELEVANT_FIELDS for field in update_fields):
            return

    try:
        bump_search_version()
    except Exception:
        logger.warning(
            "Search cache version bump failed for Ad %d — cache will "
            "refresh on next read",
            instance.id,
            exc_info=True,
        )
    else:
        logger.debug(
            "Bumped search content version due to Ad %d change (update_fields=%s)",
            instance.id,
            update_fields,
        )


@receiver(m2m_changed, sender=Ad.features.through)
def bump_search_cache_on_feature_change(sender, instance: Ad, action: str, **kwargs):  # type: ignore[no-untyped-def]
    """Bump the search content version when an ad's features M2M changes.

    ``m2m_changed`` fires separately from ``post_save`` — changes to the
    ``features`` field do not appear in ``update_fields``.  Only
    ``post_add`` and ``post_remove`` actions are relevant (pre-/clear
    actions do not mutate data).

    Best-effort: cache failures are caught and logged.
    """
    if action not in ("post_add", "post_remove"):
        return

    try:
        bump_search_version()
    except Exception:
        logger.warning(
            "Search cache version bump failed for Ad %d feature change — "
            "cache will refresh on next read",
            instance.id,
            exc_info=True,
        )
    else:
        logger.debug(
            "Bumped search content version due to Ad %d feature change (%s)",
            instance.id,
            action,
        )
