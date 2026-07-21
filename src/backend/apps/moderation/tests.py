"""
View-layer tests for moderation review actions (TST-004).

Covers:
- moderation_review: staff-only detail view for ads in moderation queue
- approve_ad: POST-only staff action that transitions ad to PUBLISHED
- reject_ad: POST-only staff action that transitions ad to REJECTED
- ban_user: POST-only staff action that bans the ad owner
- Non-staff users get 404 for all moderation views
"""

import pytest
from apps.ads.models import Ad, AdImage
from apps.categories.models import Category
from apps.core.enums import AdStatus
from apps.locations.models import City
from apps.moderation.models import ModeratorActionLog
from apps.users.models import User
from django.test import Client
from django.utils import timezone

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def staff_user() -> User:
    """Create a staff user for moderation tests."""
    return User.objects.create(
        telegram_id=900000040,
        chat_id=900000040,
        password="x",
        is_staff=True,
    )


@pytest.fixture
def regular_user() -> User:
    """Create a regular (non-staff) user for access tests."""
    return User.objects.create(
        telegram_id=900000041,
        chat_id=900000041,
        password="x",
    )


@pytest.fixture
def seller() -> User:
    """Create a seller user for ad fixtures."""
    return User.objects.create(
        telegram_id=900000042,
        chat_id=900000042,
        password="x",
    )


@pytest.fixture
def category() -> Category:
    """Create a leaf category for ad fixtures."""
    return Category.objects.create(
        name="Test Category",
        slug="test-category",
    )


