"""
Tests for SupportContact cache service and signal invalidation (Block B3).

Covers:
- get_support_contacts returns active SupportContact rows from DB
- get_support_contacts caches on second call (no DB hit)
- get_support_contacts falls back to [] on DB error (fail-open)
- post_save signal invalidates cache on save
- post_delete signal invalidates cache on delete
- get_support_contacts_async returns correct result
- get_email_contacts filters to EMAIL channel type
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from asgiref.sync import async_to_sync
from django.core.cache import cache

from apps.core.enums import SupportChannelType
from apps.core.models import SupportContact
from apps.core.services.support import (
    get_email_contacts,
    get_email_contacts_async,
    get_support_contacts,
    get_support_contacts_async,
)
from apps.core.utils.cache import get_cached_support_contacts

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear the LocMemCache before and after each test."""
    cache.clear()
    yield
    cache.clear()


def _make_email_contact(
    label: str = "Email support",
    email: str = "support@example.com",
    is_active: bool = True,
    ordering: int = 0,
) -> SupportContact:
    """Create an active EMAIL-channel SupportContact."""
    return SupportContact.objects.create(
        channel_type=SupportChannelType.EMAIL,
        label=label,
        email=email,
        is_active=is_active,
        ordering=ordering,
    )


def _make_telegram_contact(
    label: str = "Telegram support",
    telegram_id: int = 123456789,
    is_active: bool = True,
    ordering: int = 0,
) -> SupportContact:
    """Create an active TELEGRAM-channel SupportContact."""
    return SupportContact.objects.create(
        channel_type=SupportChannelType.TELEGRAM,
        label=label,
        telegram_id=telegram_id,
        is_active=is_active,
        ordering=ordering,
    )


# ---------------------------------------------------------------------------
# get_support_contacts — DB read
# ---------------------------------------------------------------------------


def test_get_support_contacts_returns_active_contacts() -> None:
    """get_support_contacts() returns only active SupportContact rows from DB."""
    active = _make_email_contact(label="Active", email="active@example.com")
    _make_email_contact(
        label="Inactive", email="inactive@example.com", is_active=False
    )

    result = get_support_contacts()
    assert len(result) == 1
    assert result[0].pk == active.pk
    assert result[0].email == "active@example.com"


def test_get_support_contacts_returns_empty_when_none_active() -> None:
    """get_support_contacts() returns [] when no contacts are active."""
    _make_email_contact(label="Inactive", email="inactive@example.com", is_active=False)

    result = get_support_contacts()
    assert result == []


def test_get_support_contacts_orders_by_ordering_then_id() -> None:
    """Results are ordered by 'ordering' then 'id' as defined in the model Meta."""
    _make_email_contact(label="Second", email="second@example.com", ordering=1)
    _make_email_contact(label="First", email="first@example.com", ordering=0)

    result = get_support_contacts()
    labels = [c.label for c in result]
    assert labels == ["First", "Second"]


# ---------------------------------------------------------------------------
# get_support_contacts — caching
# ---------------------------------------------------------------------------


def test_get_support_contacts_reads_from_cache() -> None:
    """Second call to get_support_contacts() hits the cache without DB access."""
    _make_email_contact(label="Cached", email="cached@example.com")

    # Prime the cache
    assert len(get_support_contacts()) == 1

    # Verify cache is populated
    assert get_cached_support_contacts() is not None

    # Second call should NOT access the DB (cache hit).  If filter() were
    # called the side_effect would raise, the except block would return [],
    # and the assertion below would fail.
    with patch.object(SupportContact.objects, "filter", side_effect=RuntimeError):
        result = get_support_contacts()
    assert len(result) == 1


# ---------------------------------------------------------------------------
# get_support_contacts — fail-open
# ---------------------------------------------------------------------------


def test_get_support_contacts_falls_back_on_db_error() -> None:
    """get_support_contacts() returns [] when the DB layer raises."""
    with patch.object(SupportContact.objects, "filter", side_effect=RuntimeError("db down")):
        result = get_support_contacts()
    assert result == []


