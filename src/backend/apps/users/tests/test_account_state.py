"""
Tests for account-state gating logic (TST-010).

Covers the full flag matrix for:
- can_publish_ad (banned, deleted, ads_auto_publish=False, combinations)
- can_login (banned, declined, combinations)
- get_account_state
- get_state_badge
"""

import pytest
from apps.users.models import User
from apps.users.services import (
    AccountState,
    can_login,
    can_publish_ad,
    get_account_state,
    get_state_badge,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def user() -> User:
    """Create a default user with all flags at their defaults."""
    return User.objects.create(
        telegram_id=900001000,
        chat_id=900001000,
        password="x",
    )


def _make_user(
    telegram_id: int,
    *,
    is_banned: bool = False,
    is_deleted: bool = False,
    is_declined: bool = False,
    ads_auto_publish: bool = True,
) -> User:
    """Create a user with specific account-state flags."""
    return User.objects.create(
        telegram_id=telegram_id,
        chat_id=telegram_id,
        password="x",
        is_banned=is_banned,
        is_deleted=is_deleted,
        is_declined=is_declined,
        ads_auto_publish=ads_auto_publish,
    )


# ---------------------------------------------------------------------------
# Tests: get_account_state
# ---------------------------------------------------------------------------


class TestGetAccountState:
    """get_account_state returns correct flag snapshot."""

    def test_default_state(self, user: User) -> None:
        """Default user has all flags at false/true defaults."""
        state = get_account_state(user)
        assert state == AccountState(
            is_banned=False,
            is_deleted=False,
            is_declined=False,
            ads_auto_publish=True,
            consent_revoked=False,
        )

    def test_banned_user(self) -> None:
        """Banned user has is_banned=True."""
        u = _make_user(900001001, is_banned=True)
        state = get_account_state(u)
        assert state.is_banned is True

    def test_deleted_user(self) -> None:
        """Deleted user has is_deleted=True."""
        u = _make_user(900001002, is_deleted=True)
        state = get_account_state(u)
        assert state.is_deleted is True

    def test_declined_user(self) -> None:
        """Declined user has is_declined=True."""
        u = _make_user(900001003, is_declined=True)
        state = get_account_state(u)
        assert state.is_declined is True

    def test_restricted_user(self) -> None:
        """Restricted user has ads_auto_publish=False."""
        u = _make_user(900001004, ads_auto_publish=False)
        state = get_account_state(u)
        assert state.ads_auto_publish is False

    def test_consent_revoked(self, user: User) -> None:
        """User with consent_revoked_at set has consent_revoked=True."""
        from django.utils import timezone

        user.consent_revoked_at = timezone.now()
        user.save(update_fields=["consent_revoked_at"])
        state = get_account_state(user)
        assert state.consent_revoked is True


# ---------------------------------------------------------------------------
# Tests: can_publish_ad  — flag matrix
# ---------------------------------------------------------------------------


class TestCanPublishAd:
    """Flag matrix for can_publish_ad: banned, deleted, ads_auto_publish."""

    def test_normal_user_can_publish(self, user: User) -> None:
        """Default user (no flags set) can publish."""
        assert can_publish_ad(user) is True

    def test_banned_user_cannot_publish(self) -> None:
        """Banned user cannot publish regardless of other flags."""
        u = _make_user(900001010, is_banned=True)
        assert can_publish_ad(u) is False

    def test_banned_and_restricted_cannot_publish(self) -> None:
        """Banned + restricted still cannot publish (banned takes priority in check order)."""
        u = _make_user(900001011, is_banned=True, ads_auto_publish=False)
        assert can_publish_ad(u) is False

    def test_banned_and_deleted_cannot_publish(self) -> None:
        """Banned + deleted cannot publish."""
        u = _make_user(900001012, is_banned=True, is_deleted=True)
        assert can_publish_ad(u) is False

    def test_deleted_user_cannot_publish(self) -> None:
        """Deleted user cannot publish."""
        u = _make_user(900001013, is_deleted=True)
        assert can_publish_ad(u) is False

    def test_deleted_and_restricted_cannot_publish(self) -> None:
        """Deleted + restricted cannot publish."""
        u = _make_user(900001014, is_deleted=True, ads_auto_publish=False)
        assert can_publish_ad(u) is False

    def test_restricted_user_cannot_publish(self) -> None:
        """User with ads_auto_publish=False cannot publish."""
        u = _make_user(900001015, ads_auto_publish=False)
        assert can_publish_ad(u) is False

    def test_declined_user_can_publish(self) -> None:
        """Declined user CAN publish (decline only blocks login, not publishing)."""
        u = _make_user(900001016, is_declined=True)
        assert can_publish_ad(u) is True

    def test_all_flags_cannot_publish(self) -> None:
        """All restriction flags together still cannot publish."""
        u = _make_user(
            900001017,
            is_banned=True,
            is_deleted=True,
            is_declined=True,
            ads_auto_publish=False,
        )
        assert can_publish_ad(u) is False


# ---------------------------------------------------------------------------
# Tests: can_login  — flag matrix
# ---------------------------------------------------------------------------


class TestCanLogin:
    """Flag matrix for can_login: banned, declined."""

    def test_normal_user_can_login(self, user: User) -> None:
        """Default user can login."""
        assert can_login(user) is True

    def test_banned_user_cannot_login(self) -> None:
        """Banned user cannot login."""
        u = _make_user(900001020, is_banned=True)
        assert can_login(u) is False

    def test_declined_user_cannot_login(self) -> None:
        """User who declined consent cannot login."""
        u = _make_user(900001021, is_declined=True)
        assert can_login(u) is False

    def test_banned_and_declined_cannot_login(self) -> None:
        """Banned + declined cannot login."""
        u = _make_user(900001022, is_banned=True, is_declined=True)
        assert can_login(u) is False

    def test_deleted_user_can_login_by_flag(self) -> None:
        """Deleted user CAN login by flag (telegram_id is nulled in practice).

        Note: can_login does not check is_deleted. Deleted users cannot actually
        authenticate because their telegram_id is nulled, but the gating function
        treats them as eligible. This is intentional per the docstring.
        """
        u = _make_user(900001023, is_deleted=True)
        assert can_login(u) is True

    def test_restricted_user_can_login(self) -> None:
        """User with ads_auto_publish=False can still login."""
        u = _make_user(900001024, ads_auto_publish=False)
        assert can_login(u) is True


# ---------------------------------------------------------------------------
# Tests: get_state_badge
# ---------------------------------------------------------------------------


class TestGetStateBadge:
    """get_state_badge returns correct badge text."""

    def test_normal_user_empty_badge(self, user: User) -> None:
        """Default user has empty badge."""
        assert get_state_badge(user) == ""

    def test_banned_badge(self) -> None:
        """Banned user shows 'banned'."""
        u = _make_user(900001030, is_banned=True)
        assert get_state_badge(u) == "banned"

    def test_deleted_badge(self) -> None:
        """Deleted user shows 'deleted'."""
        u = _make_user(900001031, is_deleted=True)
        assert get_state_badge(u) == "deleted"

    def test_declined_badge(self) -> None:
        """Declined user shows 'declined'."""
        u = _make_user(900001032, is_declined=True)
        assert get_state_badge(u) == "declined"

    def test_restricted_badge(self) -> None:
        """Restricted user shows 'restricted'."""
        u = _make_user(900001033, ads_auto_publish=False)
        assert get_state_badge(u) == "restricted"

    def test_all_flags_combined_badge(self) -> None:
        """All flags together show comma-separated badges."""
        u = _make_user(
            900001034,
            is_banned=True,
            is_deleted=True,
            is_declined=True,
            ads_auto_publish=False,
        )
        badge = get_state_badge(u)
        assert "banned" in badge
        assert "deleted" in badge
        assert "declined" in badge
        assert "restricted" in badge

    def test_no_badge_for_default_user(self) -> None:
        """User with default flags returns empty string."""
        u = _make_user(900001035)
        assert get_state_badge(u) == ""