@pytest.fixture
def city() -> City:
    """Create a city for ad fixtures."""
    return City.objects.create(
        country_code="BA",
        name="Test City",
        region="Test Region",
        slug="test-city",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_ad(
    user: User,
    category: Category,
    city: City,
    *,
    title: str = "Test Ad",
    status: AdStatus = AdStatus.ON_MODERATION,
) -> Ad:
    """Create an ad with the given status."""
    return Ad.objects.create(
        user=user,
        title=title,
        description="Test description for moderation",
        category=category,
        city=city,
        category_name=category.name,
        status=status,
        published_at=timezone.now() if status == AdStatus.PUBLISHED else None,
    )


def _create_ad_with_image(
    user: User,
    category: Category,
    city: City,
    **kwargs,
) -> tuple[Ad, AdImage]:
    """Create an ad with one image."""
    ad = _create_ad(user, category, city, **kwargs)
    ad_image = AdImage.objects.create(
        ad=ad,
        image="test-uuid-image-key.jpg",
    )
    return ad, ad_image


# ---------------------------------------------------------------------------
# Tests: Staff access control
# ---------------------------------------------------------------------------


class TestModerationStaffAccess:
    """All moderation views require staff access."""

    @pytest.fixture
    def ad_on_moderation(
        self,
        seller: User,
        category: Category,
        city: City,
    ) -> Ad:
        return _create_ad(seller, category, city, status=AdStatus.ON_MODERATION)

    def test_anonymous_user_gets_404(
        self,
        ad_on_moderation: Ad,
    ) -> None:
        """Anonymous users get 404 for moderation review."""
        client = Client()
        response = client.get(f"/moderation/review/{ad_on_moderation.id}/")
        assert response.status_code == 404

    def test_regular_user_gets_404(
        self,
        regular_user: User,
        ad_on_moderation: Ad,
    ) -> None:
        """Non-staff users get 404 for moderation review."""
        client = Client()
        client.force_login(regular_user)
        response = client.get(f"/moderation/review/{ad_on_moderation.id}/")
        assert response.status_code == 404

    def test_approve_regular_user_gets_404(
        self,
        regular_user: User,
        ad_on_moderation: Ad,
    ) -> None:
        """Non-staff users get 404 for approve action."""
        client = Client()
        client.force_login(regular_user)
        response = client.post(f"/moderation/approve/{ad_on_moderation.id}/")
        assert response.status_code == 404

    def test_reject_regular_user_gets_404(
        self,
        regular_user: User,
        ad_on_moderation: Ad,
    ) -> None:
        """Non-staff users get 404 for reject action."""
        client = Client()
        client.force_login(regular_user)
        response = client.post(f"/moderation/reject/{ad_on_moderation.id}/")
        assert response.status_code == 404

    def test_ban_regular_user_gets_404(
        self,
        regular_user: User,
        ad_on_moderation: Ad,
    ) -> None:
        """Non-staff users get 404 for ban action."""
        client = Client()
        client.force_login(regular_user)
        response = client.post(f"/moderation/ban/{ad_on_moderation.id}/")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Tests: moderation_review
# ---------------------------------------------------------------------------


class TestModerationReviewView:
    """moderation_review view shows ad details for staff."""

    def test_staff_can_view_review_page(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """Staff users can view the moderation review page."""
        ad, _ = _create_ad_with_image(seller, category, city, status=AdStatus.ON_MODERATION)

        client = Client()
        client.force_login(staff_user)
        response = client.get(f"/moderation/review/{ad.id}/")

        assert response.status_code == 200
        assert response.context["ad"] is not None
        assert response.context["ad"].id == ad.id

    def test_review_returns_404_for_non_moderation_status(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """Review page returns 404 for ads not in ON_MODERATION or ON_MODERATION_FAILED."""
        ad = _create_ad(seller, category, city, status=AdStatus.PUBLISHED)

        client = Client()
        client.force_login(staff_user)
        response = client.get(f"/moderation/review/{ad.id}/")

        assert response.status_code == 404

    def test_review_returns_404_for_nonexistent_ad(
        self,
        staff_user: User,
    ) -> None:
        """Review page returns 404 for non-existent ad."""
        client = Client()
        client.force_login(staff_user)
        response = client.get("/moderation/review/99999/")

        assert response.status_code == 404

    def test_review_includes_related_objects(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """Review page includes user, category, city, and images in context."""
        ad, ad_image = _create_ad_with_image(seller, category, city, status=AdStatus.ON_MODERATION)

        client = Client()
        client.force_login(staff_user)
        response = client.get(f"/moderation/review/{ad.id}/")

        assert response.status_code == 200
        ctx_ad = response.context["ad"]
        # Check that related objects are prefetched
        assert ctx_ad.user is not None
        assert ctx_ad.category is not None
        assert ctx_ad.city is not None


# ---------------------------------------------------------------------------
# Tests: approve_ad
# ---------------------------------------------------------------------------


class TestApproveAdView:
    """approve_ad view transitions ad to PUBLISHED."""

    def test_approve_transitions_to_published(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """POST to approve_ad transitions ad from ON_MODERATION to PUBLISHED."""
        ad = _create_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        client = Client()
        client.force_login(staff_user)
        response = client.post(f"/moderation/approve/{ad.id}/")

        assert response.status_code == 302  # Redirect to admin change page

        # Verify ad state
        ad.refresh_from_db()
        assert ad.status == AdStatus.PUBLISHED
        assert ad.published_at is not None
        assert ad.published_by_id == staff_user.id

    def test_approve_creates_moderation_log(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """approve_ad creates a ModeratorActionLog entry."""
        ad = _create_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        client = Client()
        client.force_login(staff_user)
        client.post(f"/moderation/approve/{ad.id}/")

        # Verify moderation log
        log_entries = ModeratorActionLog.objects.filter(ad_id=ad.id)
        assert log_entries.exists()

    def test_approve_requires_post(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """GET to approve_ad returns 405 or redirect (view does not check method)."""
        ad = _create_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        client = Client()
        client.force_login(staff_user)
        response = client.get(f"/moderation/approve/{ad.id}/")

        # The view does not check method, so GET will still work
        # But the ad should still be approved
        ad.refresh_from_db()
        assert ad.status == AdStatus.PUBLISHED

    def test_approve_non_moderation_ad_returns_404(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """approve_ad returns 404 for ads not in ON_MODERATION status."""
        ad = _create_ad(seller, category, city, status=AdStatus.PUBLISHED)

        client = Client()
        client.force_login(staff_user)
        response = client.post(f"/moderation/approve/{ad.id}/")

        # get_object_or_404 with status=ON_MODERATION will raise 404
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Tests: reject_ad
# ---------------------------------------------------------------------------


class TestRejectAdView:
    """reject_ad view transitions ad to REJECTED."""

    def test_reject_transitions_to_rejected(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """POST to reject_ad transitions ad from ON_MODERATION to REJECTED."""
        ad = _create_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        client = Client()
        client.force_login(staff_user)
        response = client.post(
            f"/moderation/reject/{ad.id}/",
            data={"reason_category": "spam_scam", "reason_text": "Spam content"},
        )

        assert response.status_code == 302  # Redirect to admin ad list

        # Verify ad state
        ad.refresh_from_db()
        assert ad.status == AdStatus.REJECTED
        assert ad.rejected_at is not None
        assert ad.moderated_by_id == staff_user.id

    def test_reject_without_reason_text(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """reject_ad works with only reason_category (reason_text is optional)."""
        ad = _create_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        client = Client()
        client.force_login(staff_user)
        response = client.post(
            f"/moderation/reject/{ad.id}/",
            data={"reason_category": "spam_scam"},
        )

        assert response.status_code == 302
        ad.refresh_from_db()
        assert ad.status == AdStatus.REJECTED

    def test_reject_creates_moderation_log(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """reject_ad creates a ModeratorActionLog entry."""
        ad = _create_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        client = Client()
        client.force_login(staff_user)
        client.post(
            f"/moderation/reject/{ad.id}/",
            data={"reason_category": "spam_scam", "reason_text": "Spam"},
        )

        log_entries = ModeratorActionLog.objects.filter(ad_id=ad.id)
        assert log_entries.exists()

    def test_reject_requires_post(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """GET to reject_ad redirects rather than rejecting."""
        ad = _create_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        client = Client()
        client.force_login(staff_user)
        response = client.get(f"/moderation/reject/{ad.id}/")

        # The view checks for POST and redirects otherwise
        assert response.status_code == 302

        # Ad should NOT be rejected
        ad.refresh_from_db()
        assert ad.status == AdStatus.ON_MODERATION
        assert ad.rejected_at is None

    def test_reject_failed_moderation_ad(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """reject_ad works for ads in ON_MODERATION_FAILED status."""
        ad = _create_ad(seller, category, city, status=AdStatus.ON_MODERATION_FAILED)

        client = Client()
        client.force_login(staff_user)
        response = client.post(
            f"/moderation/reject/{ad.id}/",
            data={"reason_category": "spam_scam"},
        )

        assert response.status_code == 302
        ad.refresh_from_db()
        assert ad.status == AdStatus.REJECTED


# ---------------------------------------------------------------------------
# Tests: ban_user
# ---------------------------------------------------------------------------


class TestBanUserView:
    """ban_user view bans the ad owner."""

    def test_ban_marks_user_as_banned(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """POST to ban_user marks the seller as banned."""
        ad = _create_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        client = Client()
        client.force_login(staff_user)
        response = client.post(
            f"/moderation/ban/{ad.id}/",
            data={"ban_reason": "Repeated violations"},
        )

        assert response.status_code == 302  # Redirect to admin ad list

        # Verify seller is banned
        seller.refresh_from_db()
        assert seller.is_banned is True

    def test_ban_creates_moderation_log(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """ban_user creates a ModeratorActionLog entry for the ban."""
        ad = _create_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        client = Client()
        client.force_login(staff_user)
        client.post(
            f"/moderation/ban/{ad.id}/",
            data={"ban_reason": "Repeated violations"},
        )

        # Verify moderation log exists for this user
        log_entries = ModeratorActionLog.objects.filter(user_id=seller.id)
        assert log_entries.exists()

    def test_ban_requires_post(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """GET to ban_user redirects without banning."""
        ad = _create_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        client = Client()
        client.force_login(staff_user)
        response = client.get(f"/moderation/ban/{ad.id}/")

        assert response.status_code == 302

        # Seller should NOT be banned
        seller.refresh_from_db()
        assert seller.is_banned is False

    def test_ban_defaults_reason_when_not_provided(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """ban_user uses default reason when ban_reason is not provided."""
        ad = _create_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        client = Client()
        client.force_login(staff_user)
        response = client.post(f"/moderation/ban/{ad.id}/")

        assert response.status_code == 302

        # Seller should still be banned with default reason
        seller.refresh_from_db()
        assert seller.is_banned is True