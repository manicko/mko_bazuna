"""
View-layer tests for consent views (TST-004).

Covers:
- consent_accept: sets consent_given_at + cookie, redirects
- consent_decline: sets ads_auto_publish=False + cookie, redirects
- consent_withdraw: soft-deletes user + ads, nulls PII, sets cookie, redirects
- Authentication required for all consent views
"""

import hashlib
from datetime import timedelta

import pytest
from apps.categories.models import Category
from apps.core.enums import AdStatus, ConsentChoice
from apps.locations.models import City
from apps.users.models import ConsentRecord, LoginToken, User
from django.test import Client
from django.utils import timezone

from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Tests: consent_accept
# ---------------------------------------------------------------------------


class TestConsentAcceptView:
    """consent_accept view sets consent_given_at and redirects."""

    def test_accept_anonymous_redirects_home_and_sets_cookie(self) -> None:
        """Anonymous POST accept redirects home and sets consent cookies."""
        client = Client()
        response = client.post("/consent/accept/")

        assert response.status_code == 302
        assert response.url == "/"

        # No DB write for anonymous consent (security gate D-3).
        assert (
            ConsentRecord.objects.filter(user__isnull=False, choice=ConsentChoice.ACCEPTED).count()
            == 0
        )

    def test_accept_requires_post(self) -> None:
        """GET /consent/accept/ is rejected (405 Method Not Allowed)."""
        client = Client()
        response = client.get("/consent/accept/")
        assert response.status_code == 405

    def test_accept_sets_consent_given_at(self, user: User) -> None:
        """consent_accept sets consent_given_at on the user."""
        client = Client()
        client.force_login(user)
        response = client.post("/consent/accept/")

        assert response.status_code == 302
        # Check redirect target
        assert response.url == "/dashboard/"  # noqa: S105

        # Verify user state
        user.refresh_from_db()
        assert user.consent_given_at is not None
        assert user.consent_revoked_at is None
        assert user.is_deleted is False

    def test_accept_sets_consent_cookie(self, user: User) -> None:
        """consent_accept sets the structured consent_given cookie."""
        client = Client()
        client.force_login(user)
        response = client.post("/consent/accept/")

        assert response.cookies.get("consent_given") is not None
        assert response.cookies["consent_given"].value == "accepted"

    def test_accept_sets_category_cookies(self, user: User) -> None:
        """consent_accept sets analytics and preferences cookies to 'true'."""
        client = Client()
        client.force_login(user)
        response = client.post("/consent/accept/")

        assert response.cookies["consent_analytics"].value == "true"
        assert response.cookies["consent_preferences"].value == "true"

    def test_accept_cookie_has_secure_flag(self, user: User) -> None:
        """consent cookies are marked Secure (T-05 / D-COOKIES)."""
        client = Client()
        client.force_login(user)
        response = client.post("/consent/accept/")

        for name in ("consent_given", "consent_analytics", "consent_preferences"):
            assert response.cookies[name]["secure"] is True, name

    def test_anonymous_accept_sets_cookie_no_db_write(self) -> None:
        """Anonymous accept sets cookies without creating a DB record."""
        client = Client()
        before = ConsentRecord.objects.count()
        response = client.post("/consent/accept/")

        assert response.status_code == 302
        assert response.url == "/"
        assert response.cookies["consent_given"].value == "accepted"
        assert response.cookies["consent_analytics"].value == "true"
        assert response.cookies["consent_preferences"].value == "true"
        # Exactly one consent record, with a null user (anonymous identity).
        assert ConsentRecord.objects.count() == before + 1
        record = ConsentRecord.objects.order_by("-id").first()
        assert record.user_id is None

    def test_accept_after_decline_restores_publishing(self, user: User) -> None:
        """Accept after decline clears is_declined and restores ads_auto_publish (D6)."""
        client = Client()
        client.force_login(user)

        client.post("/consent/decline/")
        user.refresh_from_db()
        assert user.is_declined is True
        assert user.ads_auto_publish is False

        client.post("/consent/accept/")
        user.refresh_from_db()
        assert user.is_declined is False
        assert user.ads_auto_publish is True
        assert user.consent_given_at is not None


# ---------------------------------------------------------------------------
# Tests: consent_decline
# ---------------------------------------------------------------------------


