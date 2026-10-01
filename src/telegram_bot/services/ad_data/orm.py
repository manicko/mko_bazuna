"""ORM helper functions for the Telegram bot ad-creation service.

All DB access is wrapped in ``sync_to_async`` to keep the bot's event loop
responsive (bot -> backend direction). This module may import from ``apps.*``
but ``apps.*`` must never import ``telegram_bot.*``.
"""

import logging

from asgiref.sync import sync_to_async
from django.db import IntegrityError, OperationalError, transaction
from django.utils import timezone

from apps.ads.models import Ad
from apps.categories.models import Category
from apps.core.enums import AdStatus
from apps.core.utils.db_lock_timeout import is_lock_timeout
from apps.locations.models import City
from apps.media.services.filesystem import delete_photo

logger = logging.getLogger(__name__)

__all__ = [
    "create_draft_ad",
    "_get_ad_status",
    "delete_draft",
    "touch_draft",
    "search_categories",
    "get_city_by_name",
    "get_all_cities",
    "get_category",
    "get_city",
]


# ---------------------------------------------------------------------------
# ORM helpers (sync_to_async)
# ---------------------------------------------------------------------------


async def create_draft_ad(user_id: int) -> Ad:
    """Create a draft ad row, ensuring at most one in-progress DRAFT per user.

    If an existing DRAFT is found for the user, it is deleted first (with its
    AdImage rows CASCADE-deleted). The partial unique index
    ``uq_ads_single_draft_per_user`` fires ``IntegrityError`` as a backstop
    for any concurrent race that slips past this check; on such a race we
    retry once after cleaning up.
    """

    @sync_to_async
    def _create() -> Ad:
        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
            # Remove any pre-existing in-progress DRAFT for this user before
            # creating a fresh one (Option A: delete + recreate). AdImage rows
            # CASCADE-delete via the FK. Orphaned media files are reclaimed by
            # sweep_orphaned_media.
            existing = Ad.objects.filter(user_id=user_id, status=AdStatus.DRAFT)
            if existing.exists():
                existing.delete()

            # The inner atomic() is a SAVEPOINT: on error it issues ROLLBACK TO
            # SAVEPOINT and clears needs_rollback, so the IntegrityError below
            # is caught on a healthy connection (the outer BEGIN stays open)
            # while the delete + retry remain in the outer transaction. Without
            # it the handler's first query would run against an already-aborted
            # transaction.
            try:
                with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
                    return Ad.objects.create(user_id=user_id, status=AdStatus.DRAFT)
            except IntegrityError:
                # Race: a concurrent create_draft_ad slipped through the above
                # check before the unique index was enforced. Clean up and retry.
                Ad.objects.filter(user_id=user_id, status=AdStatus.DRAFT).delete()
                return Ad.objects.create(user_id=user_id, status=AdStatus.DRAFT)

    return await _create()


async def _get_ad_status(ad_id: int) -> AdStatus | None:
    """Return the current ``AdStatus`` for *ad_id*, or ``None`` if it doesn't exist.

    Uses ``sync_to_async`` to perform the lightweight DB lookup off
    the bot's event loop, mirroring the TX-then-Filesystem pattern used
    throughout this module.
    """

    @sync_to_async
    def _get() -> AdStatus | None:
        status_str = (
            Ad.objects.filter(id=ad_id).values_list("status", flat=True).first()
        )
        if status_str is None:
            return None
        return AdStatus(status_str)

    return await _get()


async def touch_draft(ad_id: int) -> None:
    """Refresh a DRAFT ad's ``updated_at`` so the idle-timeout sweep keeps it alive.

    This is the dialog heartbeat for finding 03-DB-003: ``sweep_drafts`` reaps a
    ``DRAFT`` once it has had no interaction for 30 minutes, measured on
    ``Ad.updated_at``.  Every handler registered on an ``AdCreateForm`` state
    calls this on entry, so a dialog that stays interactive is never reaped
    however long it takes.

    The write MUST be a single-column ``QuerySet.update()``, never a full
    ``save()``.  ``auto_now`` is a ``Model.save()`` pre-save hook only;
    ``QuerySet.update()`` emits raw SQL and never fires it.  A full ``save()``
    from a stale in-memory ``Ad`` rewrites all 31 columns and was measured to
    clobber a concurrent ``submit_ad``: a stale ``title`` plus ``status='draft'``
    written over a just-published ad, while ``published_at`` stays set — a row
    that is simultaneously DRAFT (so the sweep deletes it 30 minutes later) and
    already gone from the site.  The ``CHECK`` constraints do not stop it.

    The ``status=AdStatus.DRAFT`` filter is a second, independent guarantee: once
    the ad leaves DRAFT the predicate matches 0 rows, so this can never resurrect
    or revert a published ad.

    Fail-soft: a lock timeout (SQLSTATE 55P03) is transient contention — the
    heartbeat can wait behind ``submit_ad``'s row lock — not a dialog failure.
    A missed heartbeat only degrades that one dialog to the pre-fix 30-minute
    creation-age behaviour; it must never cost the seller their step.
    """

    @sync_to_async
    def _touch() -> None:
        try:
            Ad.objects.filter(id=ad_id, status=AdStatus.DRAFT).update(
                updated_at=timezone.now()
            )
        except OperationalError as exc:
            if not is_lock_timeout(exc):
                raise
            logger.warning(
                "Lock timeout touching draft ad %s; skipping heartbeat", ad_id
            )

    await _touch()


async def delete_draft(ad_id: int) -> None:
    """Delete a draft ad and clean up its photo files."""
    @sync_to_async
    def _delete() -> None:
        try:
            ad = Ad.objects.get(id=ad_id, status=AdStatus.DRAFT)
        except Ad.DoesNotExist:
            return

        # Collect storage keys inside the transaction (DB-only read),
        # then delete the Ad row (DB-first). Filesystem deletion happens
        # only after the transaction commits — TX-then-Filesystem pattern
        # mirroring soft_delete_user_ads and sweep_drafts.
        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
            storage_keys = [
                key for img in ad.images.all() for key in img.storage_keys()
            ]
            ad.delete()

        # Delete physical media files after the transaction commits.
        # Filesystem deletions inside transaction.atomic() cannot be
        # rolled back, so a DB rollback would orphan DB rows pointing to
        # already-deleted files.
        for key in storage_keys:
            delete_photo(key)

    await _delete()


async def search_categories(keyword: str) -> list[Category]:
    """Search categories by keyword."""

    @sync_to_async
    def _search() -> list[Category]:
        return list(
            Category.objects.filter(name__icontains=keyword, is_active=True)[:5]
        )

    return await _search()


async def get_city_by_name(name: str) -> City | None:
    """Get city by exact name."""

    @sync_to_async
    def _get() -> City | None:
        try:
            return City.objects.get(name__iexact=name)
        except City.DoesNotExist:
            return None

    return await _get()


async def get_all_cities() -> list[City]:
    """Get all cities."""

    @sync_to_async
    def _get() -> list[City]:
        return list(City.objects.all())

    return await _get()


async def get_category(category_id: int) -> Category | None:
    """Get category by ID."""

    @sync_to_async
    def _get() -> Category | None:
        try:
            return Category.objects.get(id=category_id)
        except Category.DoesNotExist:
            return None

    return await _get()


async def get_city(city_id: int) -> City | None:
    """Get city by ID."""

    @sync_to_async
    def _get() -> City | None:
        try:
            return City.objects.get(id=city_id)
        except City.DoesNotExist:
            return None

    return await _get()
