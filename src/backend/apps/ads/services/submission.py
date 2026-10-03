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
from enum import StrEnum
from typing import Any, NamedTuple

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
    reclaim_staged_keys,
)
from apps.media.services.hash_service import FileHashService
from apps.media.services.thumbnails import ThumbnailService
from apps.users.models import User
from apps.users.services.account_state import can_create_ad

logger = logging.getLogger(__name__)


class SubmitAdOutcome(StrEnum):
    """Business outcome of ``submit_ad``, used by callers to branch on cause.

    The enum houses **business** outcomes only.  A lock timeout
    (``OperationalError`` / SQLSTATE 55P03) is a transient system condition,
    not a business result, and is deliberately left as an exception that
    propagates to the handler's lock-timeout boundary (03-DB-004).
    """

    PUBLISHED = "published"
    MODERATION_FAILED = "moderation_failed"
    PHOTO_UNAVAILABLE = "photo_unavailable"
    DRAFT_GONE = "draft_gone"
    INVALID_TRANSITION = "invalid_transition"
    CONSENT_REQUIRED = "consent_required"


class SubmitAdResult(NamedTuple):
    """Typed result of ``submit_ad``.

    ``outcome`` is carried in its own field, never in a truthiness position:
    every ``StrEnum`` member is a non-empty string and therefore truthy, so
    folding the outcome into a ``passed``/``errors`` slot would make
    ``if passed:`` silently succeed for every failure outcome.
    """

    outcome: SubmitAdOutcome
    errors: list[str]


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


def _permanent_thumbnail_key(
    generated_key: str | None, permanent_keys: list[str]
) -> str | None:
    """Strip the staging prefix from a generated thumbnail key and queue it.

    ``plan_staging_promotion`` runs before the thumbnails are generated, so the
    newly written ``staging/<key>`` thumbnail files are not seen by its rewrite
    and would otherwise never be promoted. This applies the same prefix strip and
    adds the result to ``permanent_keys`` so it is moved post-commit.
    """
    if generated_key is None:
        return None
    permanent = generated_key.removeprefix(STAGING_PREFIX)
    if permanent not in permanent_keys:
        permanent_keys.append(permanent)
    return permanent


