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

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.db.models.signals import post_save
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.ads.models import Ad, AdImage
from apps.ads.views.edit import EDITABLE_DIRECT_SAVE_STATUSES, _apply_price_change
from apps.core.enums import AdStatus
from apps.currencies.enums import CurrencyCode
from apps.currencies.services.price_normalizer import PriceNormalizer
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


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
        ``ad.transition_to`` inside submit_ad) and verifies
        ``auto_moderate`` is invoked.

        Note: after the A4 migration, ``auto_moderate`` is called inside
        ``submit_ad`` (not directly in edit.py), so the mock targets the
        source module ``apps.moderation.services.auto_moderation``.
        """
        ad = archived_ad
        original_title = "Old Title"
        Ad.objects.filter(pk=ad.pk).update(title=original_title)

        with patch(
            "apps.moderation.services.auto_moderation.auto_moderate",
            return_value=True,
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

        Note: after the A4 migration, ``auto_moderate`` is called inside
        ``submit_ad``, so the mock targets the source module.
        """
        ad = archived_ad

        with patch(
            "apps.moderation.services.auto_moderation.auto_moderate",
            return_value=False,
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


# ---------------------------------------------------------------------------
# Test 6: PUBLISHED text-edit branch (Zone C2 — hide-on-text-edit)
# ---------------------------------------------------------------------------


class TestPublishedTextEdit:
    """Verify the PUBLISHED text-edit branch in ``ad_edit`` (Zone C2).

    Text edits on a PUBLISHED ad transition to ON_MODERATION and hide the ad
    immediately, then ``auto_moderate`` is invoked: on pass the ad is promoted
    back to PUBLISHED; on fail it stays ON_MODERATION and the edit form is
    re-rendered with a seller-safe error. Price/photo-only edits stay
    PUBLISHED (no auto-moderation) and restart the auto-archive clock.
    Mixed edits follow the text rule.
    """

    def test_edit_published_text_edit_transitions_to_on_moderation(
        self, client_, seller, category, city
    ) -> None:
        """PUBLISHED ad with text change -> ON_MODERATION, published_at preserved,
        archived_at stays NULL, title/description updated, redirect to dashboard.

        ``transition_to(ON_MODERATION)`` clears moderation_failed_at, rejected_at,
        and archived_at — but NOT published_at. The original published_at value
        must therefore be retained (not cleared).

        We mock ``auto_moderate`` to return ``True`` so the mock bypasses
        ``_pass_moderation`` (which would set PUBLISHED), isolating the view's
        transition ``PUBLISHED -> ON_MODERATION`` and verifying the redirect.
        """
        ad = create_test_ad(
            seller, category, city, status=AdStatus.PUBLISHED, price=100
        )
        original_published_at = ad.published_at
        new_title = "Updated Published Title"
        new_description = "Updated published description text."

        with patch(
            "apps.moderation.services.auto_moderation.auto_moderate",
            return_value=True,
        ):
            response = client_.post(
                reverse("ads:edit", args=[ad.id]),
                data={
                    "title": new_title,
                    "description": new_description,
                    "price_amount": "100",
                    "price_currency": CurrencyCode.EUR.value,
                },
            )

        assert response.status_code == 302
        assert "dashboard" in response.url
        ad.refresh_from_db()
        assert ad.status == AdStatus.ON_MODERATION
        # archived_at must remain NULL (never set for a PUBLISHED ad)
        assert ad.archived_at is None
        # published_at is NOT cleared by transition_to(ON_MODERATION)
        assert ad.published_at == original_published_at
        assert ad.title == new_title
        assert ad.description == new_description

    def test_edit_published_price_only_resets_publish_clock(
        self, client_, seller, category, city
    ) -> None:
        """PUBLISHED ad with price-only change -> stays PUBLISHED and the
        publish clock is reset (published_at moves strictly forward),
        price_normalized_eur recomputed via PriceNormalizer.

        Title and description are unchanged so ``has_text_change`` is False,
        taking the price/photo-only branch (status preserved).

        Reason for the rewrite (project rule 2 — production code is king): the
        previous version of this test asserted ``published_at`` was *unchanged*
        and its docstring said so. That encoded the defect fixed in BLOCK 2;
        decision J, ``Ad.published_at``'s ``help_text`` and ``db-schema.md`` all
        promise the reset. The code now matches the documentation.
        """
        ad = create_test_ad(
            seller, category, city, status=AdStatus.PUBLISHED, price=100
        )
        initial_published_at = ad.published_at
        new_price = Decimal("200")

        response = client_.post(
            reverse("ads:edit", args=[ad.id]),
            data={
                "title": ad.title,
                "description": ad.description,
                "price_amount": str(new_price),
                "price_currency": CurrencyCode.EUR.value,
            },
        )

        assert response.status_code == 302
        assert "dashboard" in response.url
        # Assert on a second, independent fetch: an in-memory check would pass
        # even if update_fields were wrong and the reset never persisted.
        reloaded = Ad.objects.get(pk=ad.pk)
        assert reloaded.status == AdStatus.PUBLISHED
        # The price edit restarts the auto-archive clock.
        assert reloaded.published_at > initial_published_at
        # price_normalized_eur recomputed via PriceNormalizer
        expected_normalized = PriceNormalizer().normalize_to_eur(
            new_price, CurrencyCode.EUR
        )
        assert reloaded.price_normalized_eur == expected_normalized
        assert reloaded.price_amount == new_price

    def test_edit_published_price_only_does_not_touch_original_published_at(
        self, client_, seller, category, city
    ) -> None:
        """A price-only edit resets ``published_at`` but leaves the immutable
        ``original_published_at`` untouched.

        ``TestOriginalPublishedAtImmutability`` covers the re-publish path; this
        covers the price-edit path, which no existing test exercised.

        ``create_test_ad(status=PUBLISHED)`` does not set
        ``original_published_at`` (only the first ``transition_to(PUBLISHED)``
        does), so we seed it explicitly to have a real value to preserve.
        """
        first_published_at = timezone.now() - timedelta(days=30)
        ad = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.PUBLISHED,
            price=100,
            original_published_at=first_published_at,
        )
        initial_original_published_at = ad.original_published_at
        assert initial_original_published_at == first_published_at

        response = client_.post(
            reverse("ads:edit", args=[ad.id]),
            data={
                "title": ad.title,
                "description": ad.description,
                "price_amount": "200",
                "price_currency": CurrencyCode.EUR.value,
            },
        )

        assert response.status_code == 302
        reloaded = Ad.objects.get(pk=ad.pk)
        assert reloaded.original_published_at == initial_original_published_at
        assert reloaded.published_at > initial_original_published_at

    def test_edit_published_price_only_fires_single_post_save(
        self, client_, seller, category, city
    ) -> None:
        """The price-only edit produces exactly ONE ``post_save`` for ``Ad``.

        Regression guard for the duplicate-alert hazard: the clock reset shares
        the single existing ``save()``. A second ``save()`` in the same
        transaction would fire a second ``post_save`` and register a second
        ``transaction.on_commit(deliver_immediate_alerts)``, which can send a
        duplicate Telegram message.
        """
        ad = create_test_ad(
            seller, category, city, status=AdStatus.PUBLISHED, price=100
        )
        saves: list[int] = []

        def _record_post_save(sender, instance, **kwargs) -> None:
            if instance.pk == ad.pk:
                saves.append(instance.pk)

        post_save.connect(_record_post_save, sender=Ad)
        try:
            response = client_.post(
                reverse("ads:edit", args=[ad.id]),
                data={
                    "title": ad.title,
                    "description": ad.description,
                    "price_amount": "200",
                    "price_currency": CurrencyCode.EUR.value,
                },
            )
        finally:
            post_save.disconnect(_record_post_save, sender=Ad)

        assert response.status_code == 302
        assert len(saves) == 1

    def test_edit_published_mixed_edit_transitions_to_on_moderation(
        self, client_, seller, category, city
    ) -> None:
        """PUBLISHED ad with text + price change -> ON_MODERATION (text rule wins),
        while price_normalized_eur is still updated.

        The text-edit rule dominates the transition target, but the price change
        is still applied within the same save before transitioning. We mock
        ``auto_moderate`` to return ``True`` so the mock bypasses
        ``_pass_moderation`` (which would set PUBLISHED), isolating the view's
        transition to ON_MODERATION.
        """
        ad = create_test_ad(
            seller, category, city, status=AdStatus.PUBLISHED, price=100
        )
        original_published_at = ad.published_at
        new_title = "Updated Mixed Title"
        new_description = "Updated mixed description text."
        new_price = Decimal("200")

        with patch(
            "apps.moderation.services.auto_moderation.auto_moderate",
            return_value=True,
        ):
            response = client_.post(
                reverse("ads:edit", args=[ad.id]),
                data={
                    "title": new_title,
                    "description": new_description,
                    "price_amount": str(new_price),
                    "price_currency": CurrencyCode.EUR.value,
                },
            )

        assert response.status_code == 302
        assert "dashboard" in response.url
        ad.refresh_from_db()
        # Text rule wins -> ON_MODERATION
        assert ad.status == AdStatus.ON_MODERATION
        assert ad.published_at == original_published_at
        # Price is still applied even though text rule controls the transition
        expected_normalized = PriceNormalizer().normalize_to_eur(
            new_price, CurrencyCode.EUR
        )
        assert ad.price_normalized_eur == expected_normalized
        assert ad.title == new_title

    def test_edit_published_text_edit_calls_auto_moderate(
        self, client_, seller, category, city
    ) -> None:
        """PUBLISHED text edit invokes ``auto_moderate`` after the status
        transition to ON_MODERATION.

        We mock ``auto_moderate`` to return ``True`` so the mock bypasses
        ``_pass_moderation`` (which would set PUBLISHED), isolating the view's
        transition ``PUBLISHED -> ON_MODERATION`` and verifying
        ``auto_moderate`` is invoked exactly once.
        """
        ad = create_test_ad(
            seller, category, city, status=AdStatus.PUBLISHED, price=100
        )
        new_title = "Updated Auto Moderate Title"
        new_description = "Updated auto moderate description text."

        with patch(
            "apps.moderation.services.auto_moderation.auto_moderate",
            return_value=True,
        ) as mock_moderate:
            response = client_.post(
                reverse("ads:edit", args=[ad.id]),
                data={
                    "title": new_title,
                    "description": new_description,
                    "price_amount": "100",
                    "price_currency": CurrencyCode.EUR.value,
                },
            )

        assert response.status_code == 302
        assert "dashboard" in response.url
        mock_moderate.assert_called_once()
        ad.refresh_from_db()
        assert ad.status == AdStatus.ON_MODERATION

    def test_edit_published_text_edit_passes_auto_moderation(
        self, client_, seller, category, city, permissive_criteria
    ) -> None:
        """PUBLISHED text edit where content passes moderation -> redirect
        to dashboard, status PUBLISHED, published_at set by _pass_moderation.

        Uses the real ``auto_moderate`` (not mocked) with the
        ``permissive_criteria`` fixture so the full end-to-end pass path runs,
        including ``_pass_moderation`` -> ``set_published`` ->
        ``transition_to(PUBLISHED)`` (which sets ``published_at``).
        """
        ad = create_test_ad(
            seller, category, city, status=AdStatus.PUBLISHED, price=100
        )
        new_title = "Updated Pass Title"
        new_description = "Updated pass description text."

        response = client_.post(
            reverse("ads:edit", args=[ad.id]),
            data={
                "title": new_title,
                "description": new_description,
                "price_amount": "100",
                "price_currency": CurrencyCode.EUR.value,
            },
        )

        assert response.status_code == 302
        assert "dashboard" in response.url
        ad.refresh_from_db()
        assert ad.status == AdStatus.PUBLISHED

    def test_edit_published_text_edit_fails_auto_moderation(
        self, client_, seller, category, city
    ) -> None:
        """PUBLISHED text edit where moderation fails -> re-renders edit.html
        with error context (200), status stays ON_MODERATION.

        We mock ``auto_moderate`` to return ``False``. Since the mock bypasses
        the internal ``_fail_moderation`` (which would set ON_MODERATION_FAILED),
        the ad remains at ON_MODERATION — the view only re-renders the edit
        page on failure with a seller-safe error message.
        """
        ad = create_test_ad(
            seller, category, city, status=AdStatus.PUBLISHED, price=100
        )
        new_title = "Updated Fail Title"
        new_description = "Updated fail description text."

        with patch(
            "apps.moderation.services.auto_moderation.auto_moderate",
            return_value=False,
        ) as mock_moderate:
            response = client_.post(
                reverse("ads:edit", args=[ad.id]),
                data={
                    "title": new_title,
                    "description": new_description,
                    "price_amount": "100",
                    "price_currency": CurrencyCode.EUR.value,
                },
            )

        assert response.status_code == 200
        mock_moderate.assert_called_once()
        ad.refresh_from_db()
        assert ad.status == AdStatus.ON_MODERATION
        assert "error" in response.context
        assert response.context["error"]


