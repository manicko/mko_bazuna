"""
Shared ad submission service — extracted from the bot handler's
``_update_and_moderate`` logic.

``submit_ad`` is now wired into both callers:
  * the bot handler's ``process_preview`` step, invoked via ``sync_to_async``
    (see ``ad_create.py``); and
  * the web edit view's ``ad_edit`` reactivation branch, which transitions
    an ``ARCHIVED`` ad back to ``ON_MODERATION`` (see ``edit.py``).

Currency coercion is the DTO's responsibility: Pydantic v2's native ``StrEnum``
coercion converts a valid ``"EUR"`` to ``CurrencyCode.EUR`` and rejects an
unknown currency via ``ValidationError`` at construction.  The bot flow passes
``data.get("price_currency")`` (``CurrencyCode`` or ``None`` from FSM state);
the web edit path pre-coerces to a valid ``CurrencyCode | None`` before
construction, so an unparseable form value preserves the ad's currency.
"""

from __future__ import annotations

import logging
import os
from decimal import Decimal, InvalidOperation
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from pydantic import field_validator

from apps.ads.models import Ad
from apps.ads.services.images import AdImageService
from apps.core.enums import AdStatus, ThumbnailSizeStrEnum
from apps.core.schemas import BaseInputModel
from apps.currencies.enums import CurrencyCode
from apps.currencies.services.price_normalizer import normalize_price_to_eur
from apps.media.schemas import SubmittedPhoto
from apps.media.services.filesystem import (
    STAGING_PREFIX,
    plan_staging_promotion,
    promote_media_files,
)
from apps.media.services.hash_service import FileHashService
from apps.media.services.thumbnails import ThumbnailService

logger = logging.getLogger(__name__)


class SubmitAdInput(BaseInputModel):
    """DTO bundling every field ``submit_ad`` needs to finalise and moderate an ad."""

    ad_id: int
    title_ru: str
    desc_ru: str
    category_id: int | None
    city_id: int | None
    price_amount: Decimal
    price_currency: CurrencyCode | None
    photos: list[SubmittedPhoto]
    user_id: int | None
    title_bs: str = ""
    desc_bs: str = ""
    title_en: str = ""
    desc_en: str = ""
    original_language: str | None = None
    listing_purpose_id: int | None = None
    feature_ids: list[int] | None = None
    listing_condition_id: int | None = None