def submit_ad(input: SubmitAdInput) -> SubmitAdResult:
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

    Every business outcome is named by :class:`SubmitAdOutcome`: a missing
    draft is ``DRAFT_GONE`` (distinct from ``MODERATION_FAILED``), a reaped
    staged file is ``PHOTO_UNAVAILABLE``, a refused state-machine transition is
    ``INVALID_TRANSITION``, and a committed moderation pass is ``PUBLISHED``.
    The ``errors`` list carries the user-facing reason for the failure
    outcomes; its strings are wrapped in ``gettext_lazy`` at this source (the
    bot's ``process_preview`` and the web edit forms render them), so callers
    must ``str()`` the value before rendering.

    A lock timeout is **not** an outcome: ``OperationalError`` propagates to
    the caller's handler boundary (03-DB-004), exactly as before.

    Media promotion (03-DB-005): staged files are **key-rewritten** before the
    transaction by the pure ``plan_staging_promotion``; the physical move runs
    from ``transaction.on_commit`` so the file never appears in permanent
    storage — where the orphan sweep looks — before its ``AdImage`` row has
    committed.  A staged file that is missing raises before the transaction and
    becomes a recoverable seller message.
    """
    # Create-time storage-consent gate (06-PII-109). This is the FIRST statement:
    # it runs before any filesystem work, the staged-media plan, thumbnail
    # generation and ``transaction.atomic()``, so a never-consented seller
    # cannot have a single byte written or a row mutated. The seller is resolved
    # by pk; a missing user is ``DRAFT_GONE``'s business (the draft row cannot
    # exist without its owner), not this gate's — so an unresolved pk falls
    # through to the existing not-found handling rather than being reported as
    # a consent refusal.
    if input.user_id is not None:
        seller = User.objects.filter(id=input.user_id).first()
        if seller is not None and not can_create_ad(seller):
            return SubmitAdResult(
                SubmitAdOutcome.CONSENT_REQUIRED,
                [str(_("Please accept the personal data storage consent first."))],
            )

    # Capture each photo's staged key and read path BEFORE the plan rewrites the
    # staging keys in place.  Staged photos are read from ``staging/<key>`` and
    # keep the staging prefix on the generated thumbnails (stripped and queued
    # below); non-staging photos (seed data, web-edit fixtures) are read from and
    # generate against their permanent key, exactly as before.  Pure list build —
    # no I/O — so the plan's existence check is still the first filesystem touch.
    staged_keys: list[str | None] = [
        photo.storage_key if photo.storage_key.startswith(STAGING_PREFIX) else None
        for photo in input.photos
    ]
    read_paths: list[str] = [
        os.path.join(settings.MEDIA_ROOT, staged_key)
        if staged_key is not None
        else os.path.join(settings.MEDIA_ROOT, photo.storage_key)
        for photo, staged_key in zip(input.photos, staged_keys, strict=True)
    ]

    # Key rewriting happens BEFORE any I/O or transaction because it is PURE — an
    # in-memory rewrite of SubmittedPhoto fields plus an existence check, with no
    # filesystem mutation.  The physical move is scheduled post-commit.  A staged
    # file missing here (reaped after upload) raises FileNotFoundError, caught
    # below as a recoverable seller message: this is the ONE existence rule, and
    # running the plan first makes "file missing" impossible by construction for
    # the thumbnail loop and digest capture that follow, so their behaviour is
    # unambiguously about generation/read failures, not absence.
    try:
        permanent_keys = plan_staging_promotion(input.photos)
    except FileNotFoundError:
        return SubmitAdResult(
            SubmitAdOutcome.PHOTO_UNAVAILABLE,
            [
                str(
                    _(
                        "One of your photos is no longer available. "
                        "Please upload it again."
                    )
                )
            ],
        )

    # Generate thumbnails BEFORE the DB transaction (filesystem I/O outside tx)
    # so a DB rollback does not leave filesystem and DB desynced.  Staged photos
    # read the staged path captured above (the plan has already rewritten
    # ``photo.storage_key`` to the permanent key), and their generated thumbnail
    # keys carry the staging prefix — the plan ran before these files existed and
    # could not rewrite them, so they are stripped and queued for promotion.
    for photo, read_path, staged_key in zip(
        input.photos, read_paths, staged_keys, strict=True
    ):
        try:
            with open(read_path, "rb") as f:
                photo_bytes = f.read()
            thumbnail_service = ThumbnailService(settings.MEDIA_ROOT)
            generated = thumbnail_service.generate_thumbnails(
                photo_bytes, staged_key if staged_key is not None else photo.storage_key
            )
            if staged_key is not None:
                photo.thumbnail_small = _permanent_thumbnail_key(
                    generated.get(ThumbnailSizeStrEnum.SMALL), permanent_keys
                )
                photo.thumbnail_medium = _permanent_thumbnail_key(
                    generated.get(ThumbnailSizeStrEnum.MEDIUM), permanent_keys
                )
                photo.thumbnail_large = _permanent_thumbnail_key(
                    generated.get(ThumbnailSizeStrEnum.LARGE), permanent_keys
                )
            else:
                photo.thumbnail_small = generated.get(ThumbnailSizeStrEnum.SMALL)
                photo.thumbnail_medium = generated.get(ThumbnailSizeStrEnum.MEDIUM)
                photo.thumbnail_large = generated.get(ThumbnailSizeStrEnum.LARGE)
        except Exception:
            logger.exception(
                "Failed to generate thumbnails for %s", photo.storage_key
            )
            photo.thumbnail_small = None
            photo.thumbnail_medium = None
            photo.thumbnail_large = None

    # Capture the staged originals for the SHA-256 passed to AdImageService: under
    # deferred promotion the bytes are still at staging/<key>, so the digest must
    # come from the staged key captured above (03-DB-005).  The list keeps each
    # digest aligned with ``input.photos`` by index.
    staged_digests: list[str | None] = [
        FileHashService.calculate_sha256(
            os.path.join(settings.MEDIA_ROOT, staged_key)
        )
        if staged_key is not None
        else None
        for staged_key in staged_keys
    ]

    # DB transaction: save + images + status transition
    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
        try:
            ad = Ad.objects.select_for_update().get(id=input.ad_id)
        except Ad.DoesNotExist:
            return SubmitAdResult(
                SubmitAdOutcome.DRAFT_GONE, [str(_("Ad not found"))]
            )

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
        reclaimed_keys: list[str] = []
        for index, photo in enumerate(input.photos):
            created = AdImageService.create_or_skip(
                ad=ad,
                image=photo.storage_key,
                telegram_file_id=photo.telegram_file_id,
                position=photo.position,
                thumbnail_small=photo.thumbnail_small,
                thumbnail_medium=photo.thumbnail_medium,
                thumbnail_large=photo.thumbnail_large,
                sha256=staged_digests[index],
            )
            # A differing ``.image`` is exactly "not created": the offered key
            # was minted fresh by ``generate_storage_key()`` (uuid4, retried on
            # ``FileExistsError``), so no row can already carry it.  This is the
            # same proof that makes a defensive ``unreferenced_keys`` query here
            # pointless — the row was never created, so nothing can reference
            # the bytes.  Reading a *created* row as a skip would delete bytes a
            # live row references, which is why this compares keys rather than
            # testing truthiness.
            if created.image != photo.storage_key:
                reclaimed_keys.extend(photo.storage_keys())

        # Transition DRAFT -> ON_MODERATION (state machine requires this step).
        # A refusal (e.g. the row left DRAFT concurrently) is a business
        # outcome, not an exception: surface it to the caller as
        # INVALID_TRANSITION rather than letting the ValueError escape.
        try:
            ad.transition_to(AdStatus.ON_MODERATION)
        except ValueError:
            logger.warning(
                "Invalid transition submitting ad %s from status %s",
                input.ad_id,
                ad.status,
            )
            return SubmitAdResult(SubmitAdOutcome.INVALID_TRANSITION, [])

        # Delegate to shared auto-moderation service
        # Handles: banned_words, duplicate_title, all validations,
        # ModeratorActionLog, AnalyticsEvent (with enum member), status transitions
        # auto_moderate is inside the outer atomic() so its inner
        # atomic() blocks become savepoints. If auto_moderate raises, the
        # entire submit_ad transaction rolls back — the ad stays DRAFT
        # (not committed in ON_MODERATION).
        from apps.moderation.services.auto_moderation import auto_moderate

        passed = auto_moderate(ad)

        if reclaimed_keys:
            # In-place slice: the promotion closure holds THIS list object via
            # ``lambda keys=permanent_keys``, so rebinding would leave it holding
            # the unpruned list and promote the orphans.  Pruning also keeps the
            # contract truthful when a reclaim FAILS — the bytes then stay in
            # ``staging/`` for TTL reclamation instead of becoming permanent
            # orphans.
            reclaimed = set(reclaimed_keys)
            permanent_keys[:] = [key for key in permanent_keys if key not in reclaimed]

            # Registered AFTER auto_moderate, immediately BEFORE promotion: the
            # DRAFT_GONE / INVALID_TRANSITION paths are early *returns*, so the
            # atomic block still commits and any hook registered above would fire
            # — deleting the skipped file out from under the seller's re-confirm.
            # One registration per submission, so every reclaim precedes every
            # promotion and a single failing key cannot abort the rest.
            transaction.on_commit(
                lambda keys=list(reclaimed_keys): reclaim_staged_keys(keys)
            )

        # Schedule the filesystem move only after the owning rows commit.
        # Registered INSIDE the atomic block and AFTER the Ad.DoesNotExist
        # return, so a missing ad schedules no promotion.  The key list is
        # bound into the closure explicitly.
        transaction.on_commit(
            lambda keys=permanent_keys: promote_media_files(keys)
        )
    if passed:
        return SubmitAdResult(SubmitAdOutcome.PUBLISHED, [])
    else:
        return SubmitAdResult(
            SubmitAdOutcome.MODERATION_FAILED, [str(_("Ad failed moderation checks"))]
        )