# ---------------------------------------------------------------------------
# Parity test: _apply_price_change delegates to the shared utility
# (10-QLT-001 DRY invariant — closes V-09 test gap)
# ---------------------------------------------------------------------------


class TestApplyPriceChangeDelegation:
    """Verify ``_apply_price_change`` delegates price normalization to the
    shared ``normalize_price_to_eur`` utility.

    The DRY invariant (10-QLT-001) requires both the edit path and the
    ``submit_ad`` path to call the **same** shared utility.  These tests patch
    the utility at the call-site namespace (``apps.ads.views.edit``) — not the
    definition site — to verify delegation without invoking real conversion.
    """

    def test_apply_price_change_delegates_to_shared_utility(
        self, seller, category, city
    ) -> None:
        """Currency-present (success) and currency-None paths both call the
        shared ``normalize_price_to_eur`` utility instead of re-implementing
        normalization inline.
        """
        ad = create_test_ad(
            seller, category, city, status=AdStatus.PUBLISHED, price=100
        )

        with patch("apps.ads.views.edit.normalize_price_to_eur") as mock_normalizer:
            # Currency present (success path)
            _apply_price_change(ad, Decimal("200"), CurrencyCode.BAM)
            mock_normalizer.assert_called_with(ad, Decimal("200"), CurrencyCode.BAM)
            mock_normalizer.reset_mock()

            # Currency None (→ None path — utility clears the value)
            _apply_price_change(ad, Decimal("0"), None)
            mock_normalizer.assert_called_with(ad, Decimal("0"), None)


