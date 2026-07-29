"""
Tests for record_contact_response service function.

Tests the happy path (seller found, event created) and edge case
(seller not found, no crash) per the spec in T7.
"""

from __future__ import annotations

import pytest
from apps.analytics.models import AnalyticsEvent
from apps.core.enums import AnalyticsEventType
from apps.core.services.contact import record_contact_response
from apps.users.models import User

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


class TestRecordContactResponse:
    """Tests for record_contact_response."""

    def test_record_contact_response_creates_event(self) -> None:
        """Happy path: seller exists, event is created with correct type and user_id."""
        seller = User.objects.create(
            telegram_id=900100001,
            chat_id=900100001,
            password="x",
        )

        record_contact_response(seller_telegram_id=900100001)

        event = AnalyticsEvent.objects.get(event_type=AnalyticsEventType.CONTACT_RESPONSE)
        assert event.user_id == seller.id

    def test_record_contact_response_no_crash_on_missing_seller(self) -> None:
        """Edge case: seller not found, function logs warning, no exception."""
        # Should not raise
        record_contact_response(seller_telegram_id=999999999)

        # No event should be created
        assert AnalyticsEvent.objects.count() == 0

    def test_record_contact_response_multiple_events(self) -> None:
        """Multiple calls for the same seller create multiple events."""
        seller = User.objects.create(
            telegram_id=900100002,
            chat_id=900100002,
            password="x",
        )

        record_contact_response(seller_telegram_id=900100002)
        record_contact_response(seller_telegram_id=900100002)

        events = AnalyticsEvent.objects.filter(
            event_type=AnalyticsEventType.CONTACT_RESPONSE,
        )
        assert events.count() == 2
        assert all(e.user_id == seller.id for e in events)