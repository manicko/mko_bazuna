"""
PII containment regression tests for staff admin list_display.

Guards PII-001 / VAL-001: no admin list_display helper may render the raw
external ``telegram_id`` identifier. All four affected helpers must instead
render a non-identifying value (``str(obj.user)`` = "User <pk>" for the
User-FK helpers; ``mask_telegram_id(...)`` for the standalone LoginToken).
"""

from __future__ import annotations

import inspect

import pytest
from django.contrib import admin
from django.contrib.admin.utils import flatten_fieldsets
from django.contrib.messages.storage.cookie import CookieStorage
from django.test import RequestFactory

from apps.users.admin import LoginTokenAdmin, UserAdmin
from apps.users.models import User

pytestmark = [pytest.mark.unit]


def _assert_no_raw_telegram_id(source: str) -> None:
    """Assert ``source`` does not render the raw telegram_id identifier.

    The assertion targets the rendering statement ``str(obj.user.telegram_id)``
    (the PII-001 leak) rather than the bare token, because the helper docstrings
    legitimately reference ``telegram_id`` in prose and are intentionally kept.
    """
    assert "str(obj.user.telegram_id)" not in source, (
        "admin list_display helper must not render the raw telegram_id (PII-001)"
    )


def test_ads_user_link_hides_telegram_id() -> None:
    """``ads.admin.user_link`` renders a non-identifying value."""
    from apps.ads.admin import user_link

    _assert_no_raw_telegram_id(inspect.getsource(user_link))
    assert getattr(user_link, "short_description") == "User ID"  # noqa: B009


def test_analytics_user_link_hides_telegram_id() -> None:
    """``AnalyticsEventAdmin.user_link`` renders a non-identifying value."""
    from apps.analytics.admin import AnalyticsEventAdmin

    _assert_no_raw_telegram_id(inspect.getsource(AnalyticsEventAdmin.user_link))
    assert AnalyticsEventAdmin.user_link.short_description == "User ID"


def test_moderation_log_user_link_hides_telegram_id() -> None:
    """``moderation.admin.log_user_link`` renders a non-identifying value."""
    from apps.moderation.admin import log_user_link

    _assert_no_raw_telegram_id(inspect.getsource(log_user_link))
    assert getattr(log_user_link, "short_description") == "User ID"  # noqa: B009


def test_login_token_list_display_masks_telegram_id() -> None:
    """``LoginTokenAdmin.list_display`` uses the masked display, not the raw field."""
    assert "telegram_id" not in LoginTokenAdmin.list_display
    assert "telegram_id_display" in LoginTokenAdmin.list_display
    # The display method delegates to mask_telegram_id (VAL-001)
    source = inspect.getsource(LoginTokenAdmin.telegram_id_display)
    assert "mask_telegram_id" in source
    assert "obj.telegram_id" in source


# ---------------------------------------------------------------------------
# UserAdmin field-contract introspection (finding 04-AUT-005)
#
# These tests call ``UserAdmin.get_form()`` / ``get_fieldsets()`` exactly the
# way Django's add and change views do. Because ``preferred_city`` is a
# writable foreign key, ``ModelAdmin.get_form()`` runs the related admin's
# permission callbacks against ``request.user`` (a DB query), so the tests
# need a persisted staff actor and are marked ``django_db``.
# ---------------------------------------------------------------------------


def _admin_request(user: User):
    """Build a ``RequestFactory`` request carrying a real user and messages."""
    request = RequestFactory().get("/admin/")
    request.user = user
    request._messages = CookieStorage(request)  # pyright: ignore[reportAttributeAccessIssue]
    return request


@pytest.fixture
def staff_user() -> User:
    """Module-local staff (non-superuser) actor — ``conftest.py`` is off-limits."""
    return User.objects.create(
        telegram_id=930000001,
        chat_id=930000001,
        password="x",
        is_staff=True,
    )


@pytest.mark.django_db
def test_change_form_has_no_writable_privilege_field(staff_user: User) -> None:
    """``is_superuser`` / ``is_staff`` / ``groups`` / ``user_permissions`` are not writable."""
    user_admin = UserAdmin(User, admin.site)
    obj = User(telegram_id=930000002, chat_id=930000002, username="target")
    form = user_admin.get_form(_admin_request(staff_user), obj, change=True)
    for name in ("is_superuser", "is_staff", "groups", "user_permissions"):
        assert name not in form.base_fields or form.base_fields[name].disabled is True, (
            f"{name} must have no writable path in the change form (04-AUT-005)"
        )


@pytest.mark.django_db
def test_change_form_has_no_writable_account_state_field(staff_user: User) -> None:
    """Consent and account-state booleans have no writable path in the change form."""
    user_admin = UserAdmin(User, admin.site)
    obj = User(telegram_id=930000002, chat_id=930000002, username="target")
    form = user_admin.get_form(_admin_request(staff_user), obj, change=True)
    for name in ("is_banned", "is_deleted", "is_declined", "ads_auto_publish"):
        assert name not in form.base_fields or form.base_fields[name].disabled is True, (
            f"{name} must not be writable through the change form (04-AUT-005)"
        )


@pytest.mark.django_db
def test_change_form_password_is_never_a_writable_field(staff_user: User) -> None:
    """``password`` is either absent or a disabled, non-editable read-only field."""
    user_admin = UserAdmin(User, admin.site)
    obj = User(telegram_id=930000002, chat_id=930000002, username="target")
    form = user_admin.get_form(_admin_request(staff_user), obj, change=True)
    if "password" in form.base_fields:
        field = form.base_fields["password"]
        assert field.disabled is True, "password must be disabled (04-AUT-005)"
        assert field.widget.read_only is True, (
            "password widget must be non-editable (04-AUT-005)"
        )


@pytest.mark.django_db
def test_change_form_fieldsets_name_only_real_model_fields(staff_user: User) -> None:
    """Every field named in the change fieldsets resolves against the live model.

    A ``fieldsets`` entry naming a nonexistent field raises ``FieldError`` at
    form-construction time and 500s every add and change request. This is the
    structural tripwire for that failure mode.
    """
    user_admin = UserAdmin(User, admin.site)
    obj = User(telegram_id=930000002, chat_id=930000002, username="target")
    model_field_names = {field.name for field in User._meta.get_fields()}
    named_fields = flatten_fieldsets(user_admin.get_fieldsets(_admin_request(staff_user), obj))
    assert named_fields, "the change fieldsets must not be empty"
    unknown = [name for name in named_fields if name not in model_field_names]
    assert unknown == [], f"fieldsets name fields the model does not have: {unknown}"


def test_withdraw_consent_action_is_still_registered() -> None:
    """``withdraw_consent_action`` survives on ``UserAdmin`` after B-01.

    Verified against Django 5.2: a method decorated with ``@admin.action`` is
    only offered by ``get_actions()`` when its name is listed in
    ``ModelAdmin.actions``, and ``ModelAdmin.actions`` defaults to ``()``.
    ``UserAdmin`` has never listed it, so the erasure action is *declared* on
    the class but *not offered* by the changelist — B-01 must preserve both
    facts and must not start offering it (that would be a new operator surface).
    The assertion pins the declaration, its ``@admin.action`` metadata and the
    unchanged empty ``actions`` declaration.
    """
    assert hasattr(UserAdmin, "withdraw_consent_action")
    assert UserAdmin.withdraw_consent_action.short_description == (  # pyright: ignore[reportFunctionMemberAccess]
        "Withdraw consent for selected users"
    )
    assert UserAdmin.actions == ()