# ---------------------------------------------------------------------------
# TST-008: Authorization (wrong-user 403 on GET and POST)
# ---------------------------------------------------------------------------


class TestEditAuthorization:
    """TST-008: wrong-user GET/POST returns 403 Forbidden."""

    def test_edit_wrong_user_get_returns_403(
        self,
        seller,
        user,
        category,
        city,
    ) -> None:
        """A different authenticated user GETting /ads/<id>/edit/ gets 403."""
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        client = Client()
        client.force_login(user)

        response = client.get(reverse("ads:edit", args=[ad.id]))
        assert response.status_code == 403

    def test_edit_wrong_user_post_returns_403(
        self,
        seller,
        user,
        category,
        city,
    ) -> None:
        """A different authenticated user POSTing to /ads/<id>/edit/ gets 403."""
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        client = Client()
        client.force_login(user)

        response = client.post(
            reverse("ads:edit", args=[ad.id]),
            data={
                "title": "Hack Attempt",
                "description": "Trying to edit someone else's ad",
                "price_amount": "100",
                "price_currency": CurrencyCode.EUR.value,
            },
        )
        assert response.status_code == 403

        ad.refresh_from_db()
        assert ad.title != "Hack Attempt"


# ---------------------------------------------------------------------------
# TST-008: GET path renders the edit form with prefetched images
# ---------------------------------------------------------------------------


