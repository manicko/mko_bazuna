"""
Copy Ad service — creates a new draft ad based on an existing one.

Preserves category, description (all languages), address,
photos (new rows, same files), features, and contacts.
The seller must set a new purpose, price, title, and description.
"""

from django.db import IntegrityError, transaction

from apps.ads.models import Ad, AdImage
from apps.core.enums import AdStatus


def _build_ad_copy(source: Ad, seller_user_id: int) -> Ad:
    """Build an unsaved DRAFT copy of *source* owned by *seller_user_id*.

    The single-draft policy shared with ``create_draft_ad`` means ``status`` is
    always ``AdStatus.DRAFT``; the caller saves this instance.
    """
    return Ad(
        user_id=seller_user_id,
        status=AdStatus.DRAFT,
        category=source.category,
        city=source.city,
        # Copy all language variants
        title=source.title,
        title_en=source.title_en,
        title_bs=source.title_bs,
        description=source.description,
        description_en=source.description_en,
        description_bs=source.description_bs,
        original_language=source.original_language,
        # Copy listing purpose
        listing_purpose_id=source.listing_purpose_id,
    )


def copy_ad(source_ad_id: int, seller_user_id: int) -> Ad:
    """Create a new draft ad copied from an existing one.

    Single-draft policy (mirrors ``create_draft_ad``): the seller may hold at
    most one in-progress ``DRAFT``. Any existing ``DRAFT`` for the seller is
    deleted inside this transaction before the copy is created, so the copy
    replaces it rather than tripping the partial unique index
    ``uq_ads_single_draft_per_user``. Deleting inside the same transaction as
    the create means a failed create rolls the delete back, leaving the seller
    exactly as they were.

    Savepoint rationale: the create is wrapped in a nested
    ``transaction.atomic()`` — a SAVEPOINT — with the ``try`` *outside* it.
    That savepoint is what makes the ``IntegrityError`` below catchable: it
    clears ``needs_rollback`` and releases the server-side transaction, so the
    handler's first query runs on a healthy connection, while the delete and
    the retry stay in the outer transaction. If the ``try`` were placed inside
    the ``with``, ``__exit__`` would not yet have run when the handler
    executed and its first query would hit an already-aborted transaction.
    Do not "simplify" the savepoint away.

    Physical media deletion for a replaced draft is not done here: the
    ``AdImage`` ``pre_delete`` signal defers file removal to
    ``transaction.on_commit()``, so it happens after this transaction commits.
    That is correct only when the replaced draft shares no storage key with a
    surviving ad: images are copied by reusing the source keys (no file
    duplication), so a key still referenced by another ``AdImage`` is retained
    by the signal's existence check rather than deleted. Without that check,
    replacing a draft here would delete files the published source still uses.

    Args:
        source_ad_id: ID of the ad to copy.
        seller_user_id: ID of the seller creating the copy.

    Returns:
        The new Ad instance in DRAFT status.

    Raises:
        Ad.DoesNotExist: if source_ad_id not found.
        PermissionError: if seller does not own the source ad.
        IntegrityError: if ``uq_ads_single_draft_per_user`` still fires after
            the cleanup retry.
    """
    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
        source = (
            Ad.objects.select_related("listing_purpose")
            .prefetch_related("features", "images")
            .get(id=source_ad_id)
        )

        if source.user_id != seller_user_id:
            raise PermissionError("Cannot copy another user's ad")

        # Single-draft policy: replace the seller's existing DRAFT before
        # creating the copy. AdImage rows CASCADE-delete via the FK; orphaned
        # media files are reclaimed by the AdImage pre_delete ->
        # transaction.on_commit() path once this transaction commits.
        existing = Ad.objects.filter(
            user_id=seller_user_id, status=AdStatus.DRAFT
        )
        if existing.exists():
            existing.delete()

        # The inner atomic() is a SAVEPOINT: it lets the IntegrityError be
        # caught on a healthy connection (needs_rollback cleared, server
        # transaction released) while keeping the delete + retry in the outer
        # transaction. Without it the handler's first query would run against
        # an already-aborted transaction.
        try:
            with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
                new_ad = _build_ad_copy(source, seller_user_id)
                new_ad.save()
        except IntegrityError:
            # Race: a concurrent creator slipped through the check before the
            # unique index was enforced. Clean up and retry once.
            Ad.objects.filter(
                user_id=seller_user_id, status=AdStatus.DRAFT
            ).delete()
            new_ad = _build_ad_copy(source, seller_user_id)
            new_ad.save()

        # Copy features (M2M via through model)
        new_ad.features.set(source.features.all())

        # Copy images (new rows, same storage keys — no file duplication)
        for img in source.images.all():
            AdImage.objects.create(
                ad=new_ad,
                image=img.image,
                telegram_file_id=img.telegram_file_id,
                position=img.position,
                thumbnail_small=img.thumbnail_small,
                thumbnail_medium=img.thumbnail_medium,
                thumbnail_large=img.thumbnail_large,
            )

    return new_ad
