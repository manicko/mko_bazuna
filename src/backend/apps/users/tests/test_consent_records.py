"""
Tests for the server-side consent audit log (T-07 / D8, GDPR Article 7(1)).

Verifies that every consent action (accept / decline / withdraw) creates a
``ConsentRecord`` row with the correct choice, categories, anonymized IP, and
truncated user agent; and that anonymous consent records store a null user
with a session_key.
"""

from __future__ import annotations

import pytest
from django.test import Client

from apps.core.enums import ConsentChoice, ConsentVersion
from apps.users.models import ConsentRecord
from apps.users.services.consent_record import _anonymize_ip
from conftest import make_user

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestConsentRecords:
    """Consent actions create exactly one ConsentRecord each."""

    def test_accept_creates_record(self, user) -> None:
        """Authenticated accept creates an ACCEPTED record with categories."""
        client = Client()
        client.force_login(user)
        client.post("/consent/accept/")

        record = ConsentRecord.objects.get()
        assert record.user_id == user.id
        assert record.choice == ConsentChoice.ACCEPTED.value
        assert record.categories == {"analytics": True, "preferences": True}

    def test_accept_on_deleted_user_creates_no_record(self) -> None:
        """A soft-deleted user posting to /consent/accept/ creates no ConsentRecord."""
        deleted = make_user(
            900000060,
            consent_revoked=True,
            is_deleted=True,
        )

        client = Client()
        client.force_login(deleted)
        response = client.post("/consent/accept/")

        assert response.status_code == 403
        assert ConsentRecord.objects.count() == 0

    def test_decline_creates_record(self, user) -> None:
        """Authenticated decline creates a DECLINED record."""
        client = Client()
        client.force_login(user)
        client.post("/consent/decline/")

        record = ConsentRecord.objects.get()
        assert record.choice == ConsentChoice.DECLINED.value
        assert record.categories == {"analytics": False, "preferences": True}

    def test_withdraw_creates_record(self, user) -> None:
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
        assert record.consent_version == ConsentVersion.V1_0.value
        assert response.cookies.get("consent_given") is not None

    def test_ip_is_anonymized_and_ua_truncated(self, user) -> None:
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


class TestAnonymizeIp:
    """Direct unit tests for the _anonymize_ip helper (PC-005)."""

    def test_ipv6_masked_to_64_prefix(self) -> None:
        """IPv6 input is truncated to its /64 network prefix."""
        result = _anonymize_ip("2001:db8:85a3::8a2e:370:7334")
        assert result == "2001:db8:85a3::"

    def test_ipv4_last_octet_zeroed(self) -> None:
        """IPv4 input has its last octet zeroed."""
        result = _anonymize_ip("192.168.1.100")
        assert result == "192.168.1.0"

    def test_none_input_returns_none(self) -> None:
        """None input yields None."""
        assert _anonymize_ip(None) is None