class TestEditGetPath:
    """TST-008: GET display path renders the edit form."""

    def test_edit_get_renders_form_with_images(
        self,
        seller,
        category,
        city,
    ) -> None:
        """GET /ads/<id>/edit/ renders the edit template with prefetched images."""
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        AdImage.objects.create(ad=ad, image="test.jpg", position=0)

        client = Client()
        client.force_login(seller)
        response = client.get(reverse("ads:edit", args=[ad.id]))

        assert response.status_code == 200
        assert "ad" in response.context
        assert response.context["ad"] == ad


# ---------------------------------------------------------------------------
# TST-008: ad_archive authorization + PUBLISHED → ARCHIVED transition
# ---------------------------------------------------------------------------


class TestAdArchive:
    """TST-008: ad_archive view (PUBLISHED → ARCHIVED + wrong-user 403)."""

    def test_archive_owner_transitions_to_archived(
        self,
        seller,
        category,
        city,
    ) -> None:
        """Owner POSTing to /ads/<id>/archive/ transitions PUBLISHED → ARCHIVED."""
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        client = Client()
        client.force_login(seller)

        response = client.post(reverse("ads:archive", args=[ad.id]))
        assert response.status_code == 302
        assert "dashboard" in response.url

        ad.refresh_from_db()
        assert ad.status == AdStatus.ARCHIVED
        assert ad.archived_at is not None

    def test_archive_wrong_user_returns_403(
        self,
        seller,
        user,
        category,
        city,
    ) -> None:
        """A different user POSTing to /ads/<id>/archive/ gets 403."""
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        client = Client()
        client.force_login(user)

        response = client.post(reverse("ads:archive", args=[ad.id]))
        assert response.status_code == 403

        ad.refresh_from_db()
        assert ad.status == AdStatus.PUBLISHED  # unchanged

    def test_archive_non_published_is_noop(
        self,
        seller,
        category,
        city,
    ) -> None:
        """ad_archive only acts on PUBLISHED; REJECTED ad stays REJECTED."""
        ad = create_test_ad(seller, category, city, status=AdStatus.REJECTED)
        client = Client()
        client.force_login(seller)

        response = client.post(reverse("ads:archive", args=[ad.id]))
        assert response.status_code == 302
        assert "dashboard" in response.url

        ad.refresh_from_db()
        assert ad.status == AdStatus.REJECTED  # unchanged


