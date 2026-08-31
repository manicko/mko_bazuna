"""
Copy Ad service — creates a new draft ad based on an existing one.

Preserves category, description (all languages), address,
photos (new rows, same files), features, and contacts.
The seller must set a new purpose, price, title, and description.
"""

from django.db import transaction

from apps.ads.models import Ad, AdImage


def copy_ad(source_ad_id: int, seller_user_id: int) -> Ad:
    """Create a new draft ad copied from an existing one.

    Args:
        source_ad_id: ID of the ad to copy.
        seller_user_id: ID of the seller creating the copy.

    Returns:
        The new Ad instance in DRAFT status.

    Raises:
        Ad.DoesNotExist: if source_ad_id not found.
        PermissionError: if seller does not own the source ad.
    """
    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
        source = (
            Ad.objects.select_related("listing_purpose")
            .prefetch_related("features", "images")
            .get(id=source_ad_id)
        )

        if source.user_id != seller_user_id:
            raise PermissionError("Cannot copy another user's ad")

        new_ad = Ad(
            user_id=seller_user_id,
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
