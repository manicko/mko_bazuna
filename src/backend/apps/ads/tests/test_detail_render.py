"""
Integration tests for ad detail page rendering (G3, G4).

Verifies:
- G3: "Back to listings" link uses ``javascript:history.back()``
- G4: Telegram contact deep-link href is
  ``https://t.me/{bot_username}?start=contact_{ad.id}``
"""

from __future__ import annotations

import pytest
from django.conf import settings
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
        """G4: The contact link deep-links to Telegram with contact_<ad.id>."""
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
        expected_href = f"https://t.me/{settings.BOT_USERNAME}?start=contact_{ad.id}"
        assert f'href="{expected_href}"' in content
