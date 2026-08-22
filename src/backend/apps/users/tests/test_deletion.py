"""
Tests for deletion services (withdraw_consent, decline_consent).

Verifies token invalidation on consent withdrawal and ad soft-deletion.
"""

import hashlib

import pytest
from apps.users.models import LoginToken, User
from apps.users.services.deletion import (
    decline_consent,
    give_consent,
    soft_delete_user_ads,
    withdraw_consent,
)
from django.utils import timezone

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


class TestWithdrawConsentInvalidatesTokens:
    """Tests for LoginToken invalidation on consent withdrawal."""

    def test_withdraw_deletes_user_login_tokens(self, user: User):
        """withdraw_consent deletes all LoginTokens for the user."""
        # Create active tokens for the user
        now = timezone.now()
        token1 = LoginToken.objects.create(
            token_hash="hash1",
            telegram_id=user.telegram_id,
            expires_at=now + timezone.timedelta(hours=1),
        )
        # Token claimed by bot but not consumed (simulating active claim)
        token2 = LoginToken.objects.create(
            token_hash="hash2",
            telegram_id=user.telegram_id,
            expires_at=now + timezone.timedelta(hours=1),
        )

        # Withdraw consent
        withdraw_consent(user)

        # Verify tokens are deleted
        assert not LoginToken.objects.filter(pk=token1.pk).exists()
        assert not LoginToken.objects.filter(pk=token2.pk).exists()

    def test_withdraw_prevents_second_claim(self, user: User):
        """Token created before withdraw cannot be claimed after withdraw.

        Simulates the claim_login_token flow: after withdrawal, tokens with
        the user's telegram_id no longer exist to be claimed.
        """
        # Create token and hash
        raw_token = "a" * 32
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        now = timezone.now()
        # Token exists but telegram_id is NULL (unclaimed state)
        _ = LoginToken.objects.create(
            token_hash=token_hash,
            telegram_id=None,
            expires_at=now + timezone.timedelta(hours=1),
        )

        # User claims the token (simulating /start login_<token>)
        # This sets telegram_id on the token
        def claim_token():
            result = LoginToken.objects.filter(
                token_hash=token_hash,
                telegram_id__isnull=True,
                consumed_at__isnull=True,
                expires_at__gt=now,
            ).update(telegram_id=user.telegram_id)
            if result == 0:
                return None
            return LoginToken.objects.get(token_hash=token_hash)

        claimed = claim_token()
        assert claimed is not None, "Token should be claimable before withdrawal"

        # Now withdraw consent - this should delete the token
        withdraw_consent(user)

        # Verify user's telegram_id is nulled and token is gone
        user.refresh_from_db()
        assert user.telegram_id is None
        assert user.username is None
        assert user.consent_revoked_at is not None
        assert user.is_deleted is True

        # Second claim attempt on the same token fails
        second_claim = claim_token()
        assert second_claim is None, "Token should not be claimable after withdrawal"


class TestDeclineConsentDoesNotInvalideTokens:
    """Tests that decline_consent does NOT invalidate tokens (P11.1)."""

    def test_decline_preserves_login_tokens(self, user: User):
        """decline_consent does NOT delete LoginTokens."""
        now = timezone.now()
        token = LoginToken.objects.create(
            token_hash="hash_declined",
            telegram_id=user.telegram_id,
            expires_at=now + timezone.timedelta(hours=1),
        )

        decline_consent(user)

        # Token should still exist
        assert LoginToken.objects.filter(pk=token.pk).exists()

        # User's PII should NOT be nulled
        user.refresh_from_db()
        assert user.telegram_id is not None
        assert user.consent_revoked_at is None
        assert user.is_deleted is False


class TestWithdrawConsentSoftDeletesAds:
    """Tests for ad soft-deletion on consent withdrawal (P11.3)."""

    def test_withdraw_soft_deletes_user_ads(self, user: User):
        """withdraw_consent soft-deletes all user ads."""
        from apps.ads.models import Ad
        from apps.categories.models import Category
        from apps.core.enums import AdStatus
        from apps.locations.models import City

        category = Category.objects.create(
            name="Test Category",
            slug="test-category",
        )
        city = City.objects.create(
            country_code="ME",
            name="Test City",
            region="Test Region",
            slug="test-city",
        )

        # Create user ads
        ad1 = Ad.objects.create(
            user=user,
            title="Ad 1",
            description="Description 1",
            category=category,
            city=city,
            category_name=category.name,
            status=AdStatus.PUBLISHED,
            published_at=timezone.now(),
        )
        ad2 = Ad.objects.create(
            user=user,
            title="Ad 2",
            description="Description 2",
            category=category,
            city=city,
            category_name=category.name,
            status=AdStatus.ON_MODERATION,
        )

        withdraw_consent(user)

        # Verify ads are soft-deleted
        ad1.refresh_from_db()
        ad2.refresh_from_db()
        assert ad1.status == AdStatus.DELETED
        assert ad1.deleted_at is not None
        assert ad2.status == AdStatus.DELETED


