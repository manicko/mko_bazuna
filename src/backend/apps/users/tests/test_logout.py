"""
Tests for the web logout view (TST-SCB-001 / spec 12).

Covers the POST-based logout contract (SCB-001):
- ``consent:logout`` reverses to ``/logout/``
- A GET to ``/logout/`` returns 405 (POST-only via ``@require_POST``)
- A POST with a valid CSRF token logs out (session flushed) and redirects home
- A POST without a CSRF token returns 403 (CSRF middleware boundary)
- End-to-end workflow: login -> dashboard reachable -> logout -> anonymous again

Uses the Django test client over the real URL wiring.
"""

import pytest
from django.test import Client
from django.urls import reverse

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


class TestLogoutContract:
    """POST-based logout contract (SCB-001)."""

    def test_logout_url_reverses_to_slash(self) -> None:
        """``consent:logout`` resolves to ``/logout/``."""
        assert reverse("consent:logout") == "/logout/"

    def test_get_logout_returns_405(self, user) -> None:
        """A GET to /logout/ is rejected (POST-only)."""
        client = Client()
        client.force_login(user)
        response = client.get("/logout/")
        assert response.status_code == 405

    def test_post_logout_flushes_session_and_redirects(self, user) -> None:
        """A POST with a valid CSRF token logs out and redirects home."""
        client = Client()
        client.force_login(user)
        assert "_auth_user_id" in client.session

        response = client.post("/logout/")
        assert response.status_code == 302
        assert response.url == "/"  # LOGOUT_REDIRECT_URL
        # Session flushed by django.contrib.auth.logout
        assert "_auth_user_id" not in client.session

    def test_post_logout_without_csrf_returns_403(self, user) -> None:
        """A POST /logout/ without a CSRF token is rejected (403)."""
        client = Client(enforce_csrf_checks=True)
        client.force_login(user)
        response = client.post("/logout/")
        assert response.status_code == 403

    def test_logout_workflow_returns_anonymous(self, user) -> None:
        """Login -> dashboard -> POST logout -> redirected -> anonymous again."""
        client = Client()
        client.force_login(user)

        # dashboard reachable while authenticated
        dashboard = client.get("/dashboard/")
        assert dashboard.status_code == 200

        # logout via POST redirects home
        response = client.post("/logout/")
        assert response.status_code == 302
        assert response.url == "/"

        # subsequent dashboard request redirects to login (anonymous)
        response = client.get("/dashboard/")
        assert response.status_code == 302
        assert response.url.startswith("/login/issue/")
