"""
Shared ad submission service — extracted verbatim from the bot handler's
``_update_and_moderate`` logic (QLT-001 Stage 1).

``submit_ad`` is now wired into both callers:
  * the bot handler's ``process_preview`` step, invoked via ``sync_to_async``
    (see ``ad_create.py``); and
  * the web edit view's ``ad_edit`` reactivation branch, which transitions
    an ``ARCHIVED`` ad back to ``ON_MODERATION`` (see ``edit.py``).

The currency-coercion divergence between the two call paths (Path 2) is
documented in the ``submit_ad`` function docstring.
"""

from __future__ import annotations

import logging
import os
from decimal import Decimal, InvalidOperation
from typing import Any

from django.conf import settings
from django.db import transaction
from pydantic import BaseModel, field_validator

from apps.ads.models import Ad
from apps.ads.services.images import AdImageService
from apps.core.enums import AdStatus, ThumbnailSizeStrEnum
from apps.currencies.enums import CurrencyCode
from apps.currencies.services.price_normalizer import PriceNormalizer
from apps.media.services.filesystem import move_staging_to_permanent
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


class AdEditInput(BaseModel):
    """DTO validating ad-edit POST data before any ORM write (QLT-004).

    Models the web-edit path's divergent semantics that ``SubmitAdInput``
    does not cover:

    - *Currency-fallback-on-invalid:* an invalid/blank ``price_currency``
      yields ``None``; the view then preserves the ad's current currency
      (matching the original ``except ValueError: pass`` behavior — see
      Block E design §"Currency-fallback-on-invalid").
    - *Invalid price → Free:* an unparseable ``price_amount`` yields
      ``Decimal("0")`` (matching the original ``except Exception`` fallback).

    TODO(QLT-004): Blank title/description still overwrite the ad's values
    (matching the original view logic where missing POST keys → ``""``).
    Consider rejecting blanks or requiring an explicit clear signal in a
    future pass.
    """

    title: str = ""
    description: str = ""
    price_amount: Decimal = Decimal("0")
    price_currency: CurrencyCode | None = None

    @field_validator("title", "description", mode="before")
    @classmethod
    def _strip_text(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v).strip()

    @field_validator("price_amount", mode="before")
    @classmethod
    def _coerce_price_amount(cls, v: Any) -> Decimal:
        """Empty or unparseable price → Decimal("0") (Free)."""
        if v is None or v == "":
            return Decimal("0")
        try:
            return Decimal(str(v))
        except (InvalidOperation, ValueError):
            return Decimal("0")

    @field_validator("price_currency", mode="before")
    @classmethod
    def _coerce_price_currency(cls, v: Any) -> CurrencyCode | None:
        """Invalid/blank currency → None (view preserves ad's current currency)."""
        if v is None or v == "":
            return None
        try:
            return CurrencyCode(str(v))
        except ValueError:
            return None


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

    # Promote staging files to permanent storage BEFORE the transaction.
    # Thumbnailing already wrote staging/<uuid>-*.jpg variants; this moves the
    # original + all thumbnails to permanent MEDIA_ROOT so AdImage rows (in the
    # TX below) reference permanent keys.  On DB rollback the permanent files
    # become unreferenced orphans reclaimed by the normal orphan sweep.
    move_staging_to_permanent(input.photos)

    # DB transaction: save + images + status transition
    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
        try:
            ad = Ad.objects.select_for_update().get(id=input.ad_id)
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
        # DB-001: auto_moderate is inside the outer atomic() so its inner
        # atomic() blocks become savepoints. If auto_moderate raises, the
        # entire submit_ad transaction rolls back — the ad stays DRAFT
        # (not committed in ON_MODERATION).
        from apps.moderation.services.auto_moderation import auto_moderate

        passed = auto_moderate(ad)
    if passed:
        return True, []
    else:
        return False, ["Ad failed moderation checks"]
