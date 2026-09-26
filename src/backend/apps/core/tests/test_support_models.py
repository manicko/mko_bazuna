"""
Tests for SupportContact and SupportTicket models (Block B2).

Covers:
- SupportContact creation with valid email/telegram_id per channel_type
- CheckConstraint rejects: EMAIL without email, TELEGRAM without telegram_id,
  EMAIL with telegram_id set, TELEGRAM with email set
- SupportTicket ticket_ref generation (SUP-YYYYMM-NNN format)
- SupportTicket default status is OPEN
- SupportTicket creation without user (anonymous)
"""

from __future__ import annotations

import re

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.enums import SupportChannelType, SupportTicketStatus
from apps.core.models import SupportContact, SupportTicket
from apps.users.models import User

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_TICKET_REF_RE = re.compile(r"^SUP-(?P<year>\d{4})(?P<month>\d{2})-(?P<seq>\d{3})$")


# ---------------------------------------------------------------------------
# SupportContact — valid creation
# ---------------------------------------------------------------------------


class TestSupportContactValid:
    """Valid SupportContact rows per channel_type."""

    def test_email_channel_with_email(self) -> None:
        """EMAIL channel with email set and telegram_id null is valid."""
        contact = SupportContact.objects.create(
            channel_type=SupportChannelType.EMAIL,
            label="Email support",
            email="support@example.com",
        )
        assert contact.email == "support@example.com"
        assert contact.telegram_id is None

    def test_telegram_channel_with_telegram_id(self) -> None:
        """TELEGRAM channel with telegram_id set and email null is valid."""
        contact = SupportContact.objects.create(
            channel_type=SupportChannelType.TELEGRAM,
            label="Telegram support",
            telegram_id=123456789,
        )
        assert contact.telegram_id == 123456789
        assert contact.email is None

    def test_defaults(self) -> None:
        """is_active defaults to True, ordering defaults to 0."""
        contact = SupportContact.objects.create(
            channel_type=SupportChannelType.EMAIL,
            label="Defaults",
            email="defaults@example.com",
        )
        assert contact.is_active is True
        assert contact.ordering == 0


# ---------------------------------------------------------------------------
# SupportContact — CheckConstraint rejection
# ---------------------------------------------------------------------------


class TestSupportContactConstraints:
    """CheckConstraint ``support_contact_channel_value_required`` rejects invalid combos."""

    @pytest.mark.parametrize(
        ("channel_type", "email", "telegram_id"),
        [
            (SupportChannelType.EMAIL, None, None),
            (SupportChannelType.EMAIL, "a@b.com", 123456),
            (SupportChannelType.TELEGRAM, None, None),
            (SupportChannelType.TELEGRAM, "a@b.com", 123456),
        ],
        ids=[
            "email_no_email",
            "email_with_telegram",
            "telegram_no_id",
            "telegram_with_email",
        ],
    )
    def test_constraint_rejects(
        self,
        channel_type,
        email,
        telegram_id,
    ) -> None:
        """Invalid channel/value combinations raise IntegrityError."""
        with pytest.raises(IntegrityError):
            with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
                SupportContact.objects.create(
                    channel_type=channel_type,
                    label="Invalid",
                    email=email,
                    telegram_id=telegram_id,
                )


# ---------------------------------------------------------------------------
# SupportTicket — ticket_ref generation
# ---------------------------------------------------------------------------


class TestSupportTicketRef:
    """Tests for the ``ticket_ref`` auto-generation (``SUP-YYYYMM-NNN``)."""

    def test_ticket_ref_format(self) -> None:
        """ticket_ref matches SUP-YYYYMM-NNN with current month and sequence 001."""
        ticket = SupportTicket.objects.create(
            chat_id=900000001,
            telegram_id=900000001,
            text="Help me",
        )
        now = timezone.now()
        expected_prefix = f"SUP-{now.strftime('%Y%m')}-"
        assert ticket.ticket_ref.startswith(expected_prefix)
        match = _TICKET_REF_RE.match(ticket.ticket_ref)
        assert match is not None
        assert match.group("year") == now.strftime("%Y")
        assert match.group("month") == now.strftime("%m")
        assert match.group("seq") == "001"

    def test_ticket_ref_sequence_increments(self) -> None:
        """Second ticket in the same month gets sequence 002."""
        SupportTicket.objects.create(
            chat_id=900000001,
            telegram_id=900000001,
            text="First",
        )
        second = SupportTicket.objects.create(
            chat_id=900000002,
            telegram_id=900000002,
            text="Second",
        )
        now = timezone.now()
        assert second.ticket_ref == f"SUP-{now.strftime('%Y%m')}-002"


# ---------------------------------------------------------------------------
# SupportTicket — default status
# ---------------------------------------------------------------------------


class TestSupportTicketDefaults:
    """Tests for SupportTicket default field values."""

    def test_default_status_is_open(self) -> None:
        """A new ticket without explicit status defaults to OPEN."""
        ticket = SupportTicket.objects.create(
            chat_id=900000001,
            telegram_id=900000001,
            text="Help",
        )
        assert ticket.status == SupportTicketStatus.OPEN.value

    def test_default_status_field_value(self) -> None:
        """The status field's default is SupportTicketStatus.OPEN."""
        assert (
            SupportTicket._meta.get_field("status").default
            == SupportTicketStatus.OPEN
        )


# ---------------------------------------------------------------------------
# SupportTicket — anonymous (no user)
# ---------------------------------------------------------------------------


class TestSupportTicketAnonymous:
    """Tests for SupportTicket creation without an authenticated user."""

    def test_create_without_user(self) -> None:
        """A ticket with user=None (anonymous) is created successfully."""
        ticket = SupportTicket.objects.create(
            user=None,
            chat_id=900000001,
            telegram_id=900000001,
            text="Anonymous help request",
        )
        assert ticket.user is None
        assert ticket.ticket_ref.startswith("SUP-")

    def test_create_with_user(self, user: User) -> None:
        """A ticket with an authenticated user is created with the user set."""
        ticket = SupportTicket.objects.create(
            user=user,
            chat_id=900000002,
            telegram_id=900000002,
            text="Authenticated help request",
        )
        assert ticket.user == user
