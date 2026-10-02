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
from conftest import create_test_ad

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
