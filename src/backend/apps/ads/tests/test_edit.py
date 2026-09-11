"""
Integration tests for the ``ad_edit`` reactivation path.

These tests assert the **current** (pre-QLT-001 Stage 3 migration) behavior of
the ``is_reactivation`` branch in ``apps/ads/views/edit.py``. They serve as the
behavioral baseline: when the reactivation branch is migrated to call
``submit_ad`` (Block 12 / A4), every assertion in this file must continue to
hold — verifying behavioral equivalence across the migration.

Reactors under test:
    - ARCHIVED -> ON_MODERATION (status transition, archived_at cleared)
    - auto_moderate invoked inside the transaction
    - On pass: redirect to dashboard, status PUBLISHED
    - On fail: re-render edit.html with error, status stays ON_MODERATION
    - Currency "keep-current" on invalid input (diverges from bot's None-coercion)
    - price_normalized_eur recomputed via PriceNormalizer on valid price
    - Title/description updated from POST data
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest
from django.test import Client
from django.urls import reverse

from apps.ads.models import Ad
from apps.core.enums import AdStatus
from apps.currencies.enums import CurrencyCode
from apps.currencies.services.price_normalizer import PriceNormalizer
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


@pytest.fixture
def permissive_criteria(monkeypatch) -> None:
    """Monkeypatch moderation criteria so the real auto_moderate passes.

    Mirrors the ``permissive_criteria`` fixture in
    ``telegram_bot/tests/test_ad_create.py``.  This lets the real
    ``auto_moderate`` run end-to-end (including ``_pass_moderation``
    which sets PUBLISHED), rather than mocking the whole function.
    """
    _permissive = (1, 200, 1, 2000, False, 0, 10, (), 100, 0)
    monkeypatch.setattr(
        "apps.moderation.services.auto_moderation._get_cached_criteria",
        lambda: _permissive,
    )
    monkeypatch.setattr(
        "apps.moderation.services.auto_moderation._validate_max_ads_per_user",
        lambda user_id, max_ads: True,
    )
    monkeypatch.setattr(
        "apps.moderation.services.auto_moderation._is_duplicate_title",
        lambda title, user_id, ad_id, threshold: False,
    )


@pytest.fixture
def archived_ad(seller, category, city) -> Ad:
    """Create a PUBLISHED ad, then archive it so it can be reactivated."""
    ad = create_test_ad(
        seller, category, city, status=AdStatus.PUBLISHED, price=100
    )
    ad.transition_to(AdStatus.ARCHIVED)
    ad.refresh_from_db()
    assert ad.status == AdStatus.ARCHIVED
    return ad


@pytest.fixture
def client_(seller) -> Client:
    """Django test client authenticated as the seller."""
    client = Client()
    client.force_login(seller)
    return client


@pytest.fixture
def btc_rate():
    """Ensure a BAM exchange rate exists and is current for normalization."""
    from apps.currencies.models import ExchangeRate

    ExchangeRate.objects.update_or_create(
        currency=CurrencyCode.BAM.value,
        defaults={
            "rate_to_eur": Decimal("0.512"),
            "effective_date": "2025-01-01",
            "source": "manual_seed",
            "is_current": True,
        },
    )
    return Decimal("0.512")


# ---------------------------------------------------------------------------
# Test 1: ARCHIVED -> ON_MODERATION with auto_moderate invoked
# ---------------------------------------------------------------------------


class TestReactivationStatusTransition:
    """Verify the reactivation branch transitions ARCHIVED -> ON_MODERATION."""

    def test_edit_reactivation_archived_to_on_moderation(
        self, client_, seller, category, city, archived_ad
    ) -> None:
        """ARCHIVED ad edited with reactivate=1 -> status ON_MODERATION,
        auto_moderate called.

        We mock ``auto_moderate`` to return ``True`` so the mock bypasses
        ``_pass_moderation`` (which would set PUBLISHED).  This isolates the
        view's own transition (``ARCHIVED -> ON_MODERATION`` via
        ``ad.transition_to`` before the moderation call) and verifies
        ``auto_moderate`` is invoked.
        """
        ad = archived_ad
        original_title = "Old Title"
        Ad.objects.filter(pk=ad.pk).update(title=original_title)

        with patch(
            "apps.ads.views.edit.auto_moderate", return_value=True
        ) as mock_moderate:
            response = client_.post(
                reverse("ads:edit", args=[ad.id]),
                data={
                    "title": original_title,
                    "description": ad.description,
                    "price_amount": "100",
                    "price_currency": "EUR",
                    "reactivate": "1",
                },
                follow=True,
            )

        assert response.status_code == 200
        mock_moderate.assert_called_once()
        ad.refresh_from_db()
        assert ad.status == AdStatus.ON_MODERATION
        # archived_at should be cleared by transition_to(ON_MODERATION)
        assert ad.archived_at is None


# ---------------------------------------------------------------------------
# Test 2: Reactivation pass -> redirect to dashboard, PUBLISHED
# ---------------------------------------------------------------------------


class TestReactivationAutoModerate:
    """Verify auto_moderate outcome determines the post-reactivation path."""

    def test_edit_reactivation_passes_auto_moderate(
        self, client_, seller, category, city, archived_ad,
        permissive_criteria,
    ) -> None:
        """Reactivation where content passes moderation -> redirect to
        dashboard, status PUBLISHED."""
        ad = archived_ad

        response = client_.post(
            reverse("ads:edit", args=[ad.id]),
            data={
                "title": ad.title,
                "description": ad.description,
                "price_amount": "100",
                "price_currency": "EUR",
                "reactivate": "1",
            },
        )

        assert response.status_code == 302
        assert "dashboard" in response.url
        ad.refresh_from_db()
        assert ad.status == AdStatus.PUBLISHED
        assert ad.published_at is not None

    def test_edit_reactivation_fails_auto_moderate(
        self, client_, seller, category, city, archived_ad
    ) -> None:
        """Reactivation where content fails moderation -> re-renders
        edit.html with error.

        We mock ``auto_moderate`` to return ``False``.  Since the mock
        bypasses the internal ``_fail_moderation`` (which sets
        ``ON_MODERATION_FAILED``), the ad remains at ``ON_MODERATION`` —
        the view only re-renders the edit page on failure.
        """
        ad = archived_ad

        with patch(
            "apps.ads.views.edit.auto_moderate", return_value=False
        ) as mock_moderate:
            response = client_.post(
                reverse("ads:edit", args=[ad.id]),
                data={
                    "title": ad.title,
                    "description": ad.description,
                    "price_amount": "100",
                    "price_currency": "EUR",
                    "reactivate": "1",
                },
            )

        assert response.status_code == 200
        mock_moderate.assert_called_once()
        ad.refresh_from_db()
        # ad stays at ON_MODERATION (the view transitions to ON_MODERATION
        # before calling auto_moderate; the failure path does not change
        # it further)
        assert ad.status == AdStatus.ON_MODERATION
        # The edit template should be re-rendered with an error context
        assert "error" in response.context
        assert response.context["error"]


# ---------------------------------------------------------------------------
# Test 3: Currency "keep-current" on invalid input
# ---------------------------------------------------------------------------


class TestReactivationCurrencyKeepCurrent:
    """Verify invalid currency keeps the ad's existing currency (web-specific
    behavior; diverges from bot's coerce-to-None)."""

    def test_edit_reactivation_currency_keep_current(
        self, client_, seller, category, city, permissive_criteria
    ) -> None:
        """Reactivation with invalid price_currency -> keeps existing ad
        currency (NOT coerced to None)."""
        ad = create_test_ad(
            seller, category, city, status=AdStatus.PUBLISHED, price=100
        )
        ad.transition_to(AdStatus.ARCHIVED)
        ad.refresh_from_db()

        original_currency = ad.price_currency

        response = client_.post(
            reverse("ads:edit", args=[ad.id]),
            data={
                "title": ad.title,
                "description": ad.description,
                "price_amount": "100",
                "price_currency": "INVALID_CURRENCY_CODE",
                "reactivate": "1",
            },
        )

        assert response.status_code == 302
        ad.refresh_from_db()
        # The ad's currency must be preserved — NOT set to None
        assert ad.price_currency == original_currency
        assert ad.price_currency is not None


