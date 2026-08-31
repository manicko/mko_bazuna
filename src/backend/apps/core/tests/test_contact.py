"""
Tests for contact service render conditions (zone R2).

Tests the real can_contact_seller predicate using persisted User+Ad fixtures.
"""

from types import SimpleNamespace

import pytest
from apps.core.enums import AdStatus
from apps.core.services.contact import (
    can_contact_seller,
    get_seller_for_contact,
    record_contact_response,
)
from conftest import create_test_ad
from django.utils import timezone
from telegram_bot.handlers.contact import CONTACT_PATTERN

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


class TestCanContactSellerLogic:
    """Tests for can_contact_seller render condition logic (zone R2)."""

    def test_all_conditions_true_returns_true(self, seller, category, city):
        """All 5 R2 conditions true -> can_contact_seller returns True."""
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        assert can_contact_seller(ad) is True

    def test_archived_ad_returns_false(self, seller, category, city):
        """ARCHIVED/non-PUBLISHED ad -> can_contact_seller returns False."""
        ad = create_test_ad(seller, category, city, status=AdStatus.ARCHIVED)
        assert can_contact_seller(ad) is False

    def test_draft_ad_returns_false(self, seller, category, city):
        """DRAFT status -> can_contact_seller returns False."""
        ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)
        assert can_contact_seller(ad) is False

    def test_on_moderation_ad_returns_false(self, seller, category, city):
        """ON_MODERATION status -> can_contact_seller returns False."""
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)
        assert can_contact_seller(ad) is False

    def test_rejected_ad_returns_false(self, seller, category, city):
        """REJECTED status -> can_contact_seller returns False."""
        ad = create_test_ad(seller, category, city, status=AdStatus.REJECTED)
        assert can_contact_seller(ad) is False

    def test_telegram_id_none_returns_false(self):
        """Seller telegram_id is None OR seller is None -> can_contact_seller returns False.

        Note: The User model enforces telegram_id NOT NULL and the Ad model
        enforces user NOT NULL, but the function has defensive checks. We exercise
        these paths via mock objects to test the actual function logic without
        DB constraint changes.
        """

        class MockSeller:
            telegram_id = None
            is_deleted = False
            is_banned = False
            consent_revoked_at = None

        class MockAdWithSellerNone:
            status = AdStatus.PUBLISHED
            user = None

        class MockAdWithTelegramIdNone:
            status = AdStatus.PUBLISHED
            user = MockSeller()

        # Test seller is None returns False
        assert can_contact_seller(MockAdWithSellerNone()) is False
        # Test telegram_id is None returns False
        assert can_contact_seller(MockAdWithTelegramIdNone()) is False

    def test_seller_deleted_returns_false(self, seller, category, city):
        """Seller is_deleted flag -> can_contact_seller returns False."""
        seller.is_deleted = True
        seller.save(update_fields=["is_deleted"])
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        assert can_contact_seller(ad) is False

    def test_seller_banned_returns_false(self, seller, category, city):
        """Seller is_banned flag -> can_contact_seller returns False."""
        seller.is_banned = True
        seller.save(update_fields=["is_banned"])
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        assert can_contact_seller(ad) is False

    def test_consent_revoked_returns_false(self, seller, category, city):
        """Seller consent_revoked_at set -> can_contact_seller returns False."""
        seller.consent_revoked_at = timezone.now()
        seller.save(update_fields=["consent_revoked_at"])
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        assert can_contact_seller(ad) is False


class TestContactPattern:
    """Tests for contact deep-link pattern matching (from bot handler)."""

    def test_contact_pattern_matches_ad_id(self):
        """Contact pattern matches contact_<ad_id> format."""
        # Valid patterns
        assert CONTACT_PATTERN.match("contact_123") is not None
        assert CONTACT_PATTERN.match("contact_1") is not None
        assert CONTACT_PATTERN.match("contact_999999") is not None

        # Invalid patterns
        assert CONTACT_PATTERN.match("login_abc123") is None
        assert CONTACT_PATTERN.match("contact_abc") is None
        assert CONTACT_PATTERN.match("contact_123abc") is None

    def test_contact_pattern_extracts_ad_id(self):
        """Contact pattern correctly extracts ad_id from deep-link."""
        match = CONTACT_PATTERN.match("contact_456")
        assert match is not None
        assert int(match.group(1)) == 456