# ---------------------------------------------------------------------------
# Authz-002: ad_archive GET rejected with 405 (require_POST)
# ---------------------------------------------------------------------------


class TestAdArchiveGetRejected:
    """Authz-002: GET /ads/<id>/archive/ returns 405; POST still works."""

    def test_archive_get_returns_405(
        self,
        seller,
        category,
        city,
    ) -> None:
        """A crafted GET URL must not archive an ad; returns 405."""
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        client = Client()
        client.force_login(seller)

        response = client.get(reverse("ads:archive", args=[ad.id]))
        assert response.status_code == 405

        ad.refresh_from_db()
        assert ad.status == AdStatus.PUBLISHED  # unchanged by GET

    def test_archive_post_still_works(
        self,
        seller,
        category,
        city,
    ) -> None:
        """POST /ads/<id>/archive/ still archives the ad."""
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        client = Client()
        client.force_login(seller)

        response = client.post(reverse("ads:archive", args=[ad.id]))
        assert response.status_code == 302
        assert "dashboard" in response.url

        ad.refresh_from_db()
        assert ad.status == AdStatus.ARCHIVED


# ---------------------------------------------------------------------------
# TST-008: ad_reactivate authorization + ARCHIVED → ON_MODERATION/PUBLISHED
# ---------------------------------------------------------------------------


class TestAdReactivateDirect:
    """TST-008: ad_reactivate view (ARCHIVED → ON_MODERATION/PUBLISHED + 403)."""

    def test_reactivate_owner_transitions_to_published(
        self,
        seller,
        category,
        city,
        permissive_criteria,
    ) -> None:
        """Owner reactivating an ARCHIVED ad transitions through ON_MODERATION
        to PUBLISHED (with permissive criteria)."""
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        ad.transition_to(AdStatus.ARCHIVED)
        ad.refresh_from_db()
        assert ad.status == AdStatus.ARCHIVED

        client = Client()
        client.force_login(seller)
        response = client.post(reverse("ads:reactivate", args=[ad.id]))
        assert response.status_code == 302
        assert "dashboard" in response.url

        ad.refresh_from_db()
        assert ad.status == AdStatus.PUBLISHED
        assert ad.published_at is not None

    def test_reactivate_wrong_user_returns_403(
        self,
        seller,
        user,
        category,
        city,
    ) -> None:
        """A different user POSTing to /ads/<id>/reactivate/ gets 403."""
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        ad.transition_to(AdStatus.ARCHIVED)
        ad.refresh_from_db()
        client = Client()
        client.force_login(user)

        response = client.post(reverse("ads:reactivate", args=[ad.id]))
        assert response.status_code == 403

        ad.refresh_from_db()
        assert ad.status == AdStatus.ARCHIVED  # unchanged

    def test_reactivate_non_archived_is_noop(
        self,
        seller,
        category,
        city,
    ) -> None:
        """ad_reactivate only acts on ARCHIVED; PUBLISHED ad stays PUBLISHED."""
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        client = Client()
        client.force_login(seller)

        response = client.post(reverse("ads:reactivate", args=[ad.id]))
        assert response.status_code == 302
        assert "dashboard" in response.url

        ad.refresh_from_db()
        assert ad.status == AdStatus.PUBLISHED  # unchanged

    def test_reactivate_get_returns_405(
        self,
        seller,
        category,
        city,
    ) -> None:
        """A crafted GET URL must not reactivate an ad; returns 405."""
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        ad.transition_to(AdStatus.ARCHIVED)
        ad.refresh_from_db()
        assert ad.status == AdStatus.ARCHIVED

        client = Client()
        client.force_login(seller)

        response = client.get(reverse("ads:reactivate", args=[ad.id]))
        assert response.status_code == 405

        ad.refresh_from_db()
        assert ad.status == AdStatus.ARCHIVED  # unchanged by GET


