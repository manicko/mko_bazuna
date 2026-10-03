"""
Tests for deletion services (withdraw_consent, decline_consent).

Verifies token invalidation on consent withdrawal and ad soft-deletion.
"""

import hashlib

import pytest
from django.test import Client
from django.utils import timezone

from apps.ads.models import Ad, AdImage
from apps.core.enums import AdStatus
from apps.core.models import SupportTicket
from apps.search.models import SavedSearch, SearchHistory
from apps.search.services.cache import get_search_version
from apps.users.models import LoginToken, User
from apps.users.services.deletion import (
    decline_consent,
    give_consent,
    soft_delete_user_ads,
    withdraw_consent,
)
from conftest import create_test_ad, make_user

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


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

        # Set consent_given_at before withdraw (simulates prior consent)
        user.consent_given_at = timezone.now()
        user.save(update_fields=["consent_given_at"])

        # Now withdraw consent - this should delete the token
        withdraw_consent(user)

        # Verify user's telegram_id is nulled and token is gone
        user.refresh_from_db()
        assert user.telegram_id is None
        assert user.username is None
        assert user.email == ""
        assert user.consent_revoked_at is not None
        assert user.is_deleted is True
        # consent_given_at is cleared on withdraw (PC-001)
        assert user.consent_given_at is None

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

        # Set consent_given_at before decline (simulates prior consent)
        user.consent_given_at = timezone.now()
        user.save(update_fields=["consent_given_at"])

        decline_consent(user)

        # Token should still exist
        assert LoginToken.objects.filter(pk=token.pk).exists()

        # User's PII should NOT be nulled
        user.refresh_from_db()
        assert user.telegram_id is not None
        assert user.consent_revoked_at is None
        assert user.is_deleted is False
        # consent_given_at is cleared on decline (PC-001)
        assert user.consent_given_at is None


class TestDeclineConsentBumpsSearchCache:
    """decline_consent invalidates cached search results (SRH-001)."""

    @pytest.mark.django_db(transaction=True)
    def test_decline_bumps_search_cache_version(self, user: User) -> None:
        """decline_consent increments the search cache version.

        No Ad.save() fires on decline (ads are not mutated), so the post_save
        signal would not bump the search cache. The explicit
        ``transaction.on_commit(bump_search_cache_version)`` must invalidate
        cached results so the declined user's PUBLISHED ads disappear from
        search and listings. ``django_db(transaction=True)`` is required so
        the on_commit callback actually runs.
        """
        version_before = get_search_version()

        decline_consent(user)

        version_after = get_search_version()
        assert version_after > version_before


class TestWithdrawConsentSoftDeletesAds:
    """Tests for ad soft-deletion on consent withdrawal (P11.3)."""

    def test_withdraw_soft_deletes_user_ads(self, user: User, category, city):
        """withdraw_consent soft-deletes all user ads."""
        # Create user ads
        ad1 = create_test_ad(
            user,
            category,
            city,
            title="Ad 1",
            description="Description 1",
            status=AdStatus.PUBLISHED,
            published_at=timezone.now(),
        )
        ad2 = create_test_ad(
            user,
            category,
            city,
            title="Ad 2",
            description="Description 2",
            status=AdStatus.ON_MODERATION,
        )

        withdraw_consent(user)

        # Verify ads are soft-deleted
        ad1.refresh_from_db()
        ad2.refresh_from_db()
        assert ad1.status == AdStatus.DELETED
        assert ad1.deleted_at is not None
        assert ad2.status == AdStatus.DELETED

    def test_withdraw_refreshes_updated_at_on_ads(self, user: User, category, city):
        """Consent withdrawal refreshes updated_at on soft-deleted ads (AD-001).

        Previously soft_delete_user_ads used QuerySet.update(), which bypasses
        save() and leaves updated_at (auto_now=True) stale. Routing through
        transition_to(DELETED) now persists updated_at (included in the
        targeted save's update_fields), so it is refreshed.
        """
        ad = create_test_ad(
            user,
            category,
            city,
            title="Ad 1",
            description="Description 1",
            status=AdStatus.PUBLISHED,
            published_at=timezone.now(),
        )
        # Backdate updated_at so a refresh is detectable
        stale_at = timezone.now() - timezone.timedelta(days=1)
        Ad.objects.filter(pk=ad.pk).update(updated_at=stale_at)

        withdraw_consent(user)

        ad.refresh_from_db()
        assert ad.status == AdStatus.DELETED
        assert ad.updated_at > stale_at

    def test_withdraw_soft_deletes_user_sets_pii_nulls(self, user: User):
        """withdraw_consent nulls PII: telegram_id, username, first_name, last_name, email."""
        user.email = "admin@example.com"
        user.save(update_fields=["email"])

        withdraw_consent(user)

        user.refresh_from_db()
        assert user.telegram_id is None
        assert user.username is None
        assert user.first_name == ""
        assert user.last_name == ""
        assert user.email == ""

    @pytest.mark.django_db(transaction=True)
    def test_withdraw_returns_all_thumbnail_storage_keys(
        self, user: User, monkeypatch, category, city
    ):
        """withdraw_consent returns all 4 storage keys for an AdImage with thumbnails.

        Covers PC-004: storage_keys() collects image + thumbnail_small/medium/large
        so no thumbnail derivatives are orphaned on disk.
        """
        draft_ad = create_test_ad(
            user,
            category,
            city,
            title="Draft Ad",
            description="Description",
            status=AdStatus.DRAFT,
        )
        AdImage.objects.create(
            ad=draft_ad,
            image="orphan-key.jpg",
            thumbnail_small="orphan-key-small.jpg",
            thumbnail_medium="orphan-key-medium.jpg",
            thumbnail_large="orphan-key-large.jpg",
        )

        deleted_keys: list[str] = []

        def _spy(key: str) -> None:
            deleted_keys.append(key)

        monkeypatch.setattr("apps.media.signals.delete_photo", _spy)

        result = withdraw_consent(user)

        expected = {
            "orphan-key.jpg",
            "orphan-key-small.jpg",
            "orphan-key-medium.jpg",
            "orphan-key-large.jpg",
        }
        assert set(result) == expected
        assert len(result) == 4
        # delete_photo called for each of the 4 keys after transaction commits
        assert set(deleted_keys) == expected
        assert len(deleted_keys) == 4


