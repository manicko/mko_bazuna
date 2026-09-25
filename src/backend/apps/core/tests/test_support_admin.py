"""
Tests for core admin registration of SupportContact and SupportTicket (B4).

Covers:
- SupportContact and SupportTicket are registered in the Django admin
- SupportTicketAdmin has_add_permission returns False
- SupportTicketAdmin has_delete_permission returns False

All checks are pure metadata/introspection — no database access required.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from django.contrib import admin

from apps.core.models import SupportContact, SupportTicket

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
    """``SupportTicketAdmin.list_display`` contains the expected fields."""
    from apps.core.admin import SupportTicketAdmin

    expected = ["ticket_ref", "status", "user", "chat_id", "telegram_id", "created_at"]
    assert list(SupportTicketAdmin.list_display) == expected


def test_support_ticket_admin_list_filter() -> None:
    """``SupportTicketAdmin.list_filter`` contains status and created_at."""
    from apps.core.admin import SupportTicketAdmin

    assert list(SupportTicketAdmin.list_filter) == ["status", "created_at"]


def test_support_ticket_admin_search_fields() -> None:
    """``SupportTicketAdmin.search_fields`` contains ticket_ref, telegram_id, username, text."""
    from apps.core.admin import SupportTicketAdmin

    assert list(SupportTicketAdmin.search_fields) == [
        "ticket_ref",
        "telegram_id",
        "username",
        "text",
    ]


def test_support_ticket_admin_readonly_fields() -> None:
    """``SupportTicketAdmin.readonly_fields`` is fully read-only."""
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
