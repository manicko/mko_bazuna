"""
Tests for auto-moderation service validation functions.

Unit tests for validation rules without database dependencies.
"""

import pytest
from django.core.cache import cache

from apps.ads.models import AdImage
from apps.analytics.models import AnalyticsEvent
from apps.core.enums import AdStatus
from apps.moderation.models import ModeratorActionLog, ModerationCriteria
from apps.moderation.services.auto_moderation import (
    _contains_banned_words,
    _validate_description_length,
    _validate_image_count,
    _validate_max_ads_per_user,
    _validate_title_length,
    check,
)

from conftest import create_test_ad


class TestValidateTitleLength:
    """Tests for _validate_title_length function."""

    def test_title_too_short_returns_false(self):
        """Title below minimum length returns False."""
        result = _validate_title_length("abc", min_len=5, max_len=100)
        assert result is False

    def test_title_too_long_returns_false(self):
        """Title above maximum length returns False."""
        title = "x" * 150
        result = _validate_title_length(title, min_len=5, max_len=100)
        assert result is False

    def test_title_min_boundary_returns_true(self):
        """Title at minimum length returns True."""
        result = _validate_title_length("abcde", min_len=5, max_len=100)
        assert result is True

    def test_title_max_boundary_returns_true(self):
        """Title at maximum length returns True."""
        title = "x" * 100
        result = _validate_title_length(title, min_len=5, max_len=100)
        assert result is True

    def test_title_within_range_returns_true(self):
        """Title within valid range returns True."""
        result = _validate_title_length("Valid Title", min_len=5, max_len=100)
        assert result is True


class TestValidateDescriptionLength:
    """Tests for _validate_description_length function."""

    def test_description_too_short_returns_false(self):
        """Description below minimum length returns False."""
        result = _validate_description_length("short", min_len=10, max_len=2000)
        assert result is False

    def test_description_too_long_returns_false(self):
        """Description above maximum length returns False."""
        desc = "x" * 2500
        result = _validate_description_length(desc, min_len=10, max_len=2000)
        assert result is False

    def test_description_min_boundary_returns_true(self):
        """Description at minimum length returns True."""
        result = _validate_description_length("x" * 10, min_len=10, max_len=2000)
        assert result is True

    def test_description_max_boundary_returns_true(self):
        """Description at maximum length returns True."""
        desc = "x" * 2000
        result = _validate_description_length(desc, min_len=10, max_len=2000)
        assert result is True


class TestValidateImageCount:
    """Tests for _validate_image_count function."""

    def test_no_images_returns_false(self):
        """No images returns False when min_images=1."""

        class MockImagesQuerySet:
            def count(self):
                return 0

        class MockAd:
            @property
            def images(self):
                return MockImagesQuerySet()

        result = _validate_image_count(MockAd(), min_count=1, max_count=5)
        assert result is False

    def test_too_many_images_returns_false(self):
        """Too many images returns False."""

        class MockImagesQuerySet:
            def count(self):
                return 7

        class MockAd:
            @property
            def images(self):
                return MockImagesQuerySet()

        result = _validate_image_count(MockAd(), min_count=1, max_count=5)
        assert result is False

    def test_valid_image_count_returns_true(self):
        """Valid image count returns True."""

        class MockImagesQuerySet:
            def count(self):
                return 3

        class MockAd:
            @property
            def images(self):
                return MockImagesQuerySet()

        result = _validate_image_count(MockAd(), min_count=1, max_count=5)
        assert result is True


class TestContainsBannedWords:
    """Tests for _contains_banned_words function."""

    def test_banned_word_in_title_returns_true(self):
        """Banned word in title returns True."""
        result = _contains_banned_words("Spammy Title", "Description here", ("spam", "scam"))
        assert result is True

    def test_banned_word_in_description_returns_true(self):
        """Banned word in description returns True."""
        result = _contains_banned_words("Title here", "This is a scam", ("spam", "scam"))
        assert result is True

    def test_banned_word_case_insensitive_returns_true(self):
        """Banned word matching is case-insensitive."""
        result = _contains_banned_words("SPAM Title", "Description", ("spam", "scam"))
        assert result is True

    def test_no_banned_words_returns_false(self):
        """No banned words returns False."""
        result = _contains_banned_words("Normal Title", "Normal description", ("spam", "scam"))
        assert result is False

    def test_empty_banned_words_returns_false(self):
        """Empty banned words tuple returns False."""
        result = _contains_banned_words("Any Title", "Any description", ())
        assert result is False

@pytest.fixture
def moderation_criteria():
    """Create a ModerationCriteria singleton with default values."""
    cache.clear()
    criteria = ModerationCriteria.get_singleton()
    criteria.title_min_length = 5
    criteria.title_max_length = 100
    criteria.description_min_length = 10
    criteria.description_max_length = 2000
    criteria.price_required = True
    criteria.min_images = 1
    criteria.max_images = 5
    criteria.banned_words = []
    criteria.max_ads_per_user = 10
    criteria.duplicate_title_threshold = 85
    criteria.save()
    return criteria


@pytest.mark.django_db
@pytest.mark.slow
@pytest.mark.integration
class TestCheckFunction:
    """Tests for check() function with ORM-backed fixtures."""

    @pytest.fixture(autouse=True)
    def _setup(
        self,
        moderation_criteria,
        user,
        category,
        city,
    ):
        """Set up fixtures for each test."""
        self.criteria = moderation_criteria
        self.user = user
        self.category = category
        self.city = city

    def test_check_returns_passed_on_valid_ad(self):
        """Check returns (True, None) when all validations pass."""
        ad = create_test_ad(
            self.user,
            self.category,
            self.city,
            title="Valid Title",
            description="Valid description text here",
        )
        AdImage.objects.create(ad=ad, image="test.jpg", position=0)
        AdImage.objects.create(ad=ad, image="test2.jpg", position=1)

        passed, error = check(ad)
        assert passed is True
        assert error is None

    def test_check_returns_seller_safe_error_on_fail(self):
        """Check returns (False, generic_error) on validation failure - no specific reason."""
        ad = create_test_ad(
            self.user,
            self.category,
            self.city,
            title="abc",
            description="Valid description text here",
        )

        passed, error = check(ad)
        assert passed is False
        assert error is not None
        assert "does not meet our requirements" in error
        # Ensure no specific reason is exposed
        assert "too short" not in error.lower()
        assert "title" not in error.lower() or "ad content" in error.lower()

        # check() must be read-only: no status transition or audit/analytics side-effects
        assert ad.status != AdStatus.ON_MODERATION_FAILED
        assert ModeratorActionLog.objects.count() == 0
        assert AnalyticsEvent.objects.count() == 0

    def test_failed_ad_not_counted_in_active_limit(self):
        """ON_MODERATION_FAILED ads do not count toward the active-ads limit (AD-003)."""
        # 1 PUBLISHED (active) + 1 ON_MODERATION_FAILED (should be excluded).
        # With max_ads=2 and the failed ad excluded, only 1 active remains -> under limit.
        create_test_ad(
            self.user,
            self.category,
            self.city,
            title="Published Ad",
            description="Valid description text here",
            status=AdStatus.PUBLISHED,
        )
        create_test_ad(
            self.user,
            self.category,
            self.city,
            title="Failed Ad",
            description="Valid description text here",
            status=AdStatus.ON_MODERATION_FAILED,
        )

        # If ON_MODERATION_FAILED were counted, active count=2 and 2<2 would be False.
        assert _validate_max_ads_per_user(self.user.id, max_ads=2) is True
