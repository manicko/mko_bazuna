"""
Tests for the consent context processor (T-04 / D3, D4, D5; T-08; T-09).

Verifies ``apps.users.context_processors.consent_state`` computes
``consent_shown`` / ``consent_analytics`` / ``consent_preferences`` for both
anonymous (cookie-based) and authenticated (DB-based) users, including the
backward-compatible old cookie format, the 12-month re-prompt, and the
``?ref=preferences`` override.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from apps.users.context_processors import consent_state
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from django.utils import timezone

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _anon_request(**cookies) -> object:
    """Build an anonymous request with the given cookies."""
    request = RequestFactory().get("/")
    request.user = AnonymousUser()
    request.COOKIES = dict(cookies)
    return request


def _auth_request(user, **cookies) -> object:
    """Build an authenticated request for ``user`` with the given cookies."""
    request = RequestFactory().get("/")
    request.user = user
    request.COOKIES = dict(cookies)
    return request


class TestAnonymousCookieState:
    """Anonymous consent state is derived from cookies (D4)."""

    def test_anonymous_without_cookie_shows_banner(self) -> None:
        """Anonymous with no consent cookie => banner shown (consent_shown=False)."""
        ctx = consent_state(_anon_request())
        assert ctx["consent_shown"] is False
        assert ctx["consent_analytics"] is False
        assert ctx["consent_preferences"] is False

    def test_anonymous_accepted_cookie_hides_banner(self) -> None:
        """Anonymous with consent_given=accepted => banner hidden."""
        ctx = consent_state(_anon_request(consent_given="accepted"))
        assert ctx["consent_shown"] is True

    def test_anonymous_accepted_enables_analytics_and_preferences(self) -> None:
        """Anonymous accepted cookie enables both category flags."""
        ctx = consent_state(
            _anon_request(
                consent_given="accepted",
                consent_analytics="true",
                consent_preferences="true",
            )
        )
        assert ctx["consent_analytics"] is True
        assert ctx["consent_preferences"] is True

    def test_backward_compatible_old_true_cookie(self) -> None:
        """The legacy ``consent_given=true`` cookie is treated as full acceptance."""
        ctx = consent_state(_anon_request(consent_given="true"))
        assert ctx["consent_shown"] is True
        assert ctx["consent_analytics"] is True
        assert ctx["consent_preferences"] is True

    def test_anonymous_declined_cookie_keeps_preferences(self) -> None:
        """Anonymous declined => analytics off, preferences available (PO-02)."""
        ctx = consent_state(
            _anon_request(
                consent_given="declined",
                consent_analytics="false",
                consent_preferences="true",
            )
        )
        assert ctx["consent_shown"] is True
        assert ctx["consent_analytics"] is False
        assert ctx["consent_preferences"] is True


class TestAuthenticatedState:
    """Authenticated consent state is derived from the User record (D5)."""

    def test_active_user_without_consent_shows_banner(self, user) -> None:
        """Authenticated user with no consent state => banner shown."""
        ctx = consent_state(_auth_request(user))
        assert ctx["consent_shown"] is False

    def test_accepted_user_hides_banner(self, user) -> None:
        """Authenticated user with consent_given_at => banner hidden."""
        user.consent_given_at = timezone.now()
        user.save(update_fields=["consent_given_at"])
        ctx = consent_state(_auth_request(user))
        assert ctx["consent_shown"] is True
        assert ctx["consent_analytics"] is True
        assert ctx["consent_preferences"] is True

    def test_declined_user_hides_banner(self, user) -> None:
        """Authenticated user who declined is not re-prompted."""
        user.is_declined = True
        user.ads_auto_publish = False
        user.save(update_fields=["is_declined", "ads_auto_publish"])
        ctx = consent_state(_auth_request(user))
        assert ctx["consent_shown"] is True

    def test_deleted_user_hides_banner(self, user) -> None:
        """Soft-deleted users never see the banner (guard also in templates)."""
        user.is_deleted = True
        user.save(update_fields=["is_deleted"])
        ctx = consent_state(_auth_request(user))
        assert ctx["consent_shown"] is True


class TestRePrompt:
    """12-month re-prompt (T-08)."""

    def test_authenticated_consent_older_than_12_months_reprompts(self, user) -> None:
        """Consent older than 365 days => banner reappears."""
        user.consent_given_at = timezone.now() - timedelta(days=400)
        user.save(update_fields=["consent_given_at"])
        ctx = consent_state(_auth_request(user))
        assert ctx["consent_shown"] is False

    def test_authenticated_consent_younger_than_12_months(self, user) -> None:
        """Recent consent keeps the banner hidden."""
        user.consent_given_at = timezone.now() - timedelta(days=100)
        user.save(update_fields=["consent_given_at"])
        ctx = consent_state(_auth_request(user))
        assert ctx["consent_shown"] is True

    def test_anonymous_expired_timestamp_reprompts(self) -> None:
        """Anonymous consent_timestamp older than 12 months => banner reappears."""
        expired = int(timezone.now().timestamp()) - (366 * 24 * 60 * 60)
        request = _anon_request(
            consent_given="accepted", consent_timestamp=str(expired)
        )
        ctx = consent_state(request)
        assert ctx["consent_shown"] is False


class TestPreferenceCenterOverride:
    """``?ref=preferences`` forces the banner (T-09)."""

    def test_ref_preferences_forces_banner(self, user) -> None:
        """Requesting the preference center re-shows the banner."""
        user.consent_given_at = timezone.now()
        user.save(update_fields=["consent_given_at"])
        request = _auth_request(user)
        request.GET = {"ref": "preferences"}
        ctx = consent_state(request)
        assert ctx["consent_shown"] is False
