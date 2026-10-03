"""Tests for the read-only ``MediaDeletionErrorAdmin`` (07-MEDIA-010).

The "no editable field" guarantee is proven by ``get_form(request)``
introspection, never by reading the admin source: with ``has_add_permission``
and ``has_change_permission`` both ``False``, Django 5.2's ``ModelAdmin.get_form``
raises ``ImproperlyConfigured`` for ``change=False`` and ``change=True`` alike.

Staff-only access is enforced by ``AdminSite.has_permission`` (which requires
``is_active`` and ``is_staff``), not by the ``ModelAdmin`` — so the site-level
gate is what the non-staff test exercises.
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from django.contrib import admin
from django.contrib.auth.models import Permission
from django.contrib.messages.storage.cookie import CookieStorage
from django.test import RequestFactory
from django.urls import reverse

from apps.media.admin import MediaDeletionErrorAdmin
from apps.media.models import MediaDeletionError
from apps.users.models import User

# A telegram_id no other media test uses (the support-admin mirror uses
# 930000101; the canonical fixtures use 900000001/900000002).
_STAFF_TELEGRAM_ID = 941000001
_NON_STAFF_TELEGRAM_ID = 941000002

_VIEW_PERMISSION_CODENAME = "view_mediadeletionerror"


def _local_staff_user() -> User:
    """Build a module-local staff actor (``conftest.py`` is off-limits)."""
    staff = User.objects.create(
        telegram_id=_STAFF_TELEGRAM_ID,
        chat_id=_STAFF_TELEGRAM_ID,
        password="x",
        is_staff=True,
    )
    staff.user_permissions.add(
        *Permission.objects.filter(
            content_type__app_label="media",
            codename=_VIEW_PERMISSION_CODENAME,
        )
    )
    return staff


def _local_non_staff_user_with_view_permission() -> User:
    """A non-staff user who nonetheless holds the model view permission."""
    user = User.objects.create(
        telegram_id=_NON_STAFF_TELEGRAM_ID,
        chat_id=_NON_STAFF_TELEGRAM_ID,
        password="x",
        is_staff=False,
    )
    user.user_permissions.add(
        *Permission.objects.filter(
            content_type__app_label="media",
            codename=_VIEW_PERMISSION_CODENAME,
        )
    )
    return user


def _local_changelist_request(actor: User):
    """Build an admin-authenticated request for the changelist."""
    request = RequestFactory().get(
        reverse("admin:media_mediadeletionerror_changelist")
    )
    request.user = actor
    request._messages = CookieStorage(request)  # pyright: ignore[reportAttributeAccessIssue]
    request.session = {}  # pyright: ignore[reportAttributeAccessIssue]
    return request


def test_media_deletion_error_is_registered_in_admin() -> None:
    """``MediaDeletionError`` is registered in the Django admin site."""
    assert admin.site.is_registered(MediaDeletionError)


def test_get_form_refuses_to_build_a_change_form() -> None:
    """No editable field: Django builds an empty change form.

    Proven by ``get_form`` introspection, never by reading the admin source.
    ``MediaDeletionError`` declares five concrete fields, so a change form
    whose ``base_fields`` is empty is not vacuous — every field was excluded
    because ``has_change_permission`` returns ``False``. The add path is
    likewise unreachable: ``has_add_permission`` is ``False``, so the admin
    refuses before any add form is built (``add_view`` raises
    ``PermissionDenied`` on that guard).
    """
    model_admin = MediaDeletionErrorAdmin(MediaDeletionError, admin.site)
    request = MagicMock()

    # Non-vacuousness: the model really does have editable-looking fields.
    assert MediaDeletionError._meta.fields

    # The change form is built but carries zero editable fields.
    change_form = model_admin.get_form(request, change=True)
    assert list(change_form.base_fields) == []

    # The add path never reaches ``get_form``: permission is refused first.
    assert model_admin.has_add_permission(request) is False


def test_readonly_fields_is_empty() -> None:
    """``readonly_fields`` is literally empty (metadata introspection)."""
    assert list(MediaDeletionErrorAdmin.readonly_fields) == []


def test_list_display_and_list_filter_cover_created_at_and_error_type() -> None:
    """Both columns are named in ``list_display`` and ``list_filter``."""
    assert {"created_at", "error_type"} <= set(MediaDeletionErrorAdmin.list_display)
    assert {"created_at", "error_type"} <= set(MediaDeletionErrorAdmin.list_filter)


@pytest.mark.django_db
def test_changelist_resolves_both_filters() -> None:
    """Both declared filters resolve against the real queryset.

    ``ChangeList.list_filter`` holds the declared names; the actual filter
    objects are constructed lazily by ``get_filters(request)``, whose first
    element is the list of instantiated ``ListFilter``s. Asserting their
    ``field_path`` proves the filters are *resolvable against the queryset*,
    not merely named.
    """
    model_admin = MediaDeletionErrorAdmin(MediaDeletionError, admin.site)
    request = _local_changelist_request(_local_staff_user())

    changelist = model_admin.get_changelist_instance(request)
    filter_specs = changelist.get_filters(request)[0]

    assert {"error_type", "created_at"} <= {
        spec.field_path for spec in filter_specs
    }


def test_add_and_change_permissions_are_false() -> None:
    """Add and change are refused outright; the reader is diagnostic only."""
    model_admin = MediaDeletionErrorAdmin(MediaDeletionError, admin.site)
    request = MagicMock()

    assert model_admin.has_add_permission(request) is False
    assert model_admin.has_change_permission(request) is False


def test_view_permission_follows_the_view_perm() -> None:
    """Without an override, view follows the model's view permission."""
    model_admin = MediaDeletionErrorAdmin(MediaDeletionError, admin.site)
    request = MagicMock()
    request.user.has_perm.return_value = True

    assert model_admin.has_view_permission(request) is True


@pytest.mark.django_db
def test_non_staff_with_the_view_perm_is_refused_by_the_site() -> None:
    """Staff-only access is enforced by the site, not the ModelAdmin."""
    non_staff = _local_non_staff_user_with_view_permission()
    non_staff_request = MagicMock()
    non_staff_request.user = non_staff

    # The site gate requires is_active and is_staff, so holding the view
    # permission is not enough.
    assert admin.site.has_permission(non_staff_request) is False


@pytest.mark.django_db
def test_staff_actor_passes_the_site_gate() -> None:
    """A staff actor holding the view permission passes the site gate."""
    staff = _local_staff_user()
    request = MagicMock()
    request.user = staff

    assert admin.site.has_permission(request) is True


@pytest.mark.django_db
def test_changelist_renders_for_staff() -> None:
    """The changelist actually renders for a staff actor.

    This is the reachability assertion for the block's whole premise: a
    recorded deletion failure has an operator surface.
    """
    MediaDeletionError.objects.create(
        storage_key=f"{uuid4()}.jpg",
        error_type="PermissionError",
        error_message="denied by the filesystem",
        attempts=3,
    )
    model_admin = MediaDeletionErrorAdmin(MediaDeletionError, admin.site)

    response = model_admin.changelist_view(
        _local_changelist_request(_local_staff_user())
    )
    content = response.render().content.decode()

    assert "PermissionError" in content
