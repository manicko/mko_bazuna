"""
Tests for the public privacy policy page (D1 / TR-01, GDPR Article 13).

Verifies ``GET /privacy/`` returns 200 without login and includes the cookie
declaration table and third-party disclosures required to obtain informed
consent.
"""

from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse

pytestmark = [pytest.mark.django_db]


class TestPrivacyPage:
    """Privacy policy page accessibility and required disclosures."""

    def test_privacy_page_returns_200(self) -> None:
        """GET /privacy/ returns 200 for an anonymous visitor."""
        response = Client().get(reverse("core:privacy"))
        assert response.status_code == 200

    def test_privacy_page_lists_cookies(self) -> None:
        """The page discloses the cookie declaration table (Section 4.4)."""
        response = Client().get(reverse("core:privacy"))
        content = response.content.decode()
        for cookie in (
            "sessionid",
            "csrftoken",
            "consent_given",
            "lang_pref",
            "preferred_city",
        ):
            assert cookie in content

    def test_privacy_page_discloses_third_parties(self) -> None:
        """The page lists third-party data recipients."""
        response = Client().get(reverse("core:privacy"))
        content = response.content.decode()
        for third_party in ("Telegram", "Google Translate", "Plausible Analytics"):
            assert third_party in content