class TestContactResponseNoPii:
    """Tests that record_contact_response does not leak raw telegram_id in logs (PII-002)."""

    def test_contact_no_seller_no_pii_in_log(self, caplog) -> None:
        """Calling record_contact_response with non-existent seller must not log raw telegram_id."""
        with caplog.at_level("WARNING"):
            record_contact_response(seller_telegram_id=999999)

        # Raw telegram_id must not appear in any log output
        assert "999999" not in caplog.text
        # Masked value should be present for log correlation
        assert "tg_" in caplog.text


class TestCheckSellerContactable:
    """Tests for the contactable predicate via the public ``can_contact_seller``
    and ``get_seller_for_contact`` APIs (zone R2).

    Happy path plus each of the 6 conditions failing -> False.
    """

    def test_all_conditions_met_returns_true(self, seller, category, city):
        """All 6 conditions satisfied -> predicate returns True."""
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        assert can_contact_seller(ad) is True
        assert get_seller_for_contact(ad.id) == (True, seller)

    @pytest.mark.parametrize(
        "status",
        [AdStatus.DRAFT, AdStatus.ON_MODERATION, AdStatus.ARCHIVED, AdStatus.REJECTED],
    )
    def test_ad_not_published_returns_false(self, seller, category, city, status):
        """ad.status != PUBLISHED -> predicate returns False."""
        ad = create_test_ad(seller, category, city, status=status)
        assert can_contact_seller(ad) is False
        assert get_seller_for_contact(ad.id) == (False, None)

    def test_seller_is_none_returns_false(self):
        """seller is None -> predicate returns False (defensive)."""
        ad = SimpleNamespace(status=AdStatus.PUBLISHED, user=None)
        assert can_contact_seller(ad) is False

    def test_telegram_id_none_returns_false(self):
        """seller with telegram_id is None -> predicate returns False."""
        seller = SimpleNamespace(
            telegram_id=None,
            is_deleted=False,
            is_banned=False,
            consent_revoked_at=None,
        )
        ad = SimpleNamespace(status=AdStatus.PUBLISHED, user=seller)
        assert can_contact_seller(ad) is False

    def test_seller_deleted_returns_false(self, seller, category, city):
        """seller.is_deleted -> predicate returns False."""
        seller.is_deleted = True
        seller.save(update_fields=["is_deleted"])
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        assert can_contact_seller(ad) is False
        assert get_seller_for_contact(ad.id) == (False, None)

    def test_seller_banned_returns_false(self, seller, category, city):
        """seller.is_banned -> predicate returns False."""
        seller.is_banned = True
        seller.save(update_fields=["is_banned"])
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        assert can_contact_seller(ad) is False
        assert get_seller_for_contact(ad.id) == (False, None)

    def test_consent_revoked_returns_false(self, seller, category, city):
        """seller.consent_revoked_at set -> predicate returns False."""
        seller.consent_revoked_at = timezone.now()
        seller.save(update_fields=["consent_revoked_at"])
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        assert can_contact_seller(ad) is False
        assert get_seller_for_contact(ad.id) == (False, None)


class TestGetSellerForContactIntegration:
    """Integration tests for get_seller_for_contact delegating to the predicate.

    Returns (True, seller) on the happy path and (False, None) per violation
    (plus the ad-not-found case handled before the predicate runs).
    """

    def test_returns_seller_when_contactable(self, seller, category, city):
        """Published ad + contactable seller -> (True, seller)."""
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        assert get_seller_for_contact(ad.id) == (True, seller)

    def test_returns_false_none_when_ad_not_found(self):
        """Non-existent ad id -> (False, None)."""
        assert get_seller_for_contact(999999) == (False, None)

    @pytest.mark.parametrize(
        "status",
        [AdStatus.DRAFT, AdStatus.ON_MODERATION, AdStatus.ARCHIVED, AdStatus.REJECTED],
    )
    def test_returns_false_none_when_not_published(
        self, seller, category, city, status
    ):
        """Non-PUBLISHED ad -> (False, None)."""
        ad = create_test_ad(seller, category, city, status=status)
        assert get_seller_for_contact(ad.id) == (False, None)

    def test_returns_false_none_when_seller_deleted(self, seller, category, city):
        """Deleted seller -> (False, None)."""
        seller.is_deleted = True
        seller.save(update_fields=["is_deleted"])
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        assert get_seller_for_contact(ad.id) == (False, None)

    def test_returns_false_none_when_seller_banned(self, seller, category, city):
        """Banned seller -> (False, None)."""
        seller.is_banned = True
        seller.save(update_fields=["is_banned"])
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        assert get_seller_for_contact(ad.id) == (False, None)

    def test_returns_false_none_when_consent_revoked(
        self, seller, category, city
    ) -> None:
        """Consent revoked -> (False, None)."""
        seller.consent_revoked_at = timezone.now()
        seller.save(update_fields=["consent_revoked_at"])
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        assert get_seller_for_contact(ad.id) == (False, None)


