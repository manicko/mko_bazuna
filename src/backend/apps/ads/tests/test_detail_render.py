"""
Integration tests for ad detail page rendering (G3, G4).

Verifies:
- G3: "Back to listings" link uses ``javascript:history.back()``
- G4: Telegram contact deep-link renders the ``{% telegram_deep_link %}`` tag
  with ``contact_<ad.id>`` as the ``data-start`` payload (obfuscated, no
  cleartext ``t.me`` URL in href).
"""

from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse

from apps.core.enums import AdStatus
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestAdDetailRender:
    """Integration tests for the published ad detail page rendering."""

    def test_back_to_listings_link_uses_history_back(
        self,
        seller,
        category,
        city,
    ) -> None:
        """G3: The 'Back to listings' link has href=javascript:history.back()."""
        ad = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get(reverse("ads:detail", args=[ad.id]))

        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert 'href="javascript:history.back()"' in content

    def test_telegram_contact_deep_link_href(
        self,
        seller,
        category,
        city,
    ) -> None:
        """G4: The contact deep-link renders the ``telegram_deep_link`` tag
        with ``contact_<ad.id>`` as the ``data-start`` payload."""
        ad = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        client.cookies["js"] = "true"
        response = client.get(reverse("ads:detail", args=[ad.id]))

        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert 'href="#"' in content
        assert "js-telegram-link" in content
        assert "data-bot-encoded" in content
        assert f'data-start="contact_{ad.id}"' in content
