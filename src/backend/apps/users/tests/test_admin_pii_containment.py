"""
PII containment regression tests for staff admin list_display.

Guards PII-001 / VAL-001: no admin list_display helper may render the raw
external ``telegram_id`` identifier. All four affected helpers must instead
render a non-identifying value (``str(obj.user)`` = "User <pk>" for the
User-FK helpers; ``mask_telegram_id(...)`` for the standalone LoginToken).

Residual limit of this guard (06-PII-106): it enumerates masking helpers and
asserts what each one *does*, so it cannot catch a future admin that renders a
raw identity column **without** a helper — a new raw column added directly to
``list_display`` is simply not enumerated. This is the same class of limit the
PII-001 guard already has. Do not "simplify" this module into a blanket ban on
the ``telegram_id`` token: docstrings here legitimately name the field in prose
and ``SupportContactAdmin.telegram_id`` is a configured support-channel id, not
a data subject's, so a token ban would false-positive on correct code.
"""

from __future__ import annotations

import inspect
import re

import pytest
from django import forms
from django.contrib import admin
from django.contrib.admin.utils import flatten_fieldsets
from django.contrib.auth.forms import (
    ReadOnlyPasswordHashField,
    ReadOnlyPasswordHashWidget,
)
from django.contrib.messages.storage.cookie import CookieStorage
from django.forms import Field
from django.test import RequestFactory

from apps.users.admin import LoginTokenAdmin, UserAdmin
from apps.users.models import User

pytestmark = [pytest.mark.unit]

# A known raw password whose hash is stored on the change-form target. The
# PBKDF2 hash is long and recognisable, so a leak into the rendered field is
# detectable even by a substring.
_KNOWN_RAW_PASSWORD = "correct horse battery staple"
# Minimum hash-segment length treated as a leak. A segment shorter than this
# (e.g. the ``pbkdf2_sha256`` algorithm name) is not credential material.
_MIN_LEAK_SEGMENT = 8


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


def test_support_ticket_chat_id_display_masks_identifier() -> None:
    """``SupportTicketAdmin.chat_id_display`` delegates to the mask helper (06-PII-106)."""
    from apps.core.admin import SupportTicketAdmin

    assert "chat_id" not in SupportTicketAdmin.list_display
    assert "chat_id_display" in SupportTicketAdmin.list_display
    source = inspect.getsource(SupportTicketAdmin.chat_id_display)
    assert "mask_telegram_id" in source
    assert "obj.chat_id" in source


def test_support_ticket_telegram_id_display_masks_identifier() -> None:
    """``SupportTicketAdmin.telegram_id_display`` delegates to the mask helper (06-PII-106)."""
    from apps.core.admin import SupportTicketAdmin

    assert "telegram_id" not in SupportTicketAdmin.list_display
    assert "telegram_id_display" in SupportTicketAdmin.list_display
    source = inspect.getsource(SupportTicketAdmin.telegram_id_display)
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


def _read_only_password_violations(field: Field, rendered: str) -> list[str]:
    """Return violations for the change form's ``password`` field; ``[]`` is compliant.

    The invariant (04-AUT-005): the field is a disabled ``ReadOnlyPasswordHashField``
    whose ``ReadOnlyPasswordHashWidget`` renders a masked summary — the stored
    hash is never emitted as a ``value`` and no text input can write it.

    Split out from the guard so the negative-control test can prove the
    predicate detects an editable field instead of only passing today's Django
    widget. ``rendered`` is the widget's HTML for the stored ``initial`` value;
    pass ``""`` to check the field contract alone.
    """
    violations: list[str] = []
    if not isinstance(field, ReadOnlyPasswordHashField):
        violations.append(
            f"password must be a ReadOnlyPasswordHashField, got {type(field).__name__}"
        )
    if not isinstance(field.widget, ReadOnlyPasswordHashWidget):
        violations.append(
            "password widget must be a ReadOnlyPasswordHashWidget, got "
            f"{type(field.widget).__name__}"
        )
    if field.disabled is not True:
        violations.append(f"password must be disabled, got disabled={field.disabled!r}")
    if not rendered:
        return violations

    if _KNOWN_RAW_PASSWORD in rendered:
        violations.append("the raw password appears in the rendered field")
    if _hash_leaked(field.initial, rendered):
        violations.append("the stored password hash appears in the rendered field")
    if re.search(r'name="password"[^>]*value=', rendered):
        violations.append(
            'a name="password" input carries a value= attribute (hash disclosure)'
        )
    return violations


