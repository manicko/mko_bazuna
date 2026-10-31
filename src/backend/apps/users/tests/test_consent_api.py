"""Tests for the ``/api/v1/consent/…`` and ``/api/v1/auth/logout/`` writes (S3.3).

Browserless (``Client()``) coverage of the consent + logout writes:

- **401 matrix** — withdraw and logout refuse an anonymous caller with the 401
  ``unauthenticated`` problem (no ``WWW-Authenticate``); accept/decline are
  anonymous-allowed (HTML parity).
- **405 matrix** — an authenticated non-POST request answers a 405
  ``method_not_allowed`` problem with ``Allow: POST``.
- **Service parity** — the API operation mutates the account exactly as the HTML
  flow does (same end state fields), including the anonymous audit row.
- **Soft-deleted refusal** — accept/decline by a withdrawn identity → 403.
- **Withdraw parity** — the session is flushed (a subsequent request is 401),
  matching the HTML withdraw flow's ``logout()``.
- **Logout** — a session POST answers 204 with an empty body and flushes the
  session.
- **429** — an exhausted ``API_WRITE`` namespace answers the RFC 9457
  ``rate_limited`` problem + ``Retry-After``.

Cookies are deliberately **not** asserted: the consent cookie quartet stays on
the HTML surface (plan row 20), and the API sets none.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.test import Client

from apps.core.enums import ConsentChoice
from apps.core.utils.problem import (
    PROBLEM_CONTENT_TYPE,
    RETRY_AFTER_HEADER,
    TYPE_RATE_LIMITED,
)
from apps.users.models import ConsentRecord, User

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

ACCEPT = "/api/v1/consent/accept/"
DECLINE = "/api/v1/consent/decline/"
WITHDRAW = "/api/v1/consent/withdraw/"
LOGOUT = "/api/v1/auth/logout/"

# The HTML mirrors of the same flows (for end-state equivalence asserts).
HTML_ACCEPT = "/consent/accept/"
HTML_DECLINE = "/consent/decline/"
HTML_WITHDRAW = "/consent/withdraw/"


def _post(url: str, client: Client | None = None, **kwargs: Any) -> Any:
    """POST an empty JSON body to *url* unless one is supplied."""
    kwargs.setdefault("data", b"")
    kwargs.setdefault("content_type", "application/json")
    return (client or Client()).post(url, **kwargs)


@pytest.fixture
def deleted_user() -> User:
    """Create a soft-deleted (withdrawn) user for the refusal matrix."""
    from django.utils import timezone

    return User.objects.create(
        telegram_id=900000091,
        chat_id=900000091,
        password="y",
        is_deleted=True,
        consent_revoked_at=timezone.now(),
    )


class TestAuthMatrix:
    """Accept/decline anonymous-allowed; withdraw/logout session-only."""

    def test_accept_anonymous_is_allowed(self) -> None:
        response = _post(ACCEPT)

        assert response.status_code == 200
        assert response.json()["choice"] == ConsentChoice.ACCEPTED.value
        assert response.json()["authenticated"] is False

    def test_decline_anonymous_is_allowed(self) -> None:
        response = _post(DECLINE)

        assert response.status_code == 200
        assert response.json()["choice"] == ConsentChoice.DECLINED.value
        assert response.json()["authenticated"] is False

    def test_withdraw_anonymous_returns_401_problem(self) -> None:
        response = _post(WITHDRAW)

        assert response.status_code == 401
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        payload = response.json()
        assert payload["type"] == "unauthenticated"
        assert payload["status"] == 401
        assert "WWW-Authenticate" not in response.headers

    def test_logout_anonymous_returns_401_problem(self) -> None:
        response = _post(LOGOUT)

        assert response.status_code == 401
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        assert response.json()["type"] == "unauthenticated"
        assert "WWW-Authenticate" not in response.headers


class TestMethodNotAllowed:
    """Authenticated non-POST → 405 problem with ``Allow: POST``."""

    @pytest.mark.parametrize("url", [ACCEPT, DECLINE, WITHDRAW, LOGOUT])
    def test_get_returns_405_problem(self, user, url: str) -> None:
        client = Client()
        client.force_login(user)
        response = client.get(url)

        # Accept/decline are anonymous-allowed, so the GET reaches the method
        # gate; withdraw/logout are identity-gated first (still 405 for a
        # logged-in caller).
        assert response.status_code == 405
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        assert response.headers.get("Allow") == "POST"
        assert response.json()["type"] == "method_not_allowed"


class TestAccept:
    """Accept parity: anonymous audit row; session account mutation."""

    def test_anonymous_records_audit_row(self) -> None:
        response = _post(ACCEPT)

        assert response.status_code == 200
        record = ConsentRecord.objects.get(choice=ConsentChoice.ACCEPTED)
        assert record.user_id is None

    def test_session_sets_consent_given_at(self, user: User) -> None:
        user.is_declined = True
        user.ads_auto_publish = False
        user.save(update_fields=["is_declined", "ads_auto_publish"])

        client = Client()
        client.force_login(user)
        response = _post(ACCEPT, client=client)

        assert response.status_code == 200
        payload = response.json()
        assert payload["choice"] == ConsentChoice.ACCEPTED.value
        assert payload["is_declined"] is False
        assert payload["ads_auto_publish"] is True
        assert payload["consent_given_at"] is not None

        user.refresh_from_db()
        assert user.consent_given_at is not None
        assert user.is_declined is False
        assert user.ads_auto_publish is True

    def test_soft_deleted_returns_403(self, deleted_user: User) -> None:
        client = Client()
        client.force_login(deleted_user)
        response = _post(ACCEPT, client=client)

        assert response.status_code == 403
        assert response.json()["type"] == "forbidden"
        deleted_user.refresh_from_db()
        assert deleted_user.is_deleted is True
        assert deleted_user.consent_revoked_at is not None
        assert not ConsentRecord.objects.filter(choice=ConsentChoice.ACCEPTED).exists()

    def test_state_equals_html_flow(self, user: User) -> None:
        """API accept end state == HTML accept end state (field-level)."""
        api_user = user
        html_user = User.objects.create(
            telegram_id=900000092, chat_id=900000092, password="y"
        )

        api_client = Client()
        api_client.force_login(api_user)
        _post(ACCEPT, client=api_client)

        html_client = Client()
        html_client.force_login(html_user)
        html_client.post(HTML_ACCEPT)

        api_user.refresh_from_db()
        html_user.refresh_from_db()
        assert (api_user.consent_given_at is not None) == (
            html_user.consent_given_at is not None
        )
        assert api_user.is_declined == html_user.is_declined
        assert api_user.ads_auto_publish == html_user.ads_auto_publish


class TestDecline:
    """Decline parity: browse-only state, no deletion."""

    def test_anonymous_records_audit_row(self) -> None:
        response = _post(DECLINE)

        assert response.status_code == 200
        record = ConsentRecord.objects.get(choice=ConsentChoice.DECLINED)
        assert record.user_id is None

    def test_session_sets_browse_only(self, user: User) -> None:
        client = Client()
        client.force_login(user)
        response = _post(DECLINE, client=client)

        assert response.status_code == 200
        payload = response.json()
        assert payload["choice"] == ConsentChoice.DECLINED.value
        assert payload["is_declined"] is True
        assert payload["ads_auto_publish"] is False
        assert payload["is_deleted"] is False

        user.refresh_from_db()
        assert user.is_declined is True
        assert user.ads_auto_publish is False
        assert user.telegram_id is not None  # PII preserved (no deletion)

    def test_soft_deleted_returns_403(self, deleted_user: User) -> None:
        client = Client()
        client.force_login(deleted_user)
        response = _post(DECLINE, client=client)

        assert response.status_code == 403
        assert response.json()["type"] == "forbidden"
        assert not ConsentRecord.objects.filter(choice=ConsentChoice.DECLINED).exists()

    def test_state_equals_html_flow(self, user: User) -> None:
        api_user = user
        html_user = User.objects.create(
            telegram_id=900000093, chat_id=900000093, password="y"
        )

        api_client = Client()
        api_client.force_login(api_user)
        _post(DECLINE, client=api_client)

        html_client = Client()
        html_client.force_login(html_user)
        html_client.post(HTML_DECLINE)

        api_user.refresh_from_db()
        html_user.refresh_from_db()
        assert api_user.is_declined == html_user.is_declined is True
        assert api_user.ads_auto_publish == html_user.ads_auto_publish is False
        assert api_user.is_deleted == html_user.is_deleted is False


class TestWithdraw:
    """Withdraw parity: soft-delete side effects + session flush."""

    def test_session_withdraw_flushes_session(self, user: User) -> None:
        client = Client()
        client.force_login(user)
        assert "_auth_user_id" in client.session

        response = _post(WITHDRAW, client=client)

        assert response.status_code == 200
        payload = response.json()
        assert payload["choice"] == ConsentChoice.WITHDRAWN.value
        assert payload["is_deleted"] is True
        assert payload["consent_revoked_at"] is not None
        assert payload["session_flushed"] is True

        # Session actually flushed: the client is anonymous again.
        assert "_auth_user_id" not in client.session
        assert _post(WITHDRAW, client=client).status_code == 401

    def test_session_withdraw_soft_deletes_account(self, user: User) -> None:
        client = Client()
        client.force_login(user)
        response = _post(WITHDRAW, client=client)

        assert response.status_code == 200
        user.refresh_from_db()
        assert user.is_deleted is True
        assert user.consent_revoked_at is not None
        assert user.telegram_id is None  # PII nulled

    def test_soft_deleted_accept_after_withdraw_is_403(self, user: User) -> None:
        """Withdraw then a fresh session accept → 403 (WITHDRAW is terminal)."""
        client = Client()
        client.force_login(user)
        _post(WITHDRAW, client=client)

        again = Client()
        again.force_login(user)
        response = _post(ACCEPT, client=again)

        assert response.status_code == 403


class TestLogout:
    """Logout flushes the session and answers 204 empty."""

    def test_session_logout_returns_204_and_flushes(self, user: User) -> None:
        client = Client()
        client.force_login(user)
        assert "_auth_user_id" in client.session

        response = _post(LOGOUT, client=client)

        assert response.status_code == 204
        assert response.content == b""
        assert "_auth_user_id" not in client.session
        # Subsequent logout is anonymous → 401.
        assert _post(LOGOUT, client=client).status_code == 401


class TestRateLimitProblem:
    """Exhausting ``API_WRITE`` yields the RFC 9457 429 problem."""

    @pytest.mark.parametrize(
        "module,url",
        [
            ("apps.users.views.api.consent", ACCEPT),
            ("apps.users.views.api.consent", DECLINE),
            ("apps.users.views.api.consent", WITHDRAW),
            ("apps.users.views.api.logout", LOGOUT),
        ],
    )
    def test_over_budget_returns_rate_limited_problem(
        self, user, monkeypatch, module: str, url: str
    ) -> None:
        monkeypatch.setattr(f"{module}.rate_limit_check", lambda *a, **k: False)
        client = Client()
        client.force_login(user)
        response = _post(url, client=client)

        assert response.status_code == 429
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        assert response.headers.get(RETRY_AFTER_HEADER) == "60"
        payload = response.json()
        assert payload["type"] == TYPE_RATE_LIMITED
        assert payload["status"] == 429
