"""
Tests for auto-moderation service via public API (check() + auto_moderate()).

All tests exercise the public API rather than private validation helpers.
Validation rules (title/description length, image count, banned words,
max-ads-per-user) are tested through check(); side effects (status transitions,
AnalyticsEvent creation) are tested through auto_moderate().
"""

import pytest
from django.core.cache import cache

from apps.ads.models import AdImage
from apps.analytics.models import AnalyticsEvent
from apps.core.enums import AdStatus, AnalyticsEventType
from apps.moderation.models import ModerationCriteria, ModeratorActionLog
from apps.moderation.services.auto_moderation import auto_moderate, check

from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

SELLER_SAFE_ERROR = (
    "Your ad content does not meet our requirements. Please review and try again."
)


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


def _create_valid_ad(user, category, city, **kwargs):
    """Create an Ad that passes all default-criteria checks, with 2 images."""
    defaults = {
        "title": "Valid Title",
        "description": "Valid description text here",
    }
    defaults.update(kwargs)
    ad = create_test_ad(user, category, city, **defaults)
    AdImage.objects.create(ad=ad, image="img0.jpg", position=0)
    AdImage.objects.create(ad=ad, image="img1.jpg", position=1)
    return ad


# ---------------------------------------------------------------------------
# check() — return tuple and read-only semantics
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestCheckFunction:
    """Tests for check() return tuples and read-only semantics."""

    @pytest.fixture(autouse=True)
    def _setup(self, moderation_criteria, user, category, city):
        self.criteria = moderation_criteria
        self.user = user
        self.category = category
        self.city = city

    def test_check_returns_passed_on_valid_ad(self):
        """check() returns (True, None) when all validations pass."""
        ad = _create_valid_ad(self.user, self.category, self.city)

        passed, error = check(ad)
        assert passed is True
        assert error is None

    def test_check_returns_seller_safe_error_on_fail(self):
        """check() returns (False, generic_error) on validation failure.

        The error message must be seller-safe: no specific reason, no field name.
        check() must be read-only: no status transition or side-effects.
        """
        ad = create_test_ad(
            self.user,
            self.category,
            self.city,
            title="abc",
            description="Valid description text here",
        )
        AdImage.objects.create(ad=ad, image="img0.jpg", position=0)

        passed, error = check(ad)
        assert passed is False
        assert error == SELLER_SAFE_ERROR

        # check() must be read-only: no status transition or side-effects
        ad.refresh_from_db()
        assert ad.status == AdStatus.ON_MODERATION
        assert ModeratorActionLog.objects.count() == 0
        assert AnalyticsEvent.objects.count() == 0

    def test_over_limit_user_fails_check(self):
        """User exceeding max_ads_per_user fails check()."""
        self.criteria.max_ads_per_user = 2
        self.criteria.save()

        # Two PUBLISHED ads already at the limit of 2.
        create_test_ad(
            self.user,
            self.category,
            self.city,
            title="First Published Ad",
            description="Valid description text here",
            status=AdStatus.PUBLISHED,
        )
        create_test_ad(
            self.user,
            self.category,
            self.city,
            title="Second Published Ad",
            description="Valid description text here",
            status=AdStatus.PUBLISHED,
        )

        # New submission in ON_MODERATION — counted as active, pushing total to 3.
        ad = _create_valid_ad(
            self.user,
            self.category,
            self.city,
            title="New Submission Ad",
        )

        passed, error = check(ad)
        assert passed is False
        assert error == SELLER_SAFE_ERROR

    def test_failed_ad_not_counted_in_active_limit(self):
        """ON_MODERATION_FAILED ads do not count toward the active-ads limit (AD-003).

        With max_ads=2, a user with 1 PUBLISHED + 1 ON_MODERATION_FAILED has
        only 1 active ad. check() on a new DRAFT ad (not counted) returns
        (True, None). If ON_MODERATION_FAILED were counted, the active count
        would be 2 and 2 < 2 would be False.
        """
        self.criteria.max_ads_per_user = 2
        self.criteria.save()

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

        # New ad in DRAFT — not counted toward active (PUBLISHED + ON_MODERATION).
        ad = _create_valid_ad(
            self.user,
            self.category,
            self.city,
            title="New Valid Ad Title",
            status=AdStatus.DRAFT,
        )

        passed, error = check(ad)
        assert passed is True
        assert error is None


# ---------------------------------------------------------------------------
# check() — title length validation
# ---------------------------------------------------------------------------