def test_get_support_contacts_does_not_cache_failure() -> None:
    """A DB failure is not cached — subsequent calls recover when DB is healthy."""
    # Cache is empty (autouse fixture clears it); simulate DB failure
    with patch.object(SupportContact.objects, "filter", side_effect=RuntimeError("db down")):
        result = get_support_contacts()
    assert result == []

    # Cache should NOT have been set with the failure result
    assert get_cached_support_contacts() is None

    # DB is now available — next call should read from DB normally
    contact = _make_email_contact(label="OK", email="ok@example.com")
    result = get_support_contacts()
    assert len(result) == 1
    assert result[0].pk == contact.pk


# ---------------------------------------------------------------------------
# Signal invalidation
# ---------------------------------------------------------------------------


def test_post_save_invalidates_support_contacts_cache() -> None:
    """Saving a new SupportContact invalidates the cache so next read sees it."""
    _make_email_contact(label="First", email="first@example.com")

    # Prime the cache
    assert len(get_support_contacts()) == 1

    # Add a second contact — post_save signal should invalidate the cache
    _make_email_contact(label="Second", email="second@example.com", ordering=1)

    # Cache should have been invalidated
    assert get_cached_support_contacts() is None

    # Next read should reflect the new contact
    result = get_support_contacts()
    assert len(result) == 2


def test_post_delete_invalidates_support_contacts_cache() -> None:
    """Deleting a SupportContact invalidates the cache so next read excludes it."""
    first = _make_email_contact(label="ToDelete", email="delete@example.com")
    _make_email_contact(label="Keep", email="keep@example.com", ordering=1)

    # Prime the cache
    assert len(get_support_contacts()) == 2

    # Delete one — post_delete signal should invalidate the cache
    first.delete()

    # Cache should have been invalidated
    assert get_cached_support_contacts() is None

    # Next read should reflect the deletion
    result = get_support_contacts()
    assert len(result) == 1


def test_post_save_on_inactive_contact_invalidates_cache() -> None:
    """Saving an update to an existing contact (e.g. is_active) invalidates cache."""
    contact = _make_email_contact(label="Active", email="active@example.com")

    # Prime the cache
    assert len(get_support_contacts()) == 1

    # Deactivate and save — post_save signal should invalidate the cache
    contact.is_active = False
    contact.save()

    # Cache should have been invalidated
    assert get_cached_support_contacts() is None

    # Next read should reflect the change
    result = get_support_contacts()
    assert len(result) == 0


# ---------------------------------------------------------------------------
# Async wrapper
# ---------------------------------------------------------------------------


def test_get_support_contacts_async_returns_contacts() -> None:
    """get_support_contacts_async() returns active contacts via async wrapper."""
    _make_email_contact(label="Async", email="async@example.com")

    result = async_to_sync(get_support_contacts_async)()
    assert len(result) == 1
    assert result[0].email == "async@example.com"


def test_get_support_contacts_async_falls_back_on_db_error() -> None:
    """get_support_contacts_async() returns [] when the DB layer raises."""
    with patch.object(SupportContact.objects, "filter", side_effect=RuntimeError("db down")):
        result = async_to_sync(get_support_contacts_async)()
    assert result == []


def test_get_email_contacts_async_returns_email_only() -> None:
    """get_email_contacts_async() filters to EMAIL channel type."""
    _make_email_contact(label="Email1", email="e1@example.com")
    _make_telegram_contact(label="Telegram1", telegram_id=111, ordering=1)

    result = async_to_sync(get_email_contacts_async)()
    assert len(result) == 1
    assert result[0].channel_type == SupportChannelType.EMAIL.value


# ---------------------------------------------------------------------------
# get_email_contacts
# ---------------------------------------------------------------------------


def test_get_email_contacts_returns_only_email_channels() -> None:
    """get_email_contacts() returns only EMAIL-type contacts from the cached list."""
    _make_email_contact(label="Email1", email="e1@example.com")
    _make_telegram_contact(label="Telegram1", telegram_id=111)
    _make_email_contact(label="Email2", email="e2@example.com", ordering=1)

    result = get_email_contacts()
    assert len(result) == 2
    assert all(c.channel_type == SupportChannelType.EMAIL.value for c in result)
