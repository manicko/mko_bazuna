"""
Tests for the ``submit_ad`` shared submission service (QLT-001 Stage 1).

Verifies DB-001: ``auto_moderate`` runs inside ``submit_ad``'s
``transaction.atomic()`` block so that a failure in auto-moderation
rolls back the entire submission (ad stays DRAFT, not ON_MODERATION).
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.cache import cache
from pydantic import ValidationError

from apps.ads.models import Ad
from apps.ads.services.submission import (
    AdEditInput,
    SubmitAdInput,
    SubmitAdOutcome,
    SubmitAdResult,
    submit_ad,
)
from apps.core.enums import AdStatus
from apps.currencies.enums import CurrencyCode
from apps.currencies.models import ExchangeRate
from conftest import create_test_ad, make_user

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.integration,
]


@pytest.fixture(autouse=True)
def _seed_eur_rate():
    """Ensure the EUR exchange rate exists for PriceNormalizer.

    With ``transaction=True`` tests, the session-scoped ``load_exchange_rates``
    rows are truncated after each test, so we re-create the EUR rate per test.
    Also clears the Django cache so PriceNormalizer queries the DB rather than
    a stale cached rate from a prior test.
    """
    cache.clear()
    ExchangeRate.objects.update_or_create(
        currency=CurrencyCode.EUR.value,
        defaults={
            "rate_to_eur": "1.0",
            "effective_date": "2026-08-22",
            "source": "manual_seed",
            "is_current": True,
        },
    )


def _make_input(ad: Ad, *, ad_id: int | None = None) -> SubmitAdInput:
    """Build a ``SubmitAdInput`` for *ad* with minimal valid fields.

    ``ad_id`` overrides the row id when the target row no longer exists (the
    deleted-draft path), while the remaining fields still come from *ad*.
    """
    return SubmitAdInput(
        ad_id=ad.id if ad_id is None else ad_id,
        title_ru="Test Title",
        desc_ru="Test description text",
        category_id=ad.category_id,
        city_id=ad.city_id,
        price_amount=Decimal("100"),
        price_currency=CurrencyCode.EUR,
        photos=[],
        user_id=ad.user_id,
    )


# ---------------------------------------------------------------------------
# DB-001: transaction rollback when auto_moderate raises
# ---------------------------------------------------------------------------


def test_submit_ad_rolls_back_when_auto_moderate_raises(
    seller, category, city
) -> None:
    """When ``auto_moderate`` raises, the entire ``submit_ad`` transaction
    rolls back and the ad remains DRAFT.

    Because ``auto_moderate`` runs inside ``submit_ad``'s
    ``transaction.atomic()`` block (DB-001 fix), an exception propagates to
    the caller and undoes ``ad.save()`` / ``transition_to(ON_MODERATION)``.
    In the real bot path there is no enclosing transaction, so the atomic
    block is a real commit boundary; the rollback is total.
    """
    ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)

    with patch(
        "apps.moderation.services.auto_moderation.auto_moderate",
        side_effect=RuntimeError("Trust calculator failure"),
    ):
        with pytest.raises(RuntimeError, match="Trust calculator failure"):
            submit_ad(_make_input(ad))

    ad.refresh_from_db()
    assert ad.status == AdStatus.DRAFT


def test_submit_ad_commit_when_auto_moderate_passes(
    seller, category, city
) -> None:
    """When ``auto_moderate`` returns ``True``, the transaction commits and the
    ad reaches ``ON_MODERATION``.

    The mock bypasses the real ``_pass_moderation`` (which would set
    ``PUBLISHED``), so the ad stays at ``ON_MODERATION`` — the state set by
    ``transition_to`` inside the committed transaction. ``submit_ad`` returns
    the ``PUBLISHED`` outcome.
    """
    ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)

    with patch(
        "apps.moderation.services.auto_moderation.auto_moderate",
        return_value=True,
    ) as mock_moderate:
        result = submit_ad(_make_input(ad))

    assert result.outcome is SubmitAdOutcome.PUBLISHED
    assert result.errors == []
    mock_moderate.assert_called_once()

    ad.refresh_from_db()
    assert ad.status == AdStatus.ON_MODERATION


# ---------------------------------------------------------------------------
# Interleaving B: a staged file reaped before submission is recoverable
# ---------------------------------------------------------------------------


def test_missing_staged_file_reports_a_recoverable_error(
    seller, category, city, tmp_path
) -> None:
    """A reaped staged photo yields a recoverable error, never a photo-less ad.

    Interleaving B, exercised end to end through ``submit_ad``.  The staging
    file was reclaimed (e.g. by the 2 h TTL) before the seller confirmed.  The
    pre-flight existence check must catch it *before* the transaction opens and
    return ``(False, [<recoverable message>])`` — strictly better than the old
    behaviour, which rewrote the key unconditionally and committed an
    ``AdImage`` row pointing at a file that never existed.

    Hosted here (rather than in the bot's ``TestSubmitAdStagingMove``) because
    this module's ``submit_ad`` cases already run under
    ``django_db(transaction=True)`` and need no async wrapper; the pre-flight
    return is observed without converting an unrelated class.
    """
    from django.test import override_settings

    from apps.ads.models import AdImage
    from apps.media.services.filesystem import STAGING_PREFIX

    ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)

    storage_key = f"{STAGING_PREFIX}reaped.jpg"
    photos = [{"storage_key": storage_key, "telegram_file_id": "AgADBQ", "position": 0}]
    payload = SubmitAdInput(
        ad_id=ad.id,
        title_ru="Title",
        desc_ru="Description",
        category_id=ad.category_id,
        city_id=ad.city_id,
        price_amount=Decimal("100"),
        price_currency=CurrencyCode.EUR,
        photos=photos,
        user_id=ad.user_id,
    )

    # The staged file is absent — the photo was reaped before submission.
    with override_settings(MEDIA_ROOT=str(tmp_path)):
        result = submit_ad(payload)

    assert result.outcome is SubmitAdOutcome.PHOTO_UNAVAILABLE
    assert len(result.errors) == 1
    assert "photo" in result.errors[0].lower()
    assert "upload" in result.errors[0].lower()

    # No AdImage row and no rewritten key.
    assert AdImage.objects.filter(ad=ad).count() == 0
    assert payload.photos[0].storage_key == storage_key
    ad.refresh_from_db()
    assert ad.status == AdStatus.DRAFT


# ---------------------------------------------------------------------------
# Parity test: submit_ad delegates price normalization to the shared utility
# (10-QLT-001 DRY invariant — closes V-09 test gap)
# ---------------------------------------------------------------------------


def test_submit_ad_price_normalization_delegates_to_shared_utility(
    seller, category, city
) -> None:
    """``submit_ad`` invokes the shared ``normalize_price_to_eur`` utility
    (patched at the ``apps.ads.services.submission`` call-site namespace)
    during a successful submission with a currency present.

    The ``ad`` passed to the utility is fetched fresh inside ``submit_ad``'s
    transaction — assertions verify by ``pk`` rather than object identity.
    """
    ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)

    with patch(
        "apps.moderation.services.auto_moderation.auto_moderate",
        return_value=True,
    ):
        with patch(
            "apps.ads.services.submission.normalize_price_to_eur"
        ) as mock_normalizer:
            result = submit_ad(_make_input(ad))

    assert result.outcome is SubmitAdOutcome.PUBLISHED
    assert result.errors == []

    mock_normalizer.assert_called_once()
    call_args = mock_normalizer.call_args
    assert call_args.args[0].pk == ad.pk
    assert call_args.args[1] == Decimal("100")
    assert call_args.args[2] == CurrencyCode.EUR


# ---------------------------------------------------------------------------
# SubmitAdInput currency coercion (Pydantic v2 native StrEnum)
# ---------------------------------------------------------------------------


def test_submit_ad_input_coerces_valid_currency_string() -> None:
    """A raw ``"EUR"`` string passed to ``SubmitAdInput`` is coerced to
    ``CurrencyCode.EUR`` by Pydantic v2's native ``StrEnum`` coercion, so
    ``submit_ad`` can trust ``input.price_currency`` directly.
    """
    dto = SubmitAdInput(
        ad_id=1,
        title_ru="Test Title",
        desc_ru="Test description text",
        category_id=None,
        city_id=None,
        price_amount=Decimal("100"),
        price_currency="EUR",
        photos=[],
        user_id=None,
    )
    assert dto.price_currency is CurrencyCode.EUR


def test_submit_ad_input_rejects_invalid_currency_string() -> None:
    """An unknown currency string raises ``ValidationError`` at DTO
    construction — it is never silently coerced to ``None``, so the removed
    ``except ValueError`` fallback in ``submit_ad`` could never have fired.
    """
    with pytest.raises(ValidationError) as exc_info:
        SubmitAdInput(
            ad_id=1,
            title_ru="Test Title",
            desc_ru="Test description text",
            category_id=None,
            city_id=None,
            price_amount=Decimal("100"),
            price_currency="XYZ",
            photos=[],
            user_id=None,
        )
    assert exc_info.value.errors()[0]["loc"] == ("price_currency",)


# ---------------------------------------------------------------------------
# Extra-field rejection (CC-2: extra="forbid" on input DTOs)
# ---------------------------------------------------------------------------


def test_submit_ad_input_rejects_unknown_key() -> None:
    """An unknown key on ``SubmitAdInput`` raises ``ValidationError``."""
    with pytest.raises(ValidationError):
        SubmitAdInput(
            ad_id=1,
            title_ru="Test Title",
            desc_ru="Test description text",
            category_id=None,
            city_id=None,
            price_amount=Decimal("100"),
            price_currency=CurrencyCode.EUR,
            photos=[],
            user_id=None,
            rogue="x",
        )


def test_ad_edit_input_rejects_unknown_key() -> None:
    """An unknown key on ``AdEditInput`` raises ``ValidationError``.

    Regression guard for the producer fix: the web edit view filters
    ``request.POST`` to declared fields so that ``csrfmiddlewaretoken`` /
    ``reactivate`` do not trip ``extra="forbid"``.
    """
    with pytest.raises(ValidationError):
        AdEditInput(
            title="Test Title",
            description="Test description text",
            rogue="x",
        )


def test_ad_edit_input_accepts_declared_fields_only() -> None:
    """``AdEditInput`` validates cleanly when only declared fields are passed."""
    dto = AdEditInput(title="Test Title", description="Test description text")
    assert dto.title == "Test Title"
    assert dto.description == "Test description text"


# ---------------------------------------------------------------------------
# SubmitAdInput photo validation (10-QLT-008: SubmittedPhoto sub-model)
# ---------------------------------------------------------------------------


def test_submit_ad_input_rejects_photo_missing_storage_key() -> None:
    """A photo dict missing the required ``storage_key`` raises ``ValidationError``
    at ``SubmitAdInput`` construction — before any DB write or filesystem I/O.

    Pydantic v2 coerces each dict in ``photos`` into a ``SubmittedPhoto`` and
    rejects the payload when ``storage_key`` is absent.
    """
    with pytest.raises(ValidationError) as exc_info:
        SubmitAdInput(
            ad_id=1,
            title_ru="Test Title",
            desc_ru="Test description text",
            category_id=None,
            city_id=None,
            price_amount=Decimal("100"),
            price_currency=CurrencyCode.EUR,
            photos=[{"position": 0}],
            user_id=None,
        )
    errors = exc_info.value.errors()
    assert errors[0]["loc"] == ("photos", 0, "storage_key")
    assert errors[0]["type"] == "missing"


def test_submit_ad_input_accepts_valid_photo_dict() -> None:
    """A well-formed photo dict is coerced to a ``SubmittedPhoto`` instance
    with ``thumbnail_*`` defaults of ``None`` and ``position`` defaulted to 0."""
    from apps.media.schemas import SubmittedPhoto

    dto = SubmitAdInput(
        ad_id=1,
        title_ru="Test Title",
        desc_ru="Test description text",
        category_id=None,
        city_id=None,
        price_amount=Decimal("100"),
        price_currency=CurrencyCode.EUR,
        photos=[
            {"storage_key": "abc123.jpg", "telegram_file_id": "AgADBQ", "position": 2}
        ],
        user_id=None,
    )
    photo = dto.photos[0]
    assert isinstance(photo, SubmittedPhoto)
    assert photo.storage_key == "abc123.jpg"
    assert photo.telegram_file_id == "AgADBQ"
    assert photo.position == 2
    assert photo.thumbnail_small is None
    assert photo.thumbnail_medium is None
    assert photo.thumbnail_large is None



# ---------------------------------------------------------------------------
# AD-016: named outcomes — DRAFT_GONE is distinguishable from a content failure
# ---------------------------------------------------------------------------


def test_submit_ad_deleted_draft_returns_draft_gone(
    seller, category, city
) -> None:
    """A deleted/absent draft yields the ``DRAFT_GONE`` outcome.

    Closes the untested ``(False, ["Ad not found"])`` branch: before AD-016 the
    caller could not tell "the draft is gone" from a real moderation failure.
    The draft is created and then deleted, so the row is genuinely absent (the
    reaped-draft / concurrent-``/post`` path).
    """
    ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)
    ad_id = ad.id
    ad.delete()

    result = submit_ad(_make_input(ad, ad_id=ad_id))

    assert isinstance(result, SubmitAdResult)
    assert result.outcome is SubmitAdOutcome.DRAFT_GONE
    assert result.outcome is not SubmitAdOutcome.MODERATION_FAILED


def test_submit_ad_moderation_failure_returns_moderation_failed(
    seller, category, city
) -> None:
    """A genuine content failure yields ``MODERATION_FAILED``, distinct from
    ``DRAFT_GONE``.  The two causes must never collapse onto one outcome.
    """
    ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)

    with patch(
        "apps.moderation.services.auto_moderation.auto_moderate",
        return_value=False,
    ):
        result = submit_ad(_make_input(ad))

    assert result.outcome is SubmitAdOutcome.MODERATION_FAILED
    assert result.outcome is not SubmitAdOutcome.DRAFT_GONE
    assert result.errors == ["Ad failed moderation checks"]


def test_submit_ad_operational_error_propagates_as_exception(
    seller, category, city
) -> None:
    """A lock timeout stays an **exception**, never an outcome member.

    03-DB-004 owns the handler-level lock-timeout boundary; folding
    ``OperationalError`` into ``SubmitAdOutcome`` would make that boundary
    double-handle the condition.  ``submit_ad`` must let it propagate.
    """
    from django.db import OperationalError

    ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)

    with patch(
        "apps.moderation.services.auto_moderation.auto_moderate",
        side_effect=OperationalError("canceling statement due to lock timeout"),
    ):
        with pytest.raises(OperationalError):
            submit_ad(_make_input(ad))


def test_submit_ad_invalid_transition_returns_outcome_not_raises(
    seller, category, city
) -> None:
    """A refused state-machine transition is a **business outcome**.

    ``transition_to`` raises ``ValueError`` when the target is not allowed from
    the row's current status.  ``submit_ad`` must return
    ``INVALID_TRANSITION`` rather than let it escape (the state machine's
    business refusal is not an infrastructure fault).  Trap 1 guard: the
    outcome is carried in its own field, so a caller can branch on it even
    though every ``StrEnum`` member is truthy.
    """
    ad = create_test_ad(seller, category, city, status=AdStatus.REJECTED)

    with patch(
        "apps.moderation.services.auto_moderation.auto_moderate",
        return_value=True,
    ):
        result = submit_ad(_make_input(ad))

    assert result.outcome is SubmitAdOutcome.INVALID_TRANSITION
    assert result.errors == []
    # The row was untouched: REJECTED is terminal, so no transition happened.
    ad.refresh_from_db()
    assert ad.status == AdStatus.REJECTED


# ---------------------------------------------------------------------------
# 07-MEDIA-002: reclaim the staged bytes of a skipped duplicate upload
# ---------------------------------------------------------------------------


def _make_jpeg_bytes() -> bytes:
    """Return minimal decodable JPEG bytes for the real thumbnail pipeline."""
    import io

    from PIL import Image

    image = Image.new("RGB", (800, 600), color=(64, 128, 192))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=95)
    return buffer.getvalue()


def _stage_photos(media_root, photos: list[tuple[str, int]]):
    """Write staged bytes for each ``(key, position)`` and build photo dicts.

    All photos share byte-identical content so the second is a content
    duplicate of the first under per-ad dedup.
    """
    from apps.media.services.filesystem import STAGING_PREFIX

    photo_bytes = _make_jpeg_bytes()
    staging_dir = media_root / STAGING_PREFIX
    staging_dir.mkdir(parents=True, exist_ok=True)

    dicts = []
    for key, position in photos:
        (staging_dir / key).write_bytes(photo_bytes)
        dicts.append(
            {
                "storage_key": f"{STAGING_PREFIX}{key}",
                "telegram_file_id": "AgADBQ",
                "position": position,
            }
        )
    return dicts


def _submit_input(ad: Ad, photos: list[dict]) -> SubmitAdInput:
    """Build a ``SubmitAdInput`` carrying *photos* for *ad*."""
    return SubmitAdInput(
        ad_id=ad.id,
        title_ru="Title",
        desc_ru="Description",
        category_id=ad.category_id,
        city_id=ad.city_id,
        price_amount=Decimal("100"),
        price_currency=CurrencyCode.EUR,
        photos=photos,
        user_id=ad.user_id,
    )


def test_intra_submission_duplicate_reclaims_all_four_staged_files(
    seller, category, city, tmp_path
) -> None:
    """A duplicate *within one submission* reclaims all four of its staged files.

    Two byte-identical photos at positions 0 and 1 in one ``submit_ad``: photo 0
    creates the row, photo 1 is skipped as a content duplicate, leaving a legal
    gap at ``position=1`` (``AdImage.Meta`` does not enforce contiguity).  The
    reclaim must remove photo 1's original **and** all three thumbnails from
    ``staging/`` — reclaiming only the original would let ``promote_media_files``
    promote the three orphans to permanent storage.  Photo 0's four files must
    still be promoted.
    """
    from django.test import override_settings

    from apps.ads.models import AdImage
    from apps.media.services.filesystem import STAGING_PREFIX

    ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)
    media_root = tmp_path

    with override_settings(MEDIA_ROOT=str(media_root)):
        photos = _stage_photos(media_root, [("first.jpg", 0), ("second.jpg", 1)])

        with patch(
            "apps.moderation.services.auto_moderation.auto_moderate",
            return_value=True,
        ):
            result = submit_ad(_submit_input(ad, photos))

        assert result.outcome is SubmitAdOutcome.PUBLISHED, result.errors

        # Exactly one row: the second photo was skipped.
        assert AdImage.objects.filter(ad=ad).count() == 1

        # Photo 0's original and thumbnails are promoted to permanent storage.
        assert (media_root / "first.jpg").is_file()
        for suffix in ("small", "medium", "large"):
            assert (media_root / f"first-{suffix}.jpg").is_file()

        # Photo 1's original AND thumbnails are absent from staging/ ...
        assert not (media_root / STAGING_PREFIX / "second.jpg").exists()
        for suffix in ("small", "medium", "large"):
            assert not (
                media_root / STAGING_PREFIX / f"second-{suffix}.jpg"
            ).exists()
        # ... and were never promoted to permanent storage.
        assert not (media_root / "second.jpg").exists()
        for suffix in ("small", "medium", "large"):
            assert not (media_root / f"second-{suffix}.jpg").exists()


def test_rollback_leaves_skipped_photo_staged_and_promotes_nothing(
    seller, category, city, tmp_path
) -> None:
    """Placement B: on rollback neither hook runs, so nothing is reclaimed.

    The reclaim is registered on ``transaction.on_commit``, so when the atomic
    block rolls back (``auto_moderate`` raises) **both** photos' staged files
    survive in ``staging/``, no ``AdImage`` row exists, and no file was
    promoted — the bytes await TTL reclamation.  Placement B **rejects
    placement A** (deleting inside the atomic block), which would irreversibly
    destroy the staged bytes of an upload the seller can retry.  ``RuntimeError``
    is used, never sleeps, so the interleaving is deterministic.
    """
    from django.test import override_settings

    from apps.ads.models import AdImage
    from apps.media.services.filesystem import STAGING_PREFIX

    ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)
    media_root = tmp_path

    with override_settings(MEDIA_ROOT=str(media_root)):
        photos = _stage_photos(media_root, [("first.jpg", 0), ("second.jpg", 1)])

        with patch(
            "apps.moderation.services.auto_moderation.auto_moderate",
            side_effect=RuntimeError("simulated moderation failure"),
        ):
            with pytest.raises(RuntimeError, match="simulated moderation failure"):
                submit_ad(_submit_input(ad, photos))

        # Both photos' staged files survive — nothing was reclaimed.
        assert (media_root / STAGING_PREFIX / "first.jpg").is_file()
        assert (media_root / STAGING_PREFIX / "second.jpg").is_file()

        # Nothing promoted to permanent storage.
        assert not (media_root / "first.jpg").exists()
        assert not (media_root / "second.jpg").exists()

        # No row committed.
        assert AdImage.objects.filter(ad=ad).count() == 0


def test_invalid_transition_does_not_reclaim_skipped_files(
    seller, category, city, tmp_path
) -> None:
    """The reclaim hook must not fire on a refused transition.

    ``INVALID_TRANSITION`` is an early **return**, not an exception, so the
    atomic block still commits and every hook registered before the refusal
    would fire.  Registering the reclaim above ``auto_moderate`` would therefore
    delete the skipped photo's staged file, and the seller's re-confirm would
    hit ``plan_staging_promotion``'s ``FileNotFoundError`` → ``PHOTO_UNAVAILABLE``
    → a forced full re-upload.  This test pins the hook placement: after a
    refused transition the skipped photo's staged files **still exist**.  It
    fails if the reclaim is moved above ``auto_moderate`` (or above the
    transition).

    The ad is ``REJECTED`` so the ``DRAFT -> ON_MODERATION`` transition is
    refused.  It already holds a row whose digest matches the staged bytes, so
    the ``create_or_skip`` loop — which runs *before* the transition — records a
    reclaim.  The hook must therefore NOT be registered, because control leaves
    via the early return before reaching it.
    """
    from django.test import override_settings

    from apps.ads.models import AdImage
    from apps.media.services.filesystem import STAGING_PREFIX

    ad = create_test_ad(seller, category, city, status=AdStatus.REJECTED)
    media_root = tmp_path

    with override_settings(MEDIA_ROOT=str(media_root)):
        photo_bytes = _make_jpeg_bytes()
        # An existing row on this ad with the same digest as the staged bytes,
        # so the new submission is a content duplicate and would be reclaimed.
        from apps.media.services.hash_service import FileHashService

        staging_dir = media_root / STAGING_PREFIX
        staging_dir.mkdir(parents=True, exist_ok=True)
        (staging_dir / "dup.jpg").write_bytes(photo_bytes)
        digest = FileHashService.calculate_sha256(
            str(staging_dir / "dup.jpg")
        )
        AdImage.objects.create(ad=ad, image="existing.jpg", position=0, sha256=digest)

        photos = [
            {
                "storage_key": f"{STAGING_PREFIX}dup.jpg",
                "telegram_file_id": "AgADBQ",
                "position": 1,
            }
        ]

        with patch(
            "apps.moderation.services.auto_moderation.auto_moderate",
            return_value=True,
        ):
            result = submit_ad(_submit_input(ad, photos))

        assert result.outcome is SubmitAdOutcome.INVALID_TRANSITION

        # The staged duplicate is untouched — no reclaim fired on the committed
        # refusal, which is only true while the hook sits after the transition.
        assert (media_root / STAGING_PREFIX / "dup.jpg").is_file()
        assert not (media_root / "dup.jpg").exists()
        # The pre-existing row is the only row; the duplicate was skipped.
        assert AdImage.objects.filter(ad=ad).count() == 1


def test_moderation_failure_still_reclaims_skipped_files(
    seller, category, city, tmp_path
) -> None:
    """``auto_moderate`` returning ``False`` still commits, so the hooks fire.

    A moderation failure is not an exception: the transaction commits, the
    reclaim hook runs, and the skipped duplicate's staged files are removed —
    while the outcome is ``MODERATION_FAILED``.
    """
    from django.test import override_settings

    from apps.ads.models import AdImage
    from apps.media.services.filesystem import STAGING_PREFIX

    ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)
    media_root = tmp_path

    with override_settings(MEDIA_ROOT=str(media_root)):
        photos = _stage_photos(media_root, [("first.jpg", 0), ("second.jpg", 1)])

        with patch(
            "apps.moderation.services.auto_moderation.auto_moderate",
            return_value=False,
        ):
            result = submit_ad(_submit_input(ad, photos))

        assert result.outcome is SubmitAdOutcome.MODERATION_FAILED

        # The committed hooks fired: the skipped photo's staged files are gone.
        assert not (media_root / STAGING_PREFIX / "second.jpg").exists()
        for suffix in ("small", "medium", "large"):
            assert not (
                media_root / STAGING_PREFIX / f"second-{suffix}.jpg"
            ).exists()
        assert not (media_root / "second.jpg").exists()

        # The first photo's row committed and its files were promoted.
        assert AdImage.objects.filter(ad=ad).count() == 1


def test_reclaim_failure_leaves_skipped_file_staged_not_promoted(
    seller, category, city, tmp_path
) -> None:
    """A reclaim that exhausts its retries never promotes the skipped file.

    The prune of ``permanent_keys`` runs **before** the reclaim hook: the
    promotion closure binds that same list object (``lambda keys=permanent_keys``)
    and is pruned by in-place slice assignment, so when
    ``reclaim_staged_keys`` fails to delete the skipped file the key is already
    absent from the promotion list.  The bytes therefore stay in
    ``staging/`` for the mtime TTL instead of becoming a permanent orphan.

    This is the counterpart to the success-path test above.  It fails if the
    two ``on_commit`` registrations are reordered (a reclaim that runs after a
    promotion would race the file's promotion) or if the in-place prune is
    replaced by a rebind (the closure would keep the unpruned list and promote
    the orphan).  ``os.remove`` is forced to fail all retries and ``time.sleep``
    is stubbed so there is no real backoff.
    """
    from django.test import override_settings

    from apps.ads.models import AdImage
    from apps.media.services.filesystem import STAGING_PREFIX

    ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)
    media_root = tmp_path

    with override_settings(MEDIA_ROOT=str(media_root)):
        photos = _stage_photos(media_root, [("first.jpg", 0), ("second.jpg", 1)])

        with (
            patch(
                "apps.moderation.services.auto_moderation.auto_moderate",
                return_value=True,
            ),
            patch(
                "apps.media.services.filesystem.os.remove",
                side_effect=PermissionError("simulated delete failure"),
            ) as remove_mock,
            patch("apps.media.services.filesystem.time.sleep"),
        ):
            result = submit_ad(_submit_input(ad, photos))

        assert result.outcome is SubmitAdOutcome.PUBLISHED, result.errors

        # Each of the skipped upload's four staged files was retried the full
        # three attempts before ``delete_photo`` gave up.
        assert remove_mock.call_count == 4 * 3

        # Exactly one row: the second photo was skipped.
        assert AdImage.objects.filter(ad=ad).count() == 1

        # The skipped file survives in staging/ — never promoted to permanent
        # storage, so it awaits TTL reclamation rather than orphaning forever.
        assert (media_root / STAGING_PREFIX / "second.jpg").is_file()
        assert not (media_root / "second.jpg").exists()

        # The surviving photo was promoted normally, proving the failed reclaim
        # did not abort the promotion hook.
        assert (media_root / "first.jpg").is_file()
        for suffix in ("small", "medium", "large"):
            assert (media_root / f"first-{suffix}.jpg").is_file()



# ---------------------------------------------------------------------------
# 06-PII-109: create-time storage-consent gate — refused before any write
# ---------------------------------------------------------------------------


class TestSubmitAdStorageConsentGate:
    """``submit_ad`` refuses a never-consented seller before any write.

    The gate is the FIRST statement of ``submit_ad``: before the staged-media
    plan, thumbnail generation and ``transaction.atomic()``. A refused seller
    therefore has no row mutated, no ``AdImage`` created and no filesystem touch.
    """

    def _input_for(self, ad: Ad, *, photos: list[dict] | None = None) -> SubmitAdInput:
        return SubmitAdInput(
            ad_id=ad.id,
            title_ru="Should not be written",
            desc_ru="Should not be written",
            category_id=ad.category_id,
            city_id=ad.city_id,
            price_amount=Decimal("100"),
            price_currency=CurrencyCode.EUR,
            photos=photos or [],
            user_id=ad.user_id,
        )

    def test_never_consented_seller_refused(self, category, city) -> None:
        """A never-consented seller gets CONSENT_REQUIRED and no row change."""
        seller = make_user(900000710)
        assert seller.consent_given_at is None
        ad = create_test_ad(
            seller, category, city, status=AdStatus.DRAFT, title="Original"
        )

        result = submit_ad(self._input_for(ad))

        assert result.outcome is SubmitAdOutcome.CONSENT_REQUIRED
        assert result.errors  # carries a user-facing reason
        ad.refresh_from_db()
        assert ad.status == AdStatus.DRAFT
        assert ad.title == "Original"

    def test_refusal_precedes_the_staged_media_plan(self, category, city, tmp_path) -> None:
        """The gate wins over ``PHOTO_UNAVAILABLE`` — it runs before the plan.

        A staged photo key whose file is missing would normally raise inside
        ``plan_staging_promotion`` and yield PHOTO_UNAVAILABLE. Observing
        CONSENT_REQUIRED instead proves the consent gate is the first statement,
        ahead of every filesystem touch.
        """
        from django.test import override_settings

        from apps.media.services.filesystem import STAGING_PREFIX

        seller = make_user(900000711)
        ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)

        photos = [
            {
                "storage_key": f"{STAGING_PREFIX}never-uploaded.jpg",
                "telegram_file_id": "AgADBQ",
                "position": 0,
            }
        ]

        with override_settings(MEDIA_ROOT=str(tmp_path)):
            result = submit_ad(self._input_for(ad, photos=photos))

        assert result.outcome is SubmitAdOutcome.CONSENT_REQUIRED
        assert result.outcome is not SubmitAdOutcome.PHOTO_UNAVAILABLE
        assert not (tmp_path / STAGING_PREFIX / "never-uploaded.jpg").exists()

    def test_consented_seller_submits_unchanged(self, seller, category, city) -> None:
        """A consented seller submits exactly as before (the gate is transparent)."""
        ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)

        with patch(
            "apps.moderation.services.auto_moderation.auto_moderate",
            return_value=True,
        ):
            result = submit_ad(self._input_for(ad))

        assert result.outcome is SubmitAdOutcome.PUBLISHED
        assert result.errors == []
        ad.refresh_from_db()
        assert ad.status == AdStatus.ON_MODERATION
        assert ad.title == "Should not be written"