class TestValidateTitleLength:
    """Tests for title length validation through check()."""

    @pytest.fixture(autouse=True)
    def _setup(self, moderation_criteria, user, category, city):
        self.criteria = moderation_criteria
        self.user = user
        self.category = category
        self.city = city

    def test_title_too_short_returns_false(self):
        """Title below minimum length causes check() to return (False, ...)."""
        ad = _create_valid_ad(self.user, self.category, self.city, title="abc")

        passed, error = check(ad)
        assert passed is False
        assert error == SELLER_SAFE_ERROR

    def test_title_too_long_returns_false(self):
        """Title above maximum length causes check() to return (False, ...)."""
        ad = _create_valid_ad(self.user, self.category, self.city, title="x" * 150)

        passed, error = check(ad)
        assert passed is False
        assert error == SELLER_SAFE_ERROR

    def test_title_min_boundary_returns_true(self):
        """Title at minimum length passes check()."""
        ad = _create_valid_ad(self.user, self.category, self.city, title="abcde")

        passed, error = check(ad)
        assert passed is True
        assert error is None

    def test_title_max_boundary_returns_true(self):
        """Title at maximum length passes check()."""
        ad = _create_valid_ad(self.user, self.category, self.city, title="x" * 100)

        passed, error = check(ad)
        assert passed is True
        assert error is None

    def test_title_within_range_returns_true(self):
        """Title within valid range passes check()."""
        ad = _create_valid_ad(self.user, self.category, self.city, title="Valid Title")

        passed, error = check(ad)
        assert passed is True
        assert error is None


# ---------------------------------------------------------------------------
# check() — description length validation
# ---------------------------------------------------------------------------


class TestValidateDescriptionLength:
    """Tests for description length validation through check()."""

    @pytest.fixture(autouse=True)
    def _setup(self, moderation_criteria, user, category, city):
        self.criteria = moderation_criteria
        self.user = user
        self.category = category
        self.city = city

    def test_description_too_short_returns_false(self):
        """Description below minimum length causes check() to return (False, ...)."""
        ad = _create_valid_ad(
            self.user, self.category, self.city, description="short"
        )

        passed, error = check(ad)
        assert passed is False
        assert error == SELLER_SAFE_ERROR

    def test_description_too_long_returns_false(self):
        """Description above maximum length causes check() to return (False, ...)."""
        ad = _create_valid_ad(
            self.user, self.category, self.city, description="x" * 2500
        )

        passed, error = check(ad)
        assert passed is False
        assert error == SELLER_SAFE_ERROR

    def test_description_min_boundary_returns_true(self):
        """Description at minimum length passes check()."""
        ad = _create_valid_ad(
            self.user, self.category, self.city, description="x" * 10
        )

        passed, error = check(ad)
        assert passed is True
        assert error is None

    def test_description_max_boundary_returns_true(self):
        """Description at maximum length passes check()."""
        ad = _create_valid_ad(
            self.user, self.category, self.city, description="x" * 2000
        )

        passed, error = check(ad)
        assert passed is True
        assert error is None


# ---------------------------------------------------------------------------
# check() — image count validation
# ---------------------------------------------------------------------------


class TestValidateImageCount:
    """Tests for image count validation through check()."""

    @pytest.fixture(autouse=True)
    def _setup(self, moderation_criteria, user, category, city):
        self.criteria = moderation_criteria
        self.user = user
        self.category = category
        self.city = city

    def test_no_images_returns_false(self):
        """No images causes check() to return (False, ...)."""
        ad = create_test_ad(
            self.user,
            self.category,
            self.city,
            title="Valid Title",
            description="Valid description text here",
        )

        passed, error = check(ad)
        assert passed is False
        assert error == SELLER_SAFE_ERROR

    def test_too_many_images_returns_false(self):
        """Too many images (>max_images) causes check() to return (False, ...)."""
        ad = create_test_ad(
            self.user,
            self.category,
            self.city,
            title="Valid Title",
            description="Valid description text here",
        )
        for i in range(7):
            AdImage.objects.create(ad=ad, image=f"img{i}.jpg", position=i)

        passed, error = check(ad)
        assert passed is False
        assert error == SELLER_SAFE_ERROR

    def test_valid_image_count_returns_true(self):
        """Valid image count (within [min, max]) passes check()."""
        ad = create_test_ad(
            self.user,
            self.category,
            self.city,
            title="Valid Title",
            description="Valid description text here",
        )
        for i in range(3):
            AdImage.objects.create(ad=ad, image=f"img{i}.jpg", position=i)

        passed, error = check(ad)
        assert passed is True
        assert error is None


