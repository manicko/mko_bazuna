"""
View-layer tests for consent views (TST-004).

Covers:
- consent_accept: sets consent_given_at + cookie, redirects
- consent_decline: sets ads_auto_publish=False + cookie, redirects
- consent_withdraw: soft-deletes user + ads, nulls PII, sets cookie, redirects
- Authentication required for all consent views
"""

import pytest
from apps.ads.models import Ad
from apps.categories.models import Category
from apps.core.enums import AdStatus
from apps.locations.models import City
from apps.users.models import User
from django.test import Client
from django.utils import timezone

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def user() -> User:
    """Create an authenticated user for consent tests."""
    return User.objects.create(
        telegram_id=900000030,
        chat_id=900000030,
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


def _create_ad(
    user: User,
    category: Category,
    city: City,
    *,
    title: str = "Test Ad",
    status: AdStatus = AdStatus.PUBLISHED,
) -> Ad:
    """Create an ad with the given status."""
    return Ad.objects.create(
        user=user,
        title=title,
        description="Test description",
        category=category,
        city=city,
        category_name=category.name,
        status=status,
        published_at=timezone.now() if status == AdStatus.PUBLISHED else None,
    )


# ---------------------------------------------------------------------------
# Tests: consent_accept
# ---------------------------------------------------------------------------


class TestConsentAcceptView:
    """consent_accept view sets consent_given_at and redirects."""

    def test_accept_requires_authentication(self) -> None:
        """Anonymous users are redirected to login."""
        client = Client()
        response = client.get("/consent/accept/")
        # LoginRequiredMiddleware redirects to login page
        assert response.status_code == 302

    def test_accept_sets_consent_given_at(self, user: User) -> None:
        """consent_accept sets consent_given_at on the user."""
        client = Client()
        client.force_login(user)
        response = client.get("/consent/accept/")

        assert response.status_code == 302
        # Check redirect target
        assert response.url == "/dashboard/"  # noqa: S105

        # Verify user state
        user.refresh_from_db()
        assert user.consent_given_at is not None
        assert user.consent_revoked_at is None
        assert user.is_deleted is False

    def test_accept_sets_consent_cookie(self, user: User) -> None:
        """consent_accept sets the consent_given cookie."""
        client = Client()
        client.force_login(user)
        response = client.get("/consent/accept/")

        assert response.cookies.get("consent_given") is not None
        assert response.cookies["consent_given"].value == "true"


# ---------------------------------------------------------------------------
# Tests: consent_decline
# ---------------------------------------------------------------------------


class TestConsentDeclineView:
    """consent_decline view sets ads_auto_publish=False and redirects."""

    def test_decline_requires_authentication(self) -> None:
        """Anonymous users are redirected to login."""
        client = Client()
        response = client.get("/consent/decline/")
        assert response.status_code == 302

    def test_decline_sets_ads_auto_publish_false(self, user: User) -> None:
        """consent_decline sets ads_auto_publish=False and is_declined=True."""
        client = Client()
        client.force_login(user)
        response = client.get("/consent/decline/")

        assert response.status_code == 302
        assert response.url == "/dashboard/"

        # Verify user state
        user.refresh_from_db()
        assert user.ads_auto_publish is False
        assert user.is_declined is True
        assert user.consent_given_at is None
        assert user.consent_revoked_at is None
        assert user.is_deleted is False
        assert user.telegram_id is not None  # PII preserved

    def test_decline_sets_declined_cookie(self, user: User) -> None:
        """consent_decline sets the consent_given cookie to 'declined'."""
        client = Client()
        client.force_login(user)
        response = client.get("/consent/decline/")

        assert response.cookies.get("consent_given") is not None
        assert response.cookies["consent_given"].value == "declined"


# ---------------------------------------------------------------------------
# Tests: consent_withdraw
# ---------------------------------------------------------------------------


class TestConsentWithdrawView:
    """consent_withdraw view soft-deletes user and ads, redirects."""

    def test_withdraw_requires_authentication(self) -> None:
        """Anonymous users are redirected to login."""
        client = Client()
        response = client.get("/consent/withdraw/")
        assert response.status_code == 302

    def test_withdraw_triggers_user_soft_delete(
        self,
        user: User,
        category: Category,
        city: City,
    ) -> None:
        """consent_withdraw soft-deletes the user, nulls PII, and marks consent revoked."""
        # Create some ads
        _create_ad(user, category, city, title="Ad 1", status=AdStatus.PUBLISHED)
        _create_ad(user, category, city, title="Ad 2", status=AdStatus.ON_MODERATION)

        client = Client()
        client.force_login(user)
        response = client.get("/consent/withdraw/")

        assert response.status_code == 302
        assert response.url == "/dashboard/"

        # Verify user state
        user.refresh_from_db()
        assert user.consent_revoked_at is not None
        assert user.is_deleted is True
        assert user.deleted_at is not None
        assert user.telegram_id is None  # PII nulled
        assert user.username is None

    def test_withdraw_soft_deletes_ads(
        self,
        user: User,
        category: Category,
        city: City,
    ) -> None:
        """consent_withdraw soft-deletes all user ads."""
        ad1 = _create_ad(user, category, city, title="Published Ad", status=AdStatus.PUBLISHED)
        ad2 = _create_ad(user, category, city, title="Draft Ad", status=AdStatus.DRAFT)

        client = Client()
        client.force_login(user)
        client.get("/consent/withdraw/")

        # Verify ads are soft-deleted
        ad1.refresh_from_db()
        ad2.refresh_from_db()
        assert ad1.status == AdStatus.DELETED
        assert ad1.deleted_at is not None
        assert ad2.status == AdStatus.DELETED
        assert ad2.deleted_at is not None

    def test_withdraw_sets_withdrawn_cookie(self, user: User) -> None:
        """consent_withdraw sets the consent_given cookie to 'withdrawn'."""
        client = Client()
        client.force_login(user)
        response = client.get("/consent/withdraw/")

        assert response.cookies.get("consent_given") is not None
        assert response.cookies["consent_given"].value == "withdrawn"