class TestWithdrawConsentTearsDownSubscriberState:
    """withdraw_consent deactivates saved searches and deletes search history.

    Revocation actively terminates subscriber state inside the existing
    transaction instead of relying on a future filter (06-PII-110).
    """

    def test_withdraw_deactivates_saved_searches_and_deletes_history(
        self, user: User
    ) -> None:
        """The withdrawing user's SavedSearch rows go inactive; SearchHistory is deleted."""
        active = SavedSearch.objects.create(user=user, query="bike", is_active=True)
        history_a = SearchHistory.objects.create(
            user=user, query="bike", query_normalized="bike"
        )
        history_b = SearchHistory.objects.create(
            user=user, query="scooter", query_normalized="scooter"
        )

        withdraw_consent(user)

        active.refresh_from_db()
        assert active.is_active is False
        assert not SearchHistory.objects.filter(pk=history_a.pk).exists()
        assert not SearchHistory.objects.filter(pk=history_b.pk).exists()

    def test_withdraw_leaves_other_users_subscriber_state_untouched(
        self, user: User
    ) -> None:
        """A different user's SavedSearch and SearchHistory rows are untouched."""
        other = make_user(900000060)
        other_saved = SavedSearch.objects.create(
            user=other, query="other-bike", is_active=True
        )
        other_history = SearchHistory.objects.create(
            user=other, query="other-bike", query_normalized="other-bike"
        )

        withdraw_consent(user)

        other_saved.refresh_from_db()
        assert other_saved.is_active is True
        assert SearchHistory.objects.filter(pk=other_history.pk).exists()


class TestWithdrawConsentRetainsChatId:
    """The withdrawn identity stays resolvable by chat_id (06-PII-110).

    ``AccountStateMiddleware._resolve_user`` resolves the acting user on
    ``chat_id`` precisely because ``telegram_id`` is nulled. Nulling ``chat_id``
    would silently un-block a withdrawn identity; this test stops a future
    "cleanup" from doing so.
    """

    def test_chat_id_survives_and_user_is_resolvable(self, user: User) -> None:
        """chat_id is unchanged after withdrawal and User.objects.get finds it."""
        expected_chat_id = user.chat_id
        assert expected_chat_id is not None

        withdraw_consent(user)

        user.refresh_from_db()
        assert user.chat_id == expected_chat_id
        # Exactly what AccountStateMiddleware._resolve_user does.
        resolved = User.objects.get(chat_id=expected_chat_id)
        assert resolved.pk == user.pk
        assert resolved.is_deleted is True


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

    def test_give_consent_rejected_on_soft_deleted_user(self) -> None:
        """give_consent is a no-op for soft-deleted users (WITHDRAW is terminal)."""
        deleted = make_user(
            900000050,
            consent_revoked=True,
            is_deleted=True,
        )

        pre_revoked = deleted.consent_revoked_at
        pre_given = deleted.consent_given_at
        pre_telegram_id = deleted.telegram_id

        give_consent(deleted)

        deleted.refresh_from_db()
        # State must be unchanged -- no DB write occurred
        assert deleted.is_deleted is True
        assert deleted.consent_revoked_at == pre_revoked  # not cleared
        assert deleted.consent_given_at == pre_given  # not set
        assert deleted.telegram_id == pre_telegram_id  # not restored/nullified