def _hash_leaked(stored: object, rendered: str) -> bool:
    """Return ``True`` if ``stored`` (the password hash) leaks into ``rendered``.

    A hash is ``<algorithm>$<params>$<salt>$<digest>``; any segment longer than
    ``_MIN_LEAK_SEGMENT`` is credential material and must never be rendered.
    """
    if not isinstance(stored, str) or not stored:
        return False
    if stored in rendered:
        return True
    return any(
        segment in rendered
        for segment in stored.split("$")
        if len(segment) > _MIN_LEAK_SEGMENT
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
    """``password`` is never a writable field and never renders the stored hash.

    Behavioural, not attribute-introspective (04-AUT-005): an earlier revision
    asserted the undocumented ``Widget.read_only`` attribute, which Django 6.x
    removed. The invariant is asserted through the ``ReadOnlyPasswordHashField``
    contract plus the rendered output, which holds across Django versions.
    """
    target = User(telegram_id=930000002, chat_id=930000002, username="target")
    target.set_password(_KNOWN_RAW_PASSWORD)
    user_admin = UserAdmin(User, admin.site)
    form = user_admin.get_form(_admin_request(staff_user), target, change=True)
    assert "password" in form.base_fields, (
        "the change form must expose password as a read-only field (04-AUT-005)"
    )
    field = form.base_fields["password"]
    rendered = field.widget.render("password", field.initial, attrs={"id": "id_password"})
    violations = _read_only_password_violations(field, rendered)
    assert not violations, (
        "password must be a non-editable, non-disclosing field (04-AUT-005): "
        + "; ".join(violations)
    )


def test_password_read_only_predicate_detects_a_writable_field() -> None:
    """The predicate reports a plain writable text input (negative control).

    A guard that only passes today's Django field is not a guard: if the
    ``ReadOnlyPasswordHashField`` were ever swapped for an editable field, this
    predicate must go red.
    """
    writable = forms.CharField(widget=forms.TextInput, disabled=False)
    violations = _read_only_password_violations(writable, "")
    assert violations
    assert any("ReadOnlyPasswordHashField" in v for v in violations), violations
    assert any("disabled" in v for v in violations), violations


@pytest.mark.django_db
def test_change_form_fieldsets_name_only_real_model_fields(staff_user: User) -> None:
    """Every field named in the change fieldsets resolves against the live model.

    A ``fieldsets`` entry naming a field absent from the resolved form raises
    ``FieldError`` at ``get_form()`` time and turns every add and change request
    into a 500. The valid set must match what Django actually resolves against
    (``concrete_fields + many_to_many + private_fields`` as used by
    ``fields_for_model``), *not* ``User._meta.get_fields()``: the latter also
    returns reverse relations (``ads``, ``logentry``, ``trust_score``, ...),
    which are not form fields, so naming one here would pass this tripwire and
    still 500 at runtime.
    """
    user_admin = UserAdmin(User, admin.site)
    obj = User(telegram_id=930000002, chat_id=930000002, username="target")
    valid = (
        {f.name for f in User._meta.concrete_fields}
        | {f.name for f in User._meta.many_to_many}
        | {f.name for f in User._meta.private_fields}
    )
    named_fields = flatten_fieldsets(user_admin.get_fieldsets(_admin_request(staff_user), obj))
    assert named_fields, "the change fieldsets must not be empty"
    unknown = [name for name in named_fields if name not in valid]
    assert unknown == [], f"fieldsets name fields the model does not have: {unknown}"


@pytest.mark.django_db
def test_change_form_keeps_preferred_city_writable(staff_user: User) -> None:
    """The change form exposes exactly one writable field: ``preferred_city``.

    The other introspection tests are all *absent-or-disabled* assertions, so a
    fieldsets/base_fields collapse to empty would satisfy every one of them
    while silently removing the operator capability this block retains. This is
    the anti-vacuity guard: the writable field must still be present and enabled.
    """
    user_admin = UserAdmin(User, admin.site)
    obj = User(telegram_id=930000002, chat_id=930000002, username="target")
    form = user_admin.get_form(_admin_request(staff_user), obj, change=True)
    assert "preferred_city" in form.base_fields, (
        "preferred_city must remain present on the change form (04-AUT-005)"
    )
    assert form.base_fields["preferred_city"].disabled is False, (
        "preferred_city must remain writable on the change form (04-AUT-005)"
    )


@pytest.mark.django_db
def test_change_form_fieldset_never_exposes_an_uneditable_field(staff_user: User) -> None:
    """No fieldset entry can reach ``form[name]`` with a missing field.

    When a field is hidden via ``exclude`` (or ``form.Meta.exclude``) while
    ``fieldsets`` still names it, ``Fieldline.__iter__`` builds
    ``AdminField(self.form, name)`` and ``form[name]`` raises ``KeyError`` -> a
    500 on the add/change page. The KeyError is therefore unreachable exactly
    when every fieldset name is either present in ``form.base_fields`` or listed
    in ``get_readonly_fields()`` (readonly entries render via AdminReadonlyField
    and never index the form).
    """
    user_admin = UserAdmin(User, admin.site)
    obj = User(telegram_id=930000002, chat_id=930000002, username="target")
    form = user_admin.get_form(_admin_request(staff_user), obj, change=True)
    readonly = set(user_admin.get_readonly_fields(_admin_request(staff_user), obj))
    named_fields = flatten_fieldsets(user_admin.get_fieldsets(_admin_request(staff_user), obj))
    unresolvable = [
        name
        for name in named_fields
        if name not in form.base_fields and name not in readonly
    ]
    assert unresolvable == [], (
        f"fieldsets name fields that are neither form fields nor read-only: {unresolvable}"
    )