# ---------------------------------------------------------------------------
# TST-008: Other-status direct-save branch — explicit allow-list (AD-002 / 8A)
# ---------------------------------------------------------------------------


class TestEditOtherStatusDirectSave:
    """The direct-save branch is an explicit allow-list, not a catch-all.

    ``ad_edit`` saves directly (no status transition, no auto-moderation) only
    for statuses in ``EDITABLE_DIRECT_SAVE_STATUSES`` (``DRAFT``,
    ``ON_MODERATION``). Every other status is refused and left untouched.

    History: this class previously claimed coverage of ``ON_MODERATION`` *and*
    ``ON_MODERATION_FAILED`` while containing a single test that asserted an
    ``ON_MODERATION`` ad was saved directly. The former ``else:`` catch-all in
    ``edit.py`` admitted five of seven statuses, so any allow-list or
    re-moderation fix broke it. Rewritten for finding AD-002 (BLOCK 8A). Reason
    (project rule 2 — production code is king): the old test encoded the
    defect — it treated a silent direct save for a non-editable status as
    correct behavior.
    """

    @pytest.mark.parametrize(
        "status",
        [
            AdStatus.ON_MODERATION_FAILED,
            AdStatus.REJECTED,
            AdStatus.DELETED,
            AdStatus.ARCHIVED,
        ],
    )
    def test_edit_non_editable_status_is_refused(
        self,
        seller,
        category,
        city,
        status: AdStatus,
    ) -> None:
        """POSTing an edit to a non-editable status is refused and the ad is
        left byte-identical on a fresh re-fetch.

        ``ARCHIVED`` here carries no ``reactivate`` key in the POST, so it takes
        the refusal path rather than the reactivation branch. The response must
        not be a success redirect that implies persistence, and the actionable
        message must be rendered.
        """
        ad = create_test_ad(seller, category, city, status=status, price=100)
        Ad.objects.filter(pk=ad.pk).update(
            title="Untouched Title",
            description="Untouched description body.",
        )
        before = Ad.objects.get(pk=ad.pk)
        snapshot = (
            before.title,
            before.description,
            before.price_amount,
            before.price_currency,
            before.price_normalized_eur,
            before.updated_at,
        )

        client = Client()
        client.force_login(seller)
        response = client.post(
            reverse("ads:edit", args=[ad.id]),
            data={
                "title": "Changed Title",
                "description": "Changed description body.",
                "price_amount": "999",
                "price_currency": CurrencyCode.EUR.value,
            },
        )

        # Not a redirect that implies the edit was persisted.
        assert response.status_code == 200
        assert response.context["error"] == (
            "This ad cannot be edited in its current status."
        )

        # Freshly re-fetched instance is byte-identical on every field the
        # former catch-all used to write.
        after = Ad.objects.get(pk=ad.pk)
        after_snapshot = (
            after.title,
            after.description,
            after.price_amount,
            after.price_currency,
            after.price_normalized_eur,
            after.updated_at,
        )
        assert after_snapshot == snapshot
        assert after.status == status

    @pytest.mark.parametrize(
        "status",
        [AdStatus.DRAFT, AdStatus.ON_MODERATION],
    )
    def test_edit_allow_listed_status_saves_directly(
        self,
        seller,
        category,
        city,
        status: AdStatus,
    ) -> None:
        """``DRAFT`` and ``ON_MODERATION`` still take the direct save: fields
        are written, status and ``moderation_failed_at`` are untouched.

        This is the positive half of the allow-list guard — without it an empty
        allow-list would satisfy the refusal tests.
        """
        ad = create_test_ad(seller, category, city, status=status, price=100)
        new_title = "Updated Allow-Listed Title"
        client = Client()
        client.force_login(seller)

        response = client.post(
            reverse("ads:edit", args=[ad.id]),
            data={
                "title": new_title,
                "description": ad.description,
                "price_amount": "100",
                "price_currency": CurrencyCode.EUR.value,
            },
        )

        assert response.status_code == 302
        assert "dashboard" in response.url
        ad.refresh_from_db()
        assert ad.title == new_title
        assert ad.status == status  # unchanged
        assert ad.moderation_failed_at is None  # untouched