class TestWithdrawConsentAtomicity:
    """Tests for transaction.atomic() wrapping in withdraw_consent (PII-008)."""

    def test_withdraw_is_atomic_rollback(self, user: User, monkeypatch):
        """If soft_delete_user_ads raises, the entire transaction rolls back.

        LoginTokens, the SavedSearch deactivation, the SearchHistory deletion
        and the SupportTicket deletion must be fully restored when an error
        occurs inside the transaction boundary, together with the user PII
        writes.
        """
        now = timezone.now()
        token = LoginToken.objects.create(
            token_hash="hash_rollback",
            telegram_id=user.telegram_id,
            expires_at=now + timezone.timedelta(hours=1),
        )
        saved = SavedSearch.objects.create(user=user, query="rollback", is_active=True)
        history = SearchHistory.objects.create(
            user=user, query="rollback", query_normalized="rollback"
        )
        ticket = SupportTicket.objects.create(
            user=user, chat_id=user.chat_id, telegram_id=user.telegram_id, text="rollback"
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
        # SavedSearch deactivation and SearchHistory deletion rolled back too
        saved.refresh_from_db()
        assert saved.is_active is True
        assert SearchHistory.objects.filter(pk=history.pk).exists()
        # SupportTicket deletion rolled back too (06-PII-101)
        assert SupportTicket.objects.filter(pk=ticket.pk).exists()
        # User NOT soft-deleted — PII and flags rolled back
        user.refresh_from_db()
        assert user.is_deleted is False
        assert user.telegram_id is not None  # not nulled (rolled back)
        assert user.consent_revoked_at is None

    @pytest.mark.django_db(transaction=True)
    def test_withdraw_returns_storage_keys(
        self, user: User, monkeypatch, category, city
    ):
        """withdraw_consent returns list[str] of DRAFT-ad storage keys."""
        draft_ad = create_test_ad(
            user,
            category,
            city,
            title="Draft Ad",
            description="Description",
            status=AdStatus.DRAFT,
        )
        AdImage.objects.create(
            ad=draft_ad,
            image="test-draft-key.jpg",
            thumbnail_small="test-draft-key-small.jpg",
            thumbnail_medium="test-draft-key-medium.jpg",
            thumbnail_large="test-draft-key-large.jpg",
        )

        deleted_keys: list[str] = []

        def _spy(key: str) -> None:
            deleted_keys.append(key)

        monkeypatch.setattr("apps.media.signals.delete_photo", _spy)

        result = withdraw_consent(user)

        assert isinstance(result, list)
        assert all(isinstance(k, str) for k in result)
        assert "test-draft-key.jpg" in result
        assert "test-draft-key-small.jpg" in result
        assert "test-draft-key-medium.jpg" in result
        assert "test-draft-key-large.jpg" in result
        # All 4 keys returned for the single AdImage (image + 3 thumbnails)
        assert len(result) == 4
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

    def test_soft_delete_user_ads_returns_keys_not_count(
        self, user: User, monkeypatch, category, city
    ):
        """soft_delete_user_ads is DB-only: returns list[str], never calls delete_photo."""
        draft_ad = create_test_ad(
            user,
            category,
            city,
            title="Draft Ad",
            description="Description",
            status=AdStatus.DRAFT,
        )
        AdImage.objects.create(
            ad=draft_ad,
            image="orphan-key.jpg",
            thumbnail_small="orphan-key-small.jpg",
            thumbnail_medium="orphan-key-medium.jpg",
            thumbnail_large="orphan-key-large.jpg",
        )

        called: list[str] = []

        def _spy(key: str) -> None:
            called.append(key)

        monkeypatch.setattr("apps.media.signals.delete_photo", _spy)

        result = soft_delete_user_ads(user)

        assert isinstance(result, list)
        assert all(isinstance(k, str) for k in result)
        expected = {
            "orphan-key.jpg",
            "orphan-key-small.jpg",
            "orphan-key-medium.jpg",
            "orphan-key-large.jpg",
        }
        assert set(result) == expected
        assert len(result) == 4
        # delete_photo must NOT be called by soft_delete_user_ads (DB-only)
        assert called == []


class TestClearConsentGivenAt:
    """Explicit accept→decline and accept→withdraw transitions for consent_given_at (PC-001)."""

    def test_accept_then_decline_clears_consent_given_at(self, user: User):
        """give_consent sets consent_given_at; decline_consent clears it."""
        give_consent(user)
        user.refresh_from_db()
        assert user.consent_given_at is not None

        decline_consent(user)
        user.refresh_from_db()
        assert user.consent_given_at is None
        assert user.is_declined is True
        assert user.ads_auto_publish is False

    def test_accept_then_withdraw_clears_consent_given_at(self, user: User):
        """give_consent sets consent_given_at; withdraw_consent clears it."""
        give_consent(user)
        user.refresh_from_db()
        assert user.consent_given_at is not None

        withdraw_consent(user)
        user.refresh_from_db()
        assert user.consent_given_at is None
        assert user.consent_revoked_at is not None
        assert user.is_deleted is True


# ---------------------------------------------------------------------------
# Known gap (04-AUT-002, G-A) — withdraw revokes ONLY the current session
# ---------------------------------------------------------------------------


class TestWithdrawConsentMultiSessionKnownGap:
    """Pin that ``consent_withdraw`` flushes only the *current* session.

    Known gap: ``apps.users.views.consent.consent_withdraw`` calls
    ``logout(request)``, which flushes ``request.session`` — the one browser that
    triggered the withdrawal. A withdrawn user's OTHER live sessions are left
    intact. ``django_session`` has no user column and ``session_data`` is
    zlib-compressed and HMAC-signed (never encrypted), so no cheap scan can
    enumerate them. This test asserts the CURRENT, DEFECTIVE behaviour as a
    red-to-green specification for phase 15's ``15-AUTHZ-001``: it turns red the
    moment multi-session revocation lands.

    Owner of the fix: phase 15, ``15-AUTHZ-001``. Produced by B-07 gate G-A.
    """

    def test_withdraw_consent_leaves_other_sessions_intact(self, user: User) -> None:
        """A withdrawn user's second, independent session survives the withdrawal.

        Vacuity guard: both sessions are asserted live before the withdrawal, so
        the test cannot pass on a client that was never logged in.

        ``search_history`` stores anonymous history in the session by design
        (``apps/search/services/search_history.py``, capped at 50 entries), so a
        surviving session may retain up to 50 raw search queries.
        """
        # Two independent browser sessions for the same user.
        withdrawing_client = Client()
        withdrawing_client.force_login(user)
        other_client = Client()
        other_client.force_login(user)

        assert "_auth_user_id" in withdrawing_client.session
        assert "_auth_user_id" in other_client.session

        response = withdrawing_client.post("/consent/withdraw/")
        assert response.status_code == 302
        assert response.url == "/dashboard/"

        # The withdrawing browser's own session was flushed (B-03's logout).
        assert "_auth_user_id" not in withdrawing_client.session

        # Known gap (G-A): the other session is still live and usable.
        assert "_auth_user_id" in other_client.session

        user.refresh_from_db()
        assert user.is_deleted is True


# ---------------------------------------------------------------------------
# SupportTicket erasure on withdrawal (06-PII-101)
# ---------------------------------------------------------------------------


class TestWithdrawDeletesSupportTickets:
    """``withdraw_consent`` deletes the user's tickets while the User row stays.

    ``withdraw_consent`` is a SOFT delete, so the FK's ``CASCADE`` can never
    fire here; the explicit ``SupportTicket.objects.filter(user=user).delete()``
    is the load-bearing step. These tests prove the ticket disappears **and**
    the ``User`` row still exists, which is exactly what distinguishes the
    explicit delete from a cascade.
    """

    def test_withdraw_deletes_ticket_but_keeps_user_row(self, user: User) -> None:
        """The user's ticket is gone; the user row still exists after withdrawal."""
        ticket = SupportTicket.objects.create(
            user=user,
            chat_id=user.chat_id,
            telegram_id=user.telegram_id,
            text="please help",
        )

        withdraw_consent(user)

        # Ticket gone, but the soft-deleted User row remains (CASCADE never fired).
        assert not SupportTicket.objects.filter(pk=ticket.pk).exists()
        assert User.objects.filter(pk=user.pk).exists()
        user.refresh_from_db()
        assert user.is_deleted is True

    def test_withdraw_spares_another_users_ticket(self, user: User) -> None:
        """An over-broad filter is caught: another user's ticket is untouched."""
        other = make_user(900000555, consent_given_at=timezone.now())
        mine = SupportTicket.objects.create(
            user=user,
            chat_id=user.chat_id,
            telegram_id=user.telegram_id,
            text="my ticket",
        )
        theirs = SupportTicket.objects.create(
            user=other,
            chat_id=other.chat_id,
            telegram_id=other.telegram_id,
            text="their ticket",
        )

        withdraw_consent(user)

        assert not SupportTicket.objects.filter(pk=mine.pk).exists()
        assert SupportTicket.objects.filter(pk=theirs.pk).exists()
