"""
Inert ad submission service — verbatim extraction of the bot handler's
``_update_and_moderate`` logic (QLT-001 Stage 1).

No callers are wired yet.  ``submit_ad`` exists solely to provide a
shared, DTO-accepting orchestration seam that both the bot handler and the
web edit view will adopt in subsequent stages (A2, A4).
"""

from __future__ import annotations

import logging
import os
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import transaction
from pydantic import BaseModel

from apps.ads.models import Ad
from apps.ads.services.images import AdImageService
from apps.core.enums import AdStatus, ThumbnailSizeStrEnum
from apps.currencies.enums import CurrencyCode
from apps.currencies.services.price_normalizer import PriceNormalizer
from apps.media.services.thumbnails import ThumbnailService

logger = logging.getLogger(__name__)


class SubmitAdInput(BaseModel):
    """DTO bundling every field ``submit_ad`` needs to finalise and moderate an ad."""

    ad_id: int
    title_ru: str
    desc_ru: str
    category_id: int | None
    city_id: int | None
    price_amount: Decimal
    price_currency: CurrencyCode | None
    photos: list[dict[str, Any]]
    user_id: int | None
    title_bs: str = ""
    desc_bs: str = ""
    title_en: str = ""
    desc_en: str = ""
    original_language: str | None = None
    listing_purpose_id: int | None = None
    feature_ids: list[int] | None = None
    listing_condition_id: int | None = None


def submit_ad(input: SubmitAdInput) -> tuple[bool, list[str]]:
    """Update ad with multi-language content, create images, and delegate to auto_moderate.

    ``price_amount``/``price_currency`` become the source of truth; when
    ``price_currency`` is present ``price_normalized_eur`` is computed via
    ``PriceNormalizer`` using the current rate (BR-03) before saving.

    This is a synchronous function.  Callers that run in an async context
    (e.g. the bot handler) must wrap the call in ``sync_to_async``.

    .. note::

        **Currency coercion divergence (QLT-001 Stage 3 / Path 2):**
        This function defensively coerces ``CurrencyCode | str`` inputs,
        falling back to ``None`` on ``ValueError`` (inherited from the bot
        handler's original ``update_ad_and_moderate``).  The web edit view
        pre-validates currency at the view layer (preserving the user's
        current currency on invalid form input) and passes a valid
        ``CurrencyCode | None`` via ``SubmitAdInput``, so the coercion is a
        no-op for the edit path.  Do not remove this defensive check without
        verifying the bot flow still guards against raw-string currencies.
    """
    try:
        ad = Ad.objects.get(id=input.ad_id)
    except Ad.DoesNotExist:
        return False, ["Ad not found"]

    # Update ad fields — Russian remains the base content
    ad.title = input.title_ru
    ad.description = input.desc_ru
    ad.category_id = input.category_id
    ad.city_id = input.city_id
    ad.price_amount = input.price_amount

    # Currency coercion
    currency: CurrencyCode | None = None
    if input.price_currency is not None:
        try:
            currency = (
                input.price_currency
                if isinstance(input.price_currency, CurrencyCode)
                else CurrencyCode(str(input.price_currency))
            )
        except ValueError:
            logger.warning(
                "Invalid price_currency %r for ad %s", input.price_currency, input.ad_id
            )
    ad.price_currency = currency.value if currency else None

    # Price normalization (BR-03)
    if currency is not None:
        try:
            ad.price_normalized_eur = PriceNormalizer().normalize_to_eur(
                input.price_amount, currency
            )
        except Exception:
            logger.exception("Failed to normalize price for ad %s", input.ad_id)
            ad.price_normalized_eur = None
    else:
        ad.price_normalized_eur = None

    # Multi-language fields
    if input.title_bs:
        ad.title_bs = input.title_bs
    if input.desc_bs:
        ad.description_bs = input.desc_bs
    if input.title_en:
        ad.title_en = input.title_en
    if input.desc_en:
        ad.description_en = input.desc_en
    if input.original_language:
        ad.original_language = input.original_language

    # Listing purpose
    if input.listing_purpose_id:
        ad.listing_purpose_id = input.listing_purpose_id

    # Generate thumbnails BEFORE the DB transaction (filesystem I/O outside tx)
    # so a DB rollback does not leave filesystem and DB desynced.
    for photo in input.photos:
        try:
            original_path = os.path.join(settings.MEDIA_ROOT, photo["storage_key"])
            with open(original_path, "rb") as f:
                photo_bytes = f.read()
            thumbnail_service = ThumbnailService(settings.MEDIA_ROOT)
            thumbnail_keys = thumbnail_service.generate_thumbnails(
                photo_bytes, photo["storage_key"]
            )
            photo["thumbnail_small"] = thumbnail_keys.get(ThumbnailSizeStrEnum.SMALL)
            photo["thumbnail_medium"] = thumbnail_keys.get(ThumbnailSizeStrEnum.MEDIUM)
            photo["thumbnail_large"] = thumbnail_keys.get(ThumbnailSizeStrEnum.LARGE)
        except Exception:
            logger.exception(
                "Failed to generate thumbnails for %s", photo["storage_key"]
            )
            photo["thumbnail_small"] = None
            photo["thumbnail_medium"] = None
            photo["thumbnail_large"] = None

    # DB transaction: save + images + status transition
    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
        ad.listing_condition_id = input.listing_condition_id
        ad.save()

        # Save features (M2M via through model)
        if input.feature_ids is not None:
            ad.features.set(input.feature_ids)

        # Create AdImage records with pre-generated thumbnails
        for photo in input.photos:
            AdImageService.create_or_skip(
                ad=ad,
                image=photo["storage_key"],
                telegram_file_id=photo["telegram_file_id"],
                position=photo["position"],
                thumbnail_small=photo.get("thumbnail_small"),
                thumbnail_medium=photo.get("thumbnail_medium"),
                thumbnail_large=photo.get("thumbnail_large"),
            )

        # Transition DRAFT -> ON_MODERATION (state machine requires this step)
        ad.transition_to(AdStatus.ON_MODERATION)

    # Delegate to shared auto-moderation service
    # Handles: banned_words, duplicate_title, all validations,
    # ModeratorActionLog, AnalyticsEvent (with enum member), status transitions
    from apps.moderation.services.auto_moderation import auto_moderate

    passed = auto_moderate(ad)
    if passed:
        return True, []
    else:
        return False, ["Ad failed moderation checks"]
