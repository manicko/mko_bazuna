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

from apps.ads.models import Ad
from apps.ads.services.submission import SubmitAdInput, submit_ad
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


def _make_input(ad: Ad) -> SubmitAdInput:
    """Build a ``SubmitAdInput`` for *ad* with minimal valid fields."""
    return SubmitAdInput(
        ad_id=ad.id,
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
    ``(True, [])``.
    """
    ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)

    with patch(
        "apps.moderation.services.auto_moderation.auto_moderate",
        return_value=True,
    ) as mock_moderate:
        passed, errors = submit_ad(_make_input(ad))

    assert passed is True
    assert errors == []
    mock_moderate.assert_called_once()

    ad.refresh_from_db()
    assert ad.status == AdStatus.ON_MODERATION