# ---------------------------------------------------------------------------
# AD-002 / 8A: every one of the seven statuses has a defined outcome
# ---------------------------------------------------------------------------


class TestEditStatusAllowListEnumeration:
    """Structural guard: each of the seven ``AdStatus`` values has a defined
    ``ad_edit`` outcome, driven by the named ``EDITABLE_DIRECT_SAVE_STATUSES``
    allowance.

    A future re-broadening of the direct-save branch (adding back a catch-all)
    fails this enumeration.
    """

    def test_allow_list_constant_is_the_named_two_statuses(self) -> None:
        """The allow-list is the named ``frozenset`` of exactly DRAFT and
        ON_MODERATION — not a broadened set.
        """
        assert EDITABLE_DIRECT_SAVE_STATUSES == frozenset(
            {AdStatus.DRAFT, AdStatus.ON_MODERATION}
        )

    @pytest.mark.parametrize(
        ("status", "expected_outcome"),
        [
            (AdStatus.DRAFT, "direct_save"),
            (AdStatus.ON_MODERATION, "direct_save"),
            (AdStatus.PUBLISHED, "published_branch"),
            (AdStatus.ON_MODERATION_FAILED, "refused"),
            (AdStatus.REJECTED, "refused"),
            (AdStatus.DELETED, "refused"),
            (AdStatus.ARCHIVED, "refused"),
        ],
    )
    def test_every_status_has_a_defined_outcome(
        self,
        seller,
        category,
        city,
        status: AdStatus,
        expected_outcome: str,
    ) -> None:
        """Every ``AdStatus`` maps to exactly one defined outcome.

        - ``direct_save``: 302 redirect and the new title persisted.
        - ``refused``: HTTP 200, actionable error, title unchanged.
        - ``published_branch``: 302 redirect to dashboard (price-only edit;
          title is unchanged so the price/photo branch is taken).
        """
        ad = create_test_ad(seller, category, city, status=status, price=100)
        Ad.objects.filter(pk=ad.pk).update(title="Original Title")
        new_title = "Enumerated New Title"
        client = Client()
        client.force_login(seller)

        response = client.post(
            reverse("ads:edit", args=[ad.id]),
            data={
                # Title change routes PUBLISHED to the text branch; for the
                # price-only published case below we override this.
                "title": new_title,
                "description": ad.description,
                "price_amount": "100",
                "price_currency": CurrencyCode.EUR.value,
            },
        )

        ad.refresh_from_db()
        if expected_outcome == "direct_save":
            assert response.status_code == 302
            assert ad.title == new_title
        elif expected_outcome == "refused":
            assert response.status_code == 200
            assert response.context["error"] == (
                "This ad cannot be edited in its current status."
            )
            assert ad.title == "Original Title"

    def test_published_takes_its_own_branch(self, seller, category, city) -> None:
        """PUBLISHED is handled by its own branch, never the allow-list.

        A price-only edit on a PUBLISHED ad stays PUBLISHED (the price/photo
        sub-branch), proving the allow-list refused/enumerated statuses do not
        capture PUBLISHED.
        """
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED, price=100)
        client = Client()
        client.force_login(seller)

        response = client.post(
            reverse("ads:edit", args=[ad.id]),
            data={
                "title": ad.title,
                "description": ad.description,
                "price_amount": "200",
                "price_currency": CurrencyCode.EUR.value,
            },
        )

        assert response.status_code == 302
        assert "dashboard" in response.url
        ad.refresh_from_db()
        assert ad.status == AdStatus.PUBLISHED


# ---------------------------------------------------------------------------
# AD-002 / 8A: dashboard Edit link is gated by the same allow-list
# ---------------------------------------------------------------------------


