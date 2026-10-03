"""
Tests for the server-side consent audit log (T-07 / D8, GDPR Article 7(1)).

Verifies that every consent action (accept / decline / withdraw) creates a
``ConsentRecord`` row with the correct choice, categories, anonymized IP, and
truncated user agent; and that anonymous consent records store a null user
with a session_key.
"""

from __future__ import annotations

import pytest
from django.http import HttpRequest
from django.test import Client

from apps.core.enums import ConsentChoice, ConsentVersion
from apps.users.models import ConsentRecord
from apps.users.services.consent_record import _anonymize_ip, record_consent_action
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

    def test_anonymous_accept_record_has_session_key(self) -> None:
        """An anonymous consent is attributable: null user AND a session_key.

        The ``session_key`` is the sole identifier of an anonymous record (the
        field ``ConsentRecordAdmin.search_fields`` searches), so a row written
        with a NULL key is not evidence. The anonymous consent path creates no
        session otherwise, so this asserts the record is identifiable, not just
        that ``user_id`` is null (06-PII-105).
        """
        client = Client()
        response = client.post("/consent/accept/")

        record = ConsentRecord.objects.get()
        assert record.user_id is None
        assert record.session_key
        assert record.consent_version == ConsentVersion.V1_0.value
        assert response.cookies.get("consent_given") is not None

    def test_two_anonymous_consents_in_different_sessions_are_distinguishable(
        self,
    ) -> None:
        """Two anonymous accepts from different clients yield distinct records.

        Each client has its own session, so the two rows carry different,
        non-null ``session_key`` values — the property that makes the log an
        audit trail rather than an undifferentiated set.
        """
        first = Client()
        first.post("/consent/accept/")
        second = Client()
        second.post("/consent/decline/")

        records = list(ConsentRecord.objects.order_by("id"))
        assert len(records) == 2
        keys = {record.session_key for record in records}
        assert all(key for key in keys)
        assert len(keys) == 2

    def test_session_key_record_is_findable_by_search(self) -> None:
        """An anonymous accept's record is findable by searching on session_key.

        This is the RED-first case for the session guard: before it, the row
        landed with ``user_id=NULL, session_key=NULL`` and no search could
        retrieve it. After it, the key is populated and searchable.
        """
        client = Client()
        client.post("/consent/accept/")

        record = ConsentRecord.objects.get()
        assert record.session_key
        found = ConsentRecord.objects.filter(
            session_key=record.session_key
        ).first()
        assert found is not None
        assert found.pk == record.pk

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


class _Session:
    """Minimal session stub exposing only what ``record_consent_action`` reads."""

    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    def __getattr__(self, name: str) -> str | None:
        return self._values.get(name)


class TestConsentRecordDegradedRemoteAddr:
    """The HTTP context must survive absent or malformed peer metadata.

    ``get_client_ip`` never raises, but its ``"unknown"`` sentinel is not a
    parseable address; ``record_consent_action`` maps it back to ``None`` so a
    missing or malformed ``REMOTE_ADDR`` stores a null IP instead of raising
    ``AddressValueError`` (the 04-AUT-003 regression).
    """

    def test_absent_remote_addr_stores_null_ip(self) -> None:
        """An HttpRequest without REMOTE_ADDR records a null IP, no exception."""
        request = HttpRequest()
        request.session = _Session({"session_key": "degraded-absent"})

        record = record_consent_action(None, ConsentChoice.ACCEPTED, {}, request=request)

        assert record.ip_address is None

    def test_malformed_remote_addr_stores_null_ip(self) -> None:
        """An unparseable REMOTE_ADDR records a null IP, no exception."""
        request = HttpRequest()
        request.session = _Session({"session_key": "degraded-malformed"})
        request.META["REMOTE_ADDR"] = "not-an-ip"

        record = record_consent_action(None, ConsentChoice.DECLINED, {}, request=request)

        assert record.ip_address is None