class TestConsentDeclineView:
    """consent_decline view sets ads_auto_publish=False and redirects."""

    def test_decline_requires_post(self) -> None:
        """GET /consent/decline/ is rejected (405 Method Not Allowed)."""
        client = Client()
        response = client.get("/consent/decline/")
        assert response.status_code == 405

    def test_anonymous_decline_sets_cookie_no_db_write(self) -> None:
        """Anonymous decline redirects home, sets declined cookie, no DB write."""
        client = Client()
        response = client.post("/consent/decline/")

        assert response.status_code == 302
        assert response.url == "/"
        assert response.cookies["consent_given"].value == "declined"
        assert response.cookies["consent_analytics"].value == "false"
        assert response.cookies["consent_preferences"].value == "true"
        # Anonymous consent never persists a DB record for a user account.
        assert (
            ConsentRecord.objects.filter(user__isnull=False, choice=ConsentChoice.DECLINED).count()
            == 0
        )

    def test_decline_sets_ads_auto_publish_false(self, user: User) -> None:
        """consent_decline sets ads_auto_publish=False and is_declined=True."""
        client = Client()
        client.force_login(user)
        response = client.post("/consent/decline/")

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
        response = client.post("/consent/decline/")

        assert response.cookies.get("consent_given") is not None
        assert response.cookies["consent_given"].value == "declined"
        assert response.cookies["consent_analytics"].value == "false"
        # Preferences remain available even on decline (PO-02).
        assert response.cookies["consent_preferences"].value == "true"


# ---------------------------------------------------------------------------
# Tests: consent_withdraw
# ---------------------------------------------------------------------------


class TestConsentWithdrawView:
    """consent_withdraw view soft-deletes user and ads, redirects."""

    def test_withdraw_requires_authentication(self) -> None:
        """Anonymous users are redirected to login."""
        client = Client()
        response = client.post("/consent/withdraw/")
        assert response.status_code == 302

    def test_withdraw_triggers_user_soft_delete(
        self,
        user: User,
        category: Category,
        city: City,
    ) -> None:
        """consent_withdraw soft-deletes the user, nulls PII, and marks consent revoked."""
        # Create some ads
        create_test_ad(user, category, city, title="Ad 1", status=AdStatus.PUBLISHED)
        create_test_ad(user, category, city, title="Ad 2", status=AdStatus.ON_MODERATION)

        client = Client()
        client.force_login(user)
        response = client.post("/consent/withdraw/")

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
        ad1 = create_test_ad(
            user, category, city, title="Published Ad", status=AdStatus.PUBLISHED
        )
        ad2 = create_test_ad(
            user, category, city, title="Draft Ad", status=AdStatus.DRAFT
        )

        client = Client()
        client.force_login(user)
        client.post("/consent/withdraw/")

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
        response = client.post("/consent/withdraw/")

        assert response.cookies.get("consent_given") is not None
        assert response.cookies["consent_given"].value == "withdrawn"

    def test_withdraw_button_renders_on_dashboard(self, user: User) -> None:
        """Authenticated users see the Withdraw Data button on the dashboard."""
        client = Client()
        client.force_login(user)
        response = client.get("/dashboard/")

        assert response.status_code == 200
        # The Withdraw Data button is present in the response
        assert "Удалить данные".encode() in response.content
        # The form posts to the consent withdrawal endpoint
        assert b'action="/consent/withdraw/"' in response.content


# ---------------------------------------------------------------------------
# Tests: login_status PII masking
# ---------------------------------------------------------------------------


class TestLoginStatusNoPii:
    """Tests that login_status does not leak raw telegram_id in logs (PII-002)."""

    def test_login_consume_no_raw_telegram_id(self, caplog) -> None:
        """login_status must not log raw telegram_id after token consumption."""
        telegram_id = 999888777
        raw_token = "a" * 32
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        User.objects.create(
            telegram_id=telegram_id,
            chat_id=telegram_id,
            password="x",
        )
        LoginToken.objects.create(
            token_hash=token_hash,
            telegram_id=telegram_id,
            expires_at=timezone.now() + timedelta(minutes=5),
            consumed_at=None,
        )

        client = Client()
        with caplog.at_level("INFO"):
            response = client.get(f"/login/status/?token={raw_token}")

        assert response.status_code == 200
        # Raw telegram_id must not appear in any log output
        assert str(telegram_id) not in caplog.text
        # Masked value should be present for log correlation
        assert "tg_" in caplog.text


# ---------------------------------------------------------------------------
# Tests: consent banner guard for deleted users (PII-009)
# ---------------------------------------------------------------------------


@pytest.fixture
def deleted_user() -> User:
    """Create a soft-deleted user for banner visibility tests."""
    return User.objects.create(
        telegram_id=900000031,
        chat_id=900000031,
        password="x",
        is_deleted=True,
    )


class TestConsentBannerGuard:
    """Consent banner is suppressed for deleted users (PII-009).

    The banner include in every template is guarded by:
    ``{% if not request.user.is_authenticated or not request.user.is_deleted %}``
    so that soft-deleted users never see the consent banner, even when they
    briefly pass through a view before any redirect.
    """

    def test_banner_hidden_for_deleted_user(self, deleted_user: User) -> None:
        """Deleted users do *not* see the consent banner on the dashboard."""
        client = Client()
        client.force_login(deleted_user)
        response = client.get("/dashboard/")

        assert response.status_code == 200
        assert b"consent-banner" not in response.content

    def test_banner_shown_for_active_user(self, user: User) -> None:
        """Active, non-consenting users see the consent banner on the dashboard."""
        client = Client()
        client.force_login(user)
        response = client.get("/dashboard/")

        assert response.status_code == 200
        assert b"consent-banner" in response.content