class TestDashboardEditLinkGate:
    """The dashboard renders the Edit link exactly for allow-listed statuses.

    The link must be present for ``DRAFT``/``ON_MODERATION`` and absent for
    ``ON_MODERATION_FAILED``/``REJECTED``/``ARCHIVED``, matching
    ``EDITABLE_DIRECT_SAVE_STATUSES``.
    """

    def _edit_url(self, ad: Ad) -> str:
        return reverse("ads:edit", args=[ad.id])

    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            (AdStatus.ON_MODERATION, True),
            (AdStatus.PUBLISHED, False),
            (AdStatus.ON_MODERATION_FAILED, False),
            (AdStatus.REJECTED, False),
            (AdStatus.ARCHIVED, False),
        ],
    )
    def test_edit_link_presence_per_status(
        self,
        seller,
        category,
        city,
        status: AdStatus,
        expected: bool,
    ) -> None:
        """The Edit link is present iff the status is in the allow-list.

        The gate is driven by the **same** ``EDITABLE_DIRECT_SAVE_STATUSES``
        set the view enforces, so among the dashboard's buckets only
        ``ON_MODERATION`` shows the link. ``PUBLISHED`` and ``ARCHIVED`` retain
        their own action affordances (price/photo edits and reactivation) and
        the view branches for them are untouched; the link gate itself follows
        the allow-list exactly, per AD-002 / BLOCK 8A acceptance criterion 4.
        ``DRAFT`` is not a dashboard bucket, so it is covered by the view tests
        instead of the rendered dashboard.
        """
        ad = create_test_ad(seller, category, city, status=status, price=100)
        client = Client()
        client.force_login(seller)

        response = client.get(reverse("ads:dashboard"))
        assert response.status_code == 200
        rendered = response.content.decode()
        edit_url = self._edit_url(ad)

        if expected:
            assert f'href="{edit_url}"' in rendered
        else:
            assert f'href="{edit_url}"' not in rendered


# ---------------------------------------------------------------------------
# Known gap (04-AUT-002, G-A) — a banned seller can archive and relist an ad
# ---------------------------------------------------------------------------


class TestBannedSellerRelistKnownGap:
    """Pin that a banned seller's ad can return to PUBLISHED through the real
    relist chain (``ad_archive`` -> ``ad_reactivate`` -> real ``auto_moderate``).

    Known gap: ``ad_edit`` and ``ad_reactivate`` have NO account-state check, and
    ``apps.moderation.services.auto_moderation.auto_moderate`` never reads
    ``is_banned`` — it consults ``ModerationCriteria`` only. A ban that lets the
    seller relist is not a ban. This test asserts the CURRENT, DEFECTIVE
    behaviour; it is a red-to-green specification for phase 15's
    ``15-AUTHZ-001`` and turns red the moment ``ad_edit``/``ad_reactivate`` gain
    an account-state check or ``auto_moderate`` starts reading ``is_banned``.

    Owner of the fix: phase 15, ``15-AUTHZ-001``. Produced by B-07 gate G-A.
    """

    def test_banned_seller_can_archive_and_reactivate_an_ad(
        self,
        seller,
        category,
        city,
        permissive_criteria,
    ) -> None:
        """A banned seller archives then reactivates a PUBLISHED ad; the real
        ``auto_moderate`` returns it to PUBLISHED.

        The ban is applied AFTER login so a live session drives the chain, and
        ``auto_moderate`` is NOT mocked: its failure to read ``is_banned`` is the
        point of the test. Asserts on the ad's final status only.
        """
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        client = Client()
        client.force_login(seller)
        assert "_auth_user_id" in client.session

        # Ban the seller while the session is live.
        seller.is_banned = True
        seller.save(update_fields=["is_banned"])
        seller.refresh_from_db()
        assert seller.is_banned is True

        # Archive the ad (PUBLISHED -> ARCHIVED).
        archive_response = client.post(reverse("ads:archive", args=[ad.id]))
        assert archive_response.status_code == 302
        ad.refresh_from_db()
        assert ad.status == AdStatus.ARCHIVED

        # Reactivate it: the view transitions ARCHIVED -> ON_MODERATION and then
        # calls the real ``auto_moderate``, which does not read ``is_banned``.
        reactivate_response = client.post(reverse("ads:reactivate", args=[ad.id]))
        assert reactivate_response.status_code == 302

        ad.refresh_from_db()
        # Known gap (G-A): the banned seller's ad is PUBLISHED again.
        assert ad.status == AdStatus.PUBLISHED
        assert ad.published_at is not None

