"""
Signal handlers for search cache invalidation.

Bumps the content-freshness version whenever an ad changes in a way that
could affect the buyer-visible PUBLISHED search result set:

- **status transitions** — any change that adds/removes an ad from search
  results (e.g. DRAFT→PUBLISHED, PUBLISHED→ARCHIVED/DELETED).
- **content edits** — title, description, category, city, price, listing
  purpose, or published_at changes that alter what or how ads match.
- **feature M2M edits** — adding or removing features on a visible ad.
- **account-state changes** — a user's ``is_declined`` flag, the only ``User``
  predicate in ``ListingsQuery.build_queryset``, changing (08-SRCH-005).

The version counter is embedded in every cache key built by
``build_search_cache_key``, so a single ``cache.incr`` makes all stale
entries unreachable without a global prefix wipe.

**Commit-timing asymmetry (deliberate).** The two ``Ad`` receivers bump the
version **inline, inside** the transaction: an ad change is a content edit
whose visibility follows the row, and the counter is monotonic, so a later
rollback only over-invalidates. The ``User`` account-state receiver instead
uses ``transaction.on_commit`` — retiring cache keys against an *uncommitted*
predicate is exactly wrong for a consent transition, where the next cached
read must observe the committed ``is_declined`` value. Do not copy the
``Ad`` receivers' inline shape into the ``User`` receiver.

Contrary to an earlier version of this docstring, ``post_save`` does **not**
fire after commit: both ``Ad`` receivers call ``bump_search_version()``
synchronously inside the transaction. Only the ``User`` receiver defers via
``on_commit``.

Best-effort: a cache backend failure is caught and logged for the inline
``Ad`` bumps — the DB save has already committed.
"""

import logging

from django.db import transaction
from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver

from apps.ads.models import Ad
from apps.core.enums import AdStatus
from apps.search.services.cache import bump_search_cache_version, bump_search_version
from apps.users.models import User

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

# ``User`` fields that participate in the buyer-visible ad-visibility
# predicate.  ``ListingsQuery.build_queryset`` contains exactly one ``User``
# predicate today — ``user__is_declined=False`` — so ``is_declined`` is the
# only field this receiver can justify bumping on (08-SRCH-005).  These are
# NOT reusable across the ``Ad`` receivers: those consult
# ``_SEARCH_RESULT_AFFECTING_STATUSES`` (``update_fields is None``) and
# ``_SEARCH_RELEVANT_FIELDS`` (the ``else`` branch), which are Ad fields.
_ACCOUNT_STATE_SEARCH_FIELDS = frozenset({"is_declined"})



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


@receiver(post_save, sender=User)
def bump_search_cache_on_account_state_change(
    sender, instance: User, **kwargs
):  # type: ignore[no-untyped-def]
    """Bump the search version when a user's account state affects visibility.

    ``ListingsQuery.build_queryset`` excludes a declined user's ads via
    ``user__is_declined=False``, so a change to that flag changes the
    buyer-visible result set. This is a declared invariant, not a per-call-site
    convention: without it a consent restoration leaves the seller's ads
    invisible to the cached search path until the version happens to move
    (08-SRCH-005).

    The bump is deferred with ``transaction.on_commit`` because retiring cache
    keys against an uncommitted predicate is exactly wrong for a consent
    transition — the next cached read must see the committed value. This is the
    deliberate asymmetry with the two ``Ad`` receivers, which bump inline.

    A full save (``update_fields`` is None) may change ``is_declined`` and so
    bumps; a targeted save bumps only when ``is_declined`` is among the updated
    fields.
    """
    update_fields = kwargs.get("update_fields")

    if update_fields is not None and not (
        _ACCOUNT_STATE_SEARCH_FIELDS & set(update_fields)
    ):
        return

    transaction.on_commit(bump_search_cache_version)
    logger.debug(
        "Deferred search content version bump for User %s account state change "
        "(update_fields=%s)",
        instance.pk,
        update_fields,
    )
