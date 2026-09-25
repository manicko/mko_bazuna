"""
Tests for the UserRole StrEnum and User.role property (AUTZ-003).

Covers:
- UserRole enum members and string values match the Phase 15 spec.
- User.role maps identity flags to UserRole correctly across all branches.
"""

import pytest
from django.contrib.auth.models import AnonymousUser

from apps.core.enums import UserRole
from apps.users.models import User
from conftest import make_user

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestUserRoleEnum:
    """UserRole StrEnum membership and values (Phase 15 spec)."""

    def test_members_match_spec(self) -> None:
        """The enum has exactly ANONYMOUS, SELLER, ADMIN per Phase 15 spec."""
        assert set(UserRole) == {UserRole.ANONYMOUS, UserRole.SELLER, UserRole.ADMIN}

    def test_values_are_strings(self) -> None:
        """StrEnum members coerce to their lowercase string values."""
        assert UserRole.ADMIN.value == "admin"
        assert UserRole.SELLER.value == "seller"
        assert UserRole.ANONYMOUS.value == "anonymous"

    def test_str_coerces_to_value(self) -> None:
        """UserRole behaves as a plain string (StrEnum invariant)."""
        assert str(UserRole.ADMIN) == "admin"
        assert UserRole.ADMIN == "admin"


class TestUserRoleMapping:
    """User.role property maps identity flags to UserRole."""

    def test_staff_is_admin(self) -> None:
        """is_staff=True → ADMIN (even if is_superuser is False)."""
        user = make_user(900000091, is_staff=True)
        assert user.is_staff
        assert not user.is_superuser
        assert user.role == UserRole.ADMIN

    def test_superuser_is_admin_without_staff(self) -> None:
        """is_superuser=True, is_staff=False → ADMIN."""
        user = make_user(900000092, is_superuser=True)
        assert not user.is_staff
        assert user.is_superuser
        assert user.role == UserRole.ADMIN

    def test_regular_authenticated_is_seller(self) -> None:
        """Neither staff nor superuser → SELLER."""
        user = make_user(900000093)
        assert not user.is_staff
        assert not user.is_superuser
        assert user.is_authenticated
        assert user.role == UserRole.SELLER

    def test_anonymous_identity_is_anonymous(self) -> None:
        """An unauthenticated identity (AnonymousUser) resolves to ANONYMOUS.

        AnonymousUser has is_staff=False, is_superuser=False,
        is_authenticated=False — matching the property's ANONYMOUS branch.
        Invoked via the property descriptor since AnonymousUser does not
        subclass User.
        """
        anonymous = AnonymousUser()
        assert not anonymous.is_authenticated
        getter = User.role.fget
        assert getter is not None
        assert getter(anonymous) == UserRole.ANONYMOUS