# ---------------------------------------------------------------------------
# check() — banned words validation
# ---------------------------------------------------------------------------


class TestContainsBannedWords:
    """Tests for banned words validation through check()."""

    @pytest.fixture(autouse=True)
    def _setup(self, moderation_criteria, user, category, city):
        self.criteria = moderation_criteria
        self.user = user
        self.category = category
        self.city = city

    def test_banned_word_in_title_returns_false(self):
        """Banned word in title causes check() to return (False, ...)."""
        self.criteria.banned_words = ["spam", "scam"]
        self.criteria.save()
        ad = _create_valid_ad(self.user, self.category, self.city, title="Spammy Title")

        passed, error = check(ad)
        assert passed is False
        assert error == SELLER_SAFE_ERROR

    def test_banned_word_in_description_returns_false(self):
        """Banned word in description causes check() to return (False, ...)."""
        self.criteria.banned_words = ["spam", "scam"]
        self.criteria.save()
        ad = _create_valid_ad(
            self.user, self.category, self.city, description="This is a scam"
        )

        passed, error = check(ad)
        assert passed is False
        assert error == SELLER_SAFE_ERROR

    def test_banned_word_case_insensitive_returns_false(self):
        """Banned word matching is case-insensitive in check()."""
        self.criteria.banned_words = ["spam", "scam"]
        self.criteria.save()
        ad = _create_valid_ad(self.user, self.category, self.city, title="SPAM Title")

        passed, error = check(ad)
        assert passed is False
        assert error == SELLER_SAFE_ERROR

    def test_no_banned_words_returns_true(self):
        """Ad without banned words passes check()."""
        self.criteria.banned_words = ["spam", "scam"]
        self.criteria.save()
        ad = _create_valid_ad(
            self.user,
            self.category,
            self.city,
            title="Clean Title",
            description="Clean description here",
        )

        passed, error = check(ad)
        assert passed is True
        assert error is None

    def test_empty_banned_words_returns_true(self):
        """Empty banned words list allows any content through check()."""
        self.criteria.banned_words = []
        self.criteria.save()
        ad = _create_valid_ad(
            self.user,
            self.category,
            self.city,
            title="Any Title With spam",
            description="Any description",
        )

        passed, error = check(ad)
        assert passed is True
        assert error is None


# ---------------------------------------------------------------------------
# auto_moderate() — side effects: status transitions and AnalyticsEvent
# ---------------------------------------------------------------------------


class TestAutoModerateFunction:
    """Tests for auto_moderate() side effects: status transitions and analytics."""

    @pytest.fixture(autouse=True)
    def _setup(self, moderation_criteria, user, category, city):
        self.criteria = moderation_criteria
        self.user = user
        self.category = category
        self.city = city

    def test_auto_moderate_pass_sets_published_and_analytics(self):
        """auto_moderate() on a valid ad sets PUBLISHED + creates analytics events."""
        ad = _create_valid_ad(self.user, self.category, self.city)

        result = auto_moderate(ad)
        assert result is True

        ad.refresh_from_db()
        assert ad.status == AdStatus.PUBLISHED
        assert ad.published_at is not None

        event_types = set(
            AnalyticsEvent.objects.values_list("event_type", flat=True)
        )
        assert AnalyticsEventType.AD_PUBLISHED in event_types
        assert AnalyticsEventType.MODERATION_APPROVED in event_types

    def test_auto_moderate_fail_sets_failed_status_and_analytics(self):
        """auto_moderate() on an invalid ad sets ON_MODERATION_FAILED + creates analytics."""
        ad = create_test_ad(
            self.user,
            self.category,
            self.city,
            title="abc",
            description="Valid description text here",
        )
        AdImage.objects.create(ad=ad, image="img0.jpg", position=0)

        result = auto_moderate(ad)
        assert result is False

        ad.refresh_from_db()
        assert ad.status == AdStatus.ON_MODERATION_FAILED
        assert ad.moderation_failed_at is not None

        event_types = set(
            AnalyticsEvent.objects.values_list("event_type", flat=True)
        )
        assert AnalyticsEventType.MODERATION_REJECTED in event_types
        assert len(event_types) == 1
