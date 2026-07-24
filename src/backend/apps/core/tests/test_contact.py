"""
Tests for contact service render conditions (zone R2).

Tests the real can_contact_seller predicate using persisted User+Ad fixtures.
"""

import pytest
from telegram_bot.handlers.contact import CONTACT_PATTERN
from apps.ads.models import Ad
from apps.core.enums import AdStatus
from apps.core.services.contact import can_contact_seller
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