class TestGiveConsent:
    """Tests for give_consent service."""

    def test_give_consent_sets_timestamp(self, user: User):
        """give_consent sets consent_given_at on the user."""
        give_consent(user)

        user.refresh_from_db()
        assert user.consent_given_at is not None

    def test_give_consent_does_not_alter_other_flags(self, user: User):
        """give_consent only sets consent_given_at; other flags remain unchanged."""
        give_consent(user)

        user.refresh_from_db()
        assert user.is_deleted is False
        assert user.is_banned is False
        assert user.is_declined is False
        assert user.ads_auto_publish is True
        assert user.consent_revoked_at is None
        assert user.telegram_id is not None
        assert user.username is None  # default for test fixture

    def test_give_consent_after_decline_restores_publishing(self, user: User):
        """give_consent after decline_consent clears decline state (D6)."""
        decline_consent(user)
        user.refresh_from_db()
        assert user.is_declined is True
        assert user.ads_auto_publish is False

        give_consent(user)
        user.refresh_from_db()
        assert user.is_declined is False
        assert user.ads_auto_publish is True
        assert user.consent_given_at is not None
        assert user.consent_revoked_at is None


class TestWithdrawConsentAtomicity:
    """Tests for transaction.atomic() wrapping in withdraw_consent (PII-008)."""

    def test_withdraw_is_atomic_rollback(self, user: User, monkeypatch):
        """If soft_delete_user_ads raises, the entire transaction rolls back.

        LoginTokens and user PII must be fully restored when an error occurs
        inside the transaction boundary.
        """
        now = timezone.now()
        token = LoginToken.objects.create(
            token_hash="hash_rollback",
            telegram_id=user.telegram_id,
            expires_at=now + timezone.timedelta(hours=1),
        )

        def _raise(*args, **kwargs):
            raise RuntimeError("simulated DB error in soft_delete_user_ads")

        monkeypatch.setattr(
            "apps.users.services.deletion.soft_delete_user_ads",
            _raise,
        )

        with pytest.raises(RuntimeError, match="simulated DB error"):
            withdraw_consent(user)

        # LoginTokens restored — transaction rolled back
        assert LoginToken.objects.filter(pk=token.pk).exists()
        # User NOT soft-deleted — PII and flags rolled back
        user.refresh_from_db()
        assert user.is_deleted is False
        assert user.telegram_id is not None  # not nulled (rolled back)
        assert user.consent_revoked_at is None

    def test_withdraw_returns_storage_keys(self, user: User, monkeypatch):
        """withdraw_consent returns list[str] of DRAFT-ad storage keys."""
        from apps.ads.models import Ad, AdImage
        from apps.categories.models import Category
        from apps.core.enums import AdStatus
        from apps.locations.models import City

        category = Category.objects.create(name="Test Category", slug="test-category")
        city = City.objects.create(
            country_code="ME",
            name="Test City",
            region="Test Region",
            slug="test-city",
        )

        draft_ad = Ad.objects.create(
            user=user,
            title="Draft Ad",
            description="Description",
            category=category,
            city=city,
            category_name=category.name,
            status=AdStatus.DRAFT,
        )
        AdImage.objects.create(ad=draft_ad, image="test-draft-key.jpg")

        deleted_keys: list[str] = []

        def _spy(key: str) -> None:
            deleted_keys.append(key)

        monkeypatch.setattr("apps.users.services.deletion.delete_photo", _spy)

        result = withdraw_consent(user)

        assert isinstance(result, list)
        assert all(isinstance(k, str) for k in result)
        assert "test-draft-key.jpg" in result
        # delete_photo called with the same keys after transaction commits
        assert deleted_keys == result

    def test_withdraw_idempotent(self, user: User):
        """Calling withdraw_consent twice returns [] on second call, no extra deletions."""
        now = timezone.now()
        token = LoginToken.objects.create(
            token_hash="hash_idempotent",
            telegram_id=user.telegram_id,
            expires_at=now + timezone.timedelta(hours=1),
        )

        withdraw_consent(user)
        assert user.is_deleted is True
        # Token deleted by first call (inside transaction)
        assert not LoginToken.objects.filter(pk=token.pk).exists()

        second = withdraw_consent(user)
        assert second == []
        # No extra token deletion on second call (already gone)
        assert not LoginToken.objects.filter(pk=token.pk).exists()

    def test_soft_delete_user_ads_returns_keys_not_count(self, user: User, monkeypatch):
        """soft_delete_user_ads is DB-only: returns list[str], never calls delete_photo."""
        from apps.ads.models import Ad, AdImage
        from apps.categories.models import Category
        from apps.core.enums import AdStatus
        from apps.locations.models import City

        category = Category.objects.create(name="Test Category", slug="test-category")
        city = City.objects.create(
            country_code="ME",
            name="Test City",
            region="Test Region",
            slug="test-city",
        )

        draft_ad = Ad.objects.create(
            user=user,
            title="Draft Ad",
            description="Description",
            category=category,
            city=city,
            category_name=category.name,
            status=AdStatus.DRAFT,
        )
        AdImage.objects.create(ad=draft_ad, image="orphan-key.jpg")

        called: list[str] = []

        def _spy(key: str) -> None:
            called.append(key)

        monkeypatch.setattr("apps.users.services.deletion.delete_photo", _spy)

        result = soft_delete_user_ads(user)

        assert isinstance(result, list)
        assert all(isinstance(k, str) for k in result)
        assert "orphan-key.jpg" in result
        # delete_photo must NOT be called by soft_delete_user_ads (DB-only)
        assert called == []
