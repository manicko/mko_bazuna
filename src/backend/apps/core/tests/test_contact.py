"""
Tests for contact service render conditions (zone R2).

Tests the real can_contact_seller predicate using persisted User+Ad fixtures.
"""

from types import SimpleNamespace

import pytest
from telegram_bot.handlers.contact import CONTACT_PATTERN
from apps.ads.models import Ad
from apps.core.enums import AdStatus
from apps.core.services.contact import (
    _check_seller_contactable,
    can_contact_seller,
    get_seller_for_contact,
    record_contact_response,
)
from apps.users.models import User
from django.utils import timezone

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


@pytest.fixture
def seller() -> User:
    """Create a seller user for ad fixtures."""
    return User.objects.create(
        telegram_id=900000001,
        chat_id=900000001,
        password="x",
    )


@pytest.fixture
def category():
    """Create a leaf category for ad fixtures."""
    from apps.categories.models import Category

    return Category.objects.create(
        name="Test Category",
        slug="test-category",
    )


@pytest.fixture
def city():
    """Create a city for ad fixtures."""
    from apps.locations.models import City

    return City.objects.create(
        country_code="ME",
        name="Test City",
        region="Test Region",
        slug="test-city",
    )


def _set_status_timestamp(data, now=None):
    """Auto-populate timestamp fields matching the ad status."""
    from django.utils import timezone
    from apps.core.enums import AdStatus

    if now is None:
        now = timezone.now()
    status = data.get("status")
    if status == AdStatus.PUBLISHED:
        data.setdefault("published_at", now)
        data.setdefault("original_published_at", now)
    elif status == AdStatus.ARCHIVED:
        data.setdefault("archived_at", now)
        data.setdefault("published_at", now)
        data.setdefault("original_published_at", now)
    elif status == AdStatus.REJECTED:
        data.setdefault("rejected_at", now)
    elif status == AdStatus.ON_MODERATION_FAILED:
        data.setdefault("moderation_failed_at", now)
    elif status == AdStatus.DELETED:
        data.setdefault("deleted_at", now)
    return data


def _make_ad(seller, category, city, **kwargs) -> Ad:
    """Create an Ad with required FK fields, overriding any kwargs."""
    defaults = {
        "user": seller,
        "title": "Valid Title",
        "description": "Valid description text",
        "category": category,
        "city": city,
        "category_name": category.name,
        "status": AdStatus.PUBLISHED,
    }
    defaults.update(kwargs)
    _set_status_timestamp(defaults)
    return Ad.objects.create(**defaults)


class TestCanContactSellerLogic:
    """Tests for can_contact_seller render condition logic (zone R2)."""

    def test_all_conditions_true_returns_true(self, seller, category, city):
        """All 5 R2 conditions true -> can_contact_seller returns True."""
        ad = _make_ad(seller, category, city)
        assert can_contact_seller(ad) is True

    def test_archived_ad_returns_false(self, seller, category, city):
        """ARCHIVED/non-PUBLISHED ad -> can_contact_seller returns False."""
        ad = _make_ad(seller, category, city, status=AdStatus.ARCHIVED)
        assert can_contact_seller(ad) is False

    def test_draft_ad_returns_false(self, seller, category, city):
        """DRAFT status -> can_contact_seller returns False."""
        ad = _make_ad(seller, category, city, status=AdStatus.DRAFT)
        assert can_contact_seller(ad) is False

    def test_on_moderation_ad_returns_false(self, seller, category, city):
        """ON_MODERATION status -> can_contact_seller returns False."""
        ad = _make_ad(seller, category, city, status=AdStatus.ON_MODERATION)
        assert can_contact_seller(ad) is False

    def test_rejected_ad_returns_false(self, seller, category, city):
        """REJECTED status -> can_contact_seller returns False."""
        ad = _make_ad(seller, category, city, status=AdStatus.REJECTED)
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
        ad = _make_ad(seller, category, city)
        assert can_contact_seller(ad) is False

    def test_seller_banned_returns_false(self, seller, category, city):
        """Seller is_banned flag -> can_contact_seller returns False."""
        seller.is_banned = True
        seller.save(update_fields=["is_banned"])
        ad = _make_ad(seller, category, city)
        assert can_contact_seller(ad) is False

    def test_consent_revoked_returns_false(self, seller, category, city):
        """Seller consent_revoked_at set -> can_contact_seller returns False."""
        seller.consent_revoked_at = timezone.now()
        seller.save(update_fields=["consent_revoked_at"])
        ad = _make_ad(seller, category, city)
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
    """Direct unit tests for the _check_seller_contactable predicate (zone R2).

    Happy path plus each of the 6 conditions failing -> False.
    """

    def test_all_conditions_met_returns_true(self, seller, category, city):
        """All 6 conditions satisfied -> predicate returns True."""
        ad = _make_ad(seller, category, city)
        assert _check_seller_contactable(ad, seller) is True

    @pytest.mark.parametrize(
        "status",
        [AdStatus.DRAFT, AdStatus.ON_MODERATION, AdStatus.ARCHIVED, AdStatus.REJECTED],
    )
    def test_ad_not_published_returns_false(self, seller, category, city, status):
        """ad.status != PUBLISHED -> predicate returns False."""
        ad = _make_ad(seller, category, city, status=status)
        assert _check_seller_contactable(ad, seller) is False

    def test_seller_is_none_returns_false(self):
        """seller is None -> predicate returns False (defensive)."""
        ad = SimpleNamespace(status=AdStatus.PUBLISHED)
        assert _check_seller_contactable(ad, None) is False

    def test_telegram_id_none_returns_false(self):
        """seller with telegram_id is None -> predicate returns False."""
        ad = SimpleNamespace(status=AdStatus.PUBLISHED)
        seller = SimpleNamespace(
            telegram_id=None,
            is_deleted=False,
            is_banned=False,
            consent_revoked_at=None,
        )
        assert _check_seller_contactable(ad, seller) is False

    def test_seller_deleted_returns_false(self, seller, category, city):
        """seller.is_deleted -> predicate returns False."""
        seller.is_deleted = True
        seller.save(update_fields=["is_deleted"])
        ad = _make_ad(seller, category, city)
        assert _check_seller_contactable(ad, seller) is False

    def test_seller_banned_returns_false(self, seller, category, city):
        """seller.is_banned -> predicate returns False."""
        seller.is_banned = True
        seller.save(update_fields=["is_banned"])
        ad = _make_ad(seller, category, city)
        assert _check_seller_contactable(ad, seller) is False

    def test_consent_revoked_returns_false(self, seller, category, city):
        """seller.consent_revoked_at set -> predicate returns False."""
        seller.consent_revoked_at = timezone.now()
        seller.save(update_fields=["consent_revoked_at"])
        ad = _make_ad(seller, category, city)
        assert _check_seller_contactable(ad, seller) is False


class TestGetSellerForContactIntegration:
    """Integration tests for get_seller_for_contact delegating to the predicate.

    Returns (True, seller) on the happy path and (False, None) per violation
    (plus the ad-not-found case handled before the predicate runs).
    """

    def test_returns_seller_when_contactable(self, seller, category, city):
        """Published ad + contactable seller -> (True, seller)."""
        ad = _make_ad(seller, category, city)
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
        ad = _make_ad(seller, category, city, status=status)
        assert get_seller_for_contact(ad.id) == (False, None)

    def test_returns_false_none_when_seller_deleted(self, seller, category, city):
        """Deleted seller -> (False, None)."""
        seller.is_deleted = True
        seller.save(update_fields=["is_deleted"])
        ad = _make_ad(seller, category, city)
        assert get_seller_for_contact(ad.id) == (False, None)

    def test_returns_false_none_when_seller_banned(self, seller, category, city):
        """Banned seller -> (False, None)."""
        seller.is_banned = True
        seller.save(update_fields=["is_banned"])
        ad = _make_ad(seller, category, city)
        assert get_seller_for_contact(ad.id) == (False, None)

    def test_returns_false_none_when_consent_revoked(self, seller, category, city):
        """Consent revoked -> (False, None)."""
        seller.consent_revoked_at = timezone.now()
        seller.save(update_fields=["consent_revoked_at"])
        ad = _make_ad(seller, category, city)
        assert get_seller_for_contact(ad.id) == (False, None)
