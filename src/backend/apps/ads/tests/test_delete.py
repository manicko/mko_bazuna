"""
Integration tests for the ``ad_delete`` view (US-S6 self-delete flow).

Covers:
- Wrong-owner POST returns 403 Forbidden, ad status unchanged.
- Owner POST transitions ad to DELETED and redirects to dashboard.
- Re-deleting an already-DELETED ad is a safe no-op (redirect, status unchanged).
"""

from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse

from apps.ads.models import Ad
from apps.core.enums import AdStatus
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestAdDelete:
    """US-S6: Seller can delete ONLY own ads; wrong-owner returns 403."""

    def test_delete_wrong_user_returns_403(
        self,
        seller,
        user,
        category,
        city,
    ) -> None:
        """A different authenticated user POSTing to /ads/<id>/delete/ gets 403."""
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        client = Client()
        client.force_login(user)

        response = client.post(reverse("ads:delete", args=[ad.id]))
        assert response.status_code == 403

        ad.refresh_from_db()
        assert ad.status != AdStatus.DELETED

    def test_delete_owner_transitions_to_deleted(
        self,
        seller,
        category,
        city,
    ) -> None:
        """Owner POSTing to /ads/<id>/delete/ transitions ad to DELETED + redirect."""
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        client = Client()
        client.force_login(seller)

        response = client.post(reverse("ads:delete", args=[ad.id]))
        assert response.status_code == 302
        assert "dashboard" in response.url

        ad.refresh_from_db()
        assert ad.status == AdStatus.DELETED
        assert ad.deleted_at is not None

    def test_redelete_deleted_ad_is_noop(
        self,
        seller,
        category,
        city,
    ) -> None:
        """Re-deleting an already-DELETED ad does not change status or raise."""
        ad = create_test_ad(seller, category, city, status=AdStatus.DELETED)
        client = Client()
        client.force_login(seller)

        response = client.post(reverse("ads:delete", args=[ad.id]))
        assert response.status_code == 302
        assert "dashboard" in response.url

        ad.refresh_from_db()
        assert ad.status == AdStatus.DELETED