class AdEditInput(BaseInputModel):
    """DTO validating ad-edit POST data before any ORM write (QLT-004).

    Models the web-edit path's divergent semantics that ``SubmitAdInput``
    does not cover:

    - *Currency-fallback-on-invalid:* an invalid/blank ``price_currency``
      yields ``None``; the view then preserves the ad's current currency
      (matching the original ``except ValueError: pass`` behavior — see
      Block E design §"Currency-fallback-on-invalid").
    - *Invalid price → Free:* an unparseable ``price_amount`` yields
      ``Decimal("0")`` (matching the original ``except Exception`` fallback).

    The PUBLISHED text-edit branch in ``ad_edit`` now delegates to
    ``submit_ad`` (QLT-004), passing a pre-coerced ``CurrencyCode | None`` so
    that ``None`` preserves the ad's current currency via Path A.

    NOTE: Blank title/description still overwrite the ad's values (matching the
    original view logic where missing POST keys → ``""``). Consider rejecting
    blanks or requiring an explicit clear signal in a future pass.
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
    ``normalize_price_to_eur`` using the current rate (BR-03) before saving.

    This is a synchronous function.  Callers that run in an async context
    (e.g. the bot handler) must wrap the call in ``sync_to_async``.

    ``price_currency`` is trusted directly from ``SubmitAdInput``: Pydantic v2's
    native ``StrEnum`` coercion already converted it to a ``CurrencyCode``
    (or ``None``) at DTO construction, so no defensive ``isinstance``/``str()``
    re-coercion is needed here.  When ``price_currency`` is ``None`` the ad's
    existing ``price_currency`` is preserved (web "keep-current" semantic; the
    bot flow never sends ``None`` per ``price.py`` FSM handlers).

    The ``False`` branch's error strings are user-facing on both surfaces (the
    bot's ``process_preview`` answers them verbatim; the web edit forms render
    them too), so they are wrapped in ``gettext_lazy`` at this source. Callers
    must ``str()`` the value before rendering — Django templates and aiogram
    both coerce a lazy proxy on use.

    Media promotion (03-DB-005): staged files are **key-rewritten** before the
    transaction by the pure ``plan_staging_promotion``; the physical move runs
    from ``transaction.on_commit`` so the file never appears in permanent
    storage — where the orphan sweep looks — before its ``AdImage`` row has
    committed.  A staged file that is missing raises before the transaction and
    becomes a recoverable seller message.
    """
    # Pre-flight: every staged file must still exist.  A reaped photo must
    # never become an AdImage row pointing at a file that is not there.  This
    # runs before any I/O or transaction, and makes the thumbnail loop's broad
    # except (below) unambiguously about *generation* failures.
    for photo in input.photos:
        if not photo.storage_key.startswith(STAGING_PREFIX):
            continue
        if not os.path.exists(
            os.path.join(settings.MEDIA_ROOT, photo.storage_key)
        ):
            return False, [
                str(
                    _(
                        "One of your photos is no longer available. "
                        "Please upload it again."
                    )
                )
            ]

    # Generate thumbnails BEFORE the DB transaction (filesystem I/O outside tx)
    # so a DB rollback does not leave filesystem and DB desynced.
    for photo in input.photos:
        try:
            original_path = os.path.join(settings.MEDIA_ROOT, photo.storage_key)
            with open(original_path, "rb") as f:
                photo_bytes = f.read()
            thumbnail_service = ThumbnailService(settings.MEDIA_ROOT)
            thumbnail_keys = thumbnail_service.generate_thumbnails(
                photo_bytes, photo.storage_key
            )
            photo.thumbnail_small = thumbnail_keys.get(ThumbnailSizeStrEnum.SMALL)
            photo.thumbnail_medium = thumbnail_keys.get(ThumbnailSizeStrEnum.MEDIUM)
            photo.thumbnail_large = thumbnail_keys.get(ThumbnailSizeStrEnum.LARGE)
        except Exception:
            logger.exception(
                "Failed to generate thumbnails for %s", photo.storage_key
            )
            photo.thumbnail_small = None
            photo.thumbnail_medium = None
            photo.thumbnail_large = None

    # Capture the staged originals before plan_staging_promotion rewrites the
    # fields: under deferred promotion the bytes are still at staging/<key>, so
    # the SHA-256 passed to AdImageService must come from there (03-DB-005).
    # The list keeps each digest aligned with ``input.photos`` by index.
    staged_digests: list[str | None] = [
        FileHashService.calculate_sha256(os.path.join(settings.MEDIA_ROOT, key))
        if (key := photo.storage_key).startswith(STAGING_PREFIX)
        else None
        for photo in input.photos
    ]

    # Key rewriting happens BEFORE the transaction because it is PURE — an
    # in-memory rewrite of SubmittedPhoto fields plus an existence check, with
    # no filesystem mutation.  The physical move is scheduled post-commit.
    permanent_keys = plan_staging_promotion(input.photos)

    # DB transaction: save + images + status transition
    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
        try:
            ad = Ad.objects.select_for_update().get(id=input.ad_id)
        except Ad.DoesNotExist:
            return False, [str(_("Ad not found"))]

        # Update ad fields — Russian remains the base content
        ad.title = input.title_ru
        ad.description = input.desc_ru
        ad.category_id = input.category_id
        ad.city_id = input.city_id
        ad.price_amount = input.price_amount

        # Currency is already coerced to CurrencyCode | None by SubmitAdInput
        # via Pydantic v2's native StrEnum coercion; trust the DTO directly.
        # None means "preserve the ad's current currency" (web "keep-current"
        # semantic); the bot flow always passes a valid CurrencyCode per
        # price.py FSM handlers, so this branch is a no-op for bots.
        currency = input.price_currency
        if currency is not None:
            ad.price_currency = currency.value

        # Price normalization (BR-03)
        normalize_price_to_eur(ad, input.price_amount, currency)

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

        # Create AdImage records with pre-generated thumbnails.  The digest of
        # the staged bytes was captured above (they are not at the row's
        # permanent key), so content dedup keeps working under deferred
        # promotion.
        for index, photo in enumerate(input.photos):
            AdImageService.create_or_skip(
                ad=ad,
                image=photo.storage_key,
                telegram_file_id=photo.telegram_file_id,
                position=photo.position,
                thumbnail_small=photo.thumbnail_small,
                thumbnail_medium=photo.thumbnail_medium,
                thumbnail_large=photo.thumbnail_large,
                sha256=staged_digests[index],
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

        # Schedule the filesystem move only after the owning rows commit.
        # Registered INSIDE the atomic block and AFTER the Ad.DoesNotExist
        # return, so a missing ad schedules no promotion.  The key list is
        # bound into the closure explicitly.
        transaction.on_commit(
            lambda keys=permanent_keys: promote_media_files(keys)
        )
    if passed:
        return True, []
    else:
        return False, [str(_("Ad failed moderation checks"))]
