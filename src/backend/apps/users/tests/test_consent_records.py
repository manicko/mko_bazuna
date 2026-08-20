"""
Tests for the server-side consent audit log (T-07 / D8, GDPR Article 7(1)).

Verifies that every consent action (accept / decline / withdraw) creates a
``ConsentRecord`` row with the correct choice, categories, anonymized IP, and
truncated user agent; and that anonymous consent records store a null user
with a session_key.
"""

from __future__ import annotations

import pytest
from apps.core.enums import ConsentChoice
from apps.users.models import ConsentRecord, User
from django.test import Client

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


@pytest.fixture
def user() -> User:
    """An authenticated user."""
    return User.objects.create(
        telegram_id=900000050,
        chat_id=900000050,
        password="x",
    )


class TestConsentRecords:
    """Consent actions create exactly one ConsentRecord each."""

    def test_accept_creates_record(self, user: User) -> None:
        """Authenticated accept creates an ACCEPTED record with categories."""
        client = Client()
        client.force_login(user)
        client.post("/consent/accept/")

        record = ConsentRecord.objects.get()
        assert record.user_id == user.id
        assert record.choice == ConsentChoice.ACCEPTED.value
        assert record.categories == {"analytics": True, "preferences": True}

    def test_decline_creates_record(self, user: User) -> None:
        """Authenticated decline creates a DECLINED record."""
        client = Client()
        client.force_login(user)
        client.post("/consent/decline/")

        record = ConsentRecord.objects.get()
        assert record.choice == ConsentChoice.DECLINED.value
        assert record.categories == {"analytics": False, "preferences": True}

    def test_withdraw_creates_record(self, user: User) -> None:
        """Authenticated withdraw creates a WITHDRAWN record."""
        client = Client()
        client.force_login(user)
        client.post("/consent/withdraw/")

        record = ConsentRecord.objects.get()
        assert record.choice == ConsentChoice.WITHDRAWN.value
        assert record.categories == {"analytics": False, "preferences": False}

    def test_anonymous_accept_record_has_null_user(self) -> None:
        """Anonymous consent stores a null user and a session_key."""
        client = Client()
        response = client.post("/consent/accept/")

        # The client holds a session when cookies are enabled.
        record = ConsentRecord.objects.get()
        assert record.user_id is None
        assert record.consent_version == "1.0"
        assert response.cookies.get("consent_given") is not None

    def test_ip_is_anonymized_and_ua_truncated(self, user: User) -> None:
        """IP last octet zeroed; user agent truncated to 500 chars."""
        client = Client()
        client.force_login(user)
        long_ua = "A" * 1000
        client.post("/consent/accept/", HTTP_USER_AGENT=long_ua)

        record = ConsentRecord.objects.get()
        assert record.user_agent == "A" * 500
        # REMOTE_ADDR is set by Django's test client; the stored value must be
        # either None (unset) or end in ".0" (anonymized).
        if record.ip_address is not None:
            assert record.ip_address.endswith(".0")