# ---------------------------------------------------------------------------
# Test 4: price_normalized_eur recomputed on valid price
# ---------------------------------------------------------------------------


class TestReactivationPriceNormalized:
    """Verify price_normalized_eur is recomputed via PriceNormalizer."""

    def test_edit_reactivation_price_normalized_recomputed(
        self, client_, seller, category, city, btc_rate, permissive_criteria
    ) -> None:
        """Reactivation with valid BAM price -> price_normalized_eur
        matches PriceNormalizer().normalize_to_eur(amount, BAM)."""
        ad = create_test_ad(
            seller, category, city, status=AdStatus.PUBLISHED, price=100
        )
        ad.transition_to(AdStatus.ARCHIVED)
        ad.refresh_from_db()

        new_amount = Decimal("200")

        response = client_.post(
            reverse("ads:edit", args=[ad.id]),
            data={
                "title": ad.title,
                "description": ad.description,
                "price_amount": str(new_amount),
                "price_currency": CurrencyCode.BAM.value,
                "reactivate": "1",
            },
        )

        assert response.status_code == 302
        ad.refresh_from_db()
        expected = PriceNormalizer().normalize_to_eur(
            new_amount, CurrencyCode.BAM
        )
        assert ad.price_normalized_eur == expected
        assert ad.price_amount == new_amount
        assert ad.price_currency == CurrencyCode.BAM.value


# ---------------------------------------------------------------------------
# Test 5: Title/description updated from POST
# ---------------------------------------------------------------------------


class TestReactivationTextUpdated:
    """Verify reactivation updates title/description from POST data."""

    def test_edit_reactivation_text_updated(
        self, client_, seller, category, city, archived_ad,
        permissive_criteria,
    ) -> None:
        """Reactivation updates ad.title and ad.description from POST."""
        ad = archived_ad
        new_title = "Updated Reactivated Title"
        new_description = "Updated reactivated description text."

        response = client_.post(
            reverse("ads:edit", args=[ad.id]),
            data={
                "title": new_title,
                "description": new_description,
                "price_amount": "100",
                "price_currency": "EUR",
                "reactivate": "1",
            },
        )

        assert response.status_code == 302
        ad.refresh_from_db()
        assert ad.title == new_title
        assert ad.description == new_description
