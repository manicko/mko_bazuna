"""
Tests for core admin registration of SupportContact and SupportTicket (B4).

Covers:
- SupportContact and SupportTicket are registered in the Django admin
- SupportTicketAdmin has_add_permission returns False
- SupportTicketAdmin has_delete_permission returns False
- SupportTicketAdmin masks the requester's identifiers in the changelist and
  no longer searches the unbounded ticket body (06-PII-106)

Metadata/introspection checks need no database; the changelist-rendering and
search behaviour tests build their own rows and are marked ``django_db``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from django.contrib import admin
from django.contrib.auth.models import Permission
from django.contrib.messages.storage.cookie import CookieStorage
from django.test import RequestFactory
from django.urls import reverse

from apps.core.models import SupportContact, SupportTicket
from apps.core.utils.sanitize import mask_telegram_id
from apps.users.models import User

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Admin registration
# ---------------------------------------------------------------------------


def test_support_contact_registered_in_admin() -> None:
    """``SupportContact`` is registered in the Django admin site."""
    assert admin.site.is_registered(SupportContact)


def test_support_ticket_registered_in_admin() -> None:
    """``SupportTicket`` is registered in the Django admin site."""
    assert admin.site.is_registered(SupportTicket)


def test_support_contact_admin_list_display() -> None:
    """``SupportContactAdmin.list_display`` contains the expected fields."""
    from apps.core.admin import SupportContactAdmin

    expected = ["label", "channel_type", "email", "telegram_id", "is_active", "ordering"]
    assert list(SupportContactAdmin.list_display) == expected


def test_support_contact_admin_list_editable() -> None:
    """``SupportContactAdmin.list_editable`` contains is_active and ordering."""
    from apps.core.admin import SupportContactAdmin

    assert list(SupportContactAdmin.list_editable) == ["is_active", "ordering"]


def test_support_contact_admin_list_filter() -> None:
    """``SupportContactAdmin.list_filter`` contains channel_type and is_active."""
    from apps.core.admin import SupportContactAdmin

    assert list(SupportContactAdmin.list_filter) == ["channel_type", "is_active"]


def test_support_contact_admin_search_fields() -> None:
    """``SupportContactAdmin.search_fields`` contains label, email, telegram_id."""
    from apps.core.admin import SupportContactAdmin

    assert list(SupportContactAdmin.search_fields) == ["label", "email", "telegram_id"]


def test_support_contact_admin_add_enabled() -> None:
    """``SupportContactAdmin`` allows adding (no override)."""
    from apps.core.admin import SupportContactAdmin

    instance = SupportContactAdmin(SupportContact, admin.site)
    request = MagicMock()
    request.user.has_perm.return_value = True
    assert instance.has_add_permission(request) is True


def test_support_contact_admin_delete_enabled() -> None:
    """``SupportContactAdmin`` allows deleting (no override)."""
    from apps.core.admin import SupportContactAdmin

    instance = SupportContactAdmin(SupportContact, admin.site)
    request = MagicMock()
    request.user.has_perm.return_value = True
    assert instance.has_delete_permission(request) is True


def test_support_ticket_admin_list_display() -> None:
    """``SupportTicketAdmin.list_display`` names the masked identifier displays (06-PII-106).

    The raw ``chat_id`` / ``telegram_id`` columns are replaced by the
    ``@admin.display`` methods that delegate to ``mask_telegram_id``; the
    surrounding column order is unchanged.
    """
    from apps.core.admin import SupportTicketAdmin

    expected = [
        "ticket_ref",
        "status",
        "user",
        "chat_id_display",
        "telegram_id_display",
        "created_at",
    ]
    assert list(SupportTicketAdmin.list_display) == expected


def test_support_ticket_admin_list_filter() -> None:
    """``SupportTicketAdmin.list_filter`` contains status and created_at."""
    from apps.core.admin import SupportTicketAdmin

    assert list(SupportTicketAdmin.list_filter) == ["status", "created_at"]


def test_support_ticket_admin_search_fields() -> None:
    """``SupportTicketAdmin.search_fields`` drops ``text`` (06-PII-106).

    The unbounded ticket body is no longer a search target; ``telegram_id``
    deliberately stays as support's only identifier lookup.
    """
    from apps.core.admin import SupportTicketAdmin

    assert list(SupportTicketAdmin.search_fields) == [
        "ticket_ref",
        "telegram_id",
        "username",
    ]


def test_support_ticket_admin_readonly_fields() -> None:
    """``SupportTicketAdmin.readonly_fields`` is fully read-only (06-PII-106).

    Re-pinned unchanged on purpose: this block deliberately left
    ``readonly_fields`` alone — the leak was in the changelist and the search
    index, not in the change form.
    """
    from apps.core.admin import SupportTicketAdmin

    expected = [
        "ticket_ref",
        "chat_id",
        "telegram_id",
        "username",
        "text",
        "user",
        "created_at",
    ]
    assert list(SupportTicketAdmin.readonly_fields) == expected


def test_support_ticket_admin_add_permission_false() -> None:
    """``SupportTicketAdmin.has_add_permission`` returns False."""
    from apps.core.admin import SupportTicketAdmin

    instance = SupportTicketAdmin(SupportTicket, admin.site)
    request = MagicMock()
    assert instance.has_add_permission(request) is False


def test_support_ticket_admin_delete_permission_false() -> None:
    """``SupportTicketAdmin.has_delete_permission`` returns False."""
    from apps.core.admin import SupportTicketAdmin

    instance = SupportTicketAdmin(SupportTicket, admin.site)
    request = MagicMock()
    assert instance.has_delete_permission(request) is False


# ---------------------------------------------------------------------------
# SupportTicketAdmin containment behaviour (06-PII-106)
#
# These assertions are behavioural, not trivia: the changelist response must
# never contain the raw identifiers, and the ticket body must no longer be a
# free-text search target. The staff actor is built locally because
# ``src/backend/conftest.py`` is off-limits.
# ---------------------------------------------------------------------------


def _local_staff_user() -> User:
    """Build a module-local staff actor (``conftest.py`` is off-limits)."""
    staff = User.objects.create(
        telegram_id=930000101,
        chat_id=930000101,
        password="x",
        is_staff=True,
    )
    staff.user_permissions.add(
        *Permission.objects.filter(
            content_type__app_label="core",
            codename__in=("view_supportticket",),
        )
    )
    return staff


def _local_changelist_request(staff: User):
    """Build an admin-authenticated request for ``SupportTicketAdmin``."""
    request = RequestFactory().get(reverse("admin:core_supportticket_changelist"))
    request.user = staff
    request._messages = CookieStorage(request)  # pyright: ignore[reportAttributeAccessIssue]
    request.session = {}  # pyright: ignore[reportAttributeAccessIssue]
    return request


@pytest.mark.django_db
def test_support_ticket_changelist_renders_masked_identifiers() -> None:
    """The changelist row renders the masks and neither raw identifier (06-PII-106)."""
    from apps.core.admin import SupportTicketAdmin

    staff = _local_staff_user()
    raw_chat_id = 945500011
    raw_telegram_id = 945500022
    SupportTicket.objects.create(
        chat_id=raw_chat_id,
        telegram_id=raw_telegram_id,
        username="subject",
        text="Ticket body",
    )

    support_admin = SupportTicketAdmin(SupportTicket, admin.site)
    response = support_admin.changelist_view(_local_changelist_request(staff))
    content = response.render().content.decode()

    assert mask_telegram_id(raw_chat_id) in content
    assert mask_telegram_id(raw_telegram_id) in content
    assert str(raw_chat_id) not in content
    assert str(raw_telegram_id) not in content


@pytest.mark.django_db
def test_support_ticket_search_does_not_match_body_text() -> None:
    """A term only in the ticket body matches no row; ``ticket_ref`` still does (06-PII-106)."""
    from apps.core.admin import SupportTicketAdmin

    ticket = SupportTicket.objects.create(
        chat_id=945500033,
        telegram_id=945500044,
        username="subject",
        text="a uniquebodytoken-marker phrase",
    )
    support_admin = SupportTicketAdmin(SupportTicket, admin.site)
    request = _local_changelist_request(_local_staff_user())
    base = support_admin.get_queryset(request)

    body_matches = support_admin.get_search_results(
        request, base, "uniquebodytoken-marker"
    )[0]
    assert list(body_matches) == []

    ref_matches = support_admin.get_search_results(
        request, base, ticket.ticket_ref
    )[0]
    assert list(ref_matches) == [ticket]


@pytest.mark.django_db
def test_support_ticket_search_still_matches_raw_telegram_id() -> None:
    """Searching the raw numeric ``telegram_id`` still finds the ticket (06-PII-106)."""
    from apps.core.admin import SupportTicketAdmin

    raw_telegram_id = 945500055
    ticket = SupportTicket.objects.create(
        chat_id=945500066,
        telegram_id=raw_telegram_id,
        username="subject",
        text="Ticket body",
    )
    support_admin = SupportTicketAdmin(SupportTicket, admin.site)
    request = _local_changelist_request(_local_staff_user())
    base = support_admin.get_queryset(request)

    matches = support_admin.get_search_results(
        request, base, str(raw_telegram_id)
    )[0]
    assert list(matches) == [ticket]