# ---------------------------------------------------------------------------
# Combinatorial edge cases (G-04)
# ---------------------------------------------------------------------------


class TestContactCombinatorial:
    """Cross-product tests for ``can_contact_seller`` and ``get_seller_for_contact``.

    Verifies that:
      (a) banned + consent WITHDRAWN both fail the predicate,
      (b) DECLINE (``is_declined``) does NOT block contact — only WITHDRAWN
          (``consent_revoked_at``) does,
      (c) ``get_seller_for_contact`` returns the correct ``(bool, User|None)``
          tuple across condition combinations.
    """

    @pytest.mark.parametrize(
        ("is_banned", "is_deleted", "revoked", "is_declined", "expected"),
        [
            # Happy path: all conditions clear -> contactable.
            (False, False, None, False, True),
            # Single failing condition.
            (True, False, None, False, False),
            (False, True, None, False, False),
            (False, False, timezone.now(), False, False),
            # Combined failures.
            (True, True, timezone.now(), False, False),
            (True, False, timezone.now(), False, False),
            # is_declined alone does NOT block contact (DISTINCT from consent_revoked_at).
            (False, False, None, True, True),
            # is_declined + consent_revoked → not contactable (revoked dominates).
            (False, False, timezone.now(), True, False),
            (True, False, timezone.now(), True, False),
        ],
        ids=[
            "all_clear",
            "banned",
            "deleted",
            "revoked",
            "banned+deleted+revoked",
            "banned+revoked",
            "declined_only_contactable",
            "declined+revoked",
            "declined+banned+revoked",
        ],
    )
    def test_can_contact_seller_cross_product(
        self,
        seller,
        category,
        city,
        is_banned: bool,
        is_deleted: bool,
        revoked,
        is_declined: bool,
        expected: bool,
    ) -> None:
        """``can_contact_seller`` correctly evaluates the cross-product of R2 conditions."""
        seller.is_banned = is_banned
        seller.is_deleted = is_deleted
        seller.is_declined = is_declined
        if revoked is not None:
            seller.consent_revoked_at = revoked
        seller.save(
            update_fields=[
                "is_banned",
                "is_deleted",
                "is_declined",
                "consent_revoked_at",
            ]
        )

        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        assert can_contact_seller(ad) is expected

    @pytest.mark.parametrize(
        ("is_banned", "revoked"),
        [
            (True, None),
            (False, timezone.now()),
            (True, timezone.now()),
        ],
        ids=["banned_only", "revoked_only", "banned_and_revoked"],
    )
    def test_get_seller_for_contact_return_tuple(
        self, seller, category, city, is_banned: bool, revoked
    ) -> None:
        """``get_seller_for_contact`` returns ``(False, None)`` when any R2 condition fails."""
        seller.is_banned = is_banned
        if revoked is not None:
            seller.consent_revoked_at = revoked
        seller.save(update_fields=["is_banned", "consent_revoked_at"])

        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        assert get_seller_for_contact(ad.id) == (False, None)

    def test_contactable_seller_return_tuple_contract(
        self, seller, category, city
    ) -> None:
        """When all conditions pass, ``get_seller_for_contact`` returns ``(True, seller)``."""
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        is_available, result_seller = get_seller_for_contact(ad.id)

        assert is_available is True
        assert result_seller == seller
