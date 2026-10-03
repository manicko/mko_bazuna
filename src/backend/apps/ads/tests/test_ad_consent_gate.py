"""Deviation record for option (b) of finding 06-PII-109.

The determination is that ad text is **not** scrubbed on consent withdrawal:
the 30-day ``consent_hard_delete`` sweep is the erasure, and it hard-deletes the
whole ad row (via ``Ad.user`` ``on_delete=CASCADE``) at its named bound. What
withdrawal does today — and must keep doing — is:

* soft-delete the ad immediately (``status=DELETED``) so it leaves every public
  surface at once;
* remove it from the shared ``ListingsQuery.build_queryset`` result set;
* 404 it from ``ad_detail``; and
* leave the user-authored ``title`` and ``description`` byte-for-byte intact
  during the grace window (they are retained, not anonymised), so moderation
  records stay reviewable for dispute resolution.

This module is the named deviation record: it pins the retained-text behaviour
that the rejected option (a) would have changed, so a future "scrub" cannot land
silently. It deliberately does **not** assert on any ``search_vector`` column.
"""

from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse

from apps.ads.services.listings_query import ListingsQuery, ListingsQueryParams
from apps.core.enums import AdStatus
from apps.users.services.deletion import withdraw_consent
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

# Byte-for-byte content that must survive the grace window untouched.
_TITLE = "Naslov sa imenom Marko Marković"
_DESCRIPTION = "Prodajem bicikl. Pozovite Marka na +382 67 123 456."


class TestWithdrawalRetainsAdTextWithoutAnonymising:
    """Option (b): withdrawal hides the ad but does not anonymise its text."""

    def test_ad_is_soft_deleted_with_text_intact(self, user, category, city) -> None:
        """After withdrawal: status DELETED, title/description unchanged."""
        ad = create_test_ad(
            user,
            category,
            city,
            title=_TITLE,
            description=_DESCRIPTION,
            status=AdStatus.PUBLISHED,
        )

        withdraw_consent(user)

        ad.refresh_from_db()
        assert ad.status == AdStatus.DELETED
        assert ad.title == _TITLE
        assert ad.description == _DESCRIPTION

    def test_deleted_ad_is_absent_from_listings_queryset(
        self, user, category, city
    ) -> None:
        """A withdrawn seller's ad is not returned by ``build_queryset``."""
        ad = create_test_ad(
            user,
            category,
            city,
            title=_TITLE,
            description=_DESCRIPTION,
            status=AdStatus.PUBLISHED,
        )

        params = ListingsQueryParams()
        assert ListingsQuery.build_queryset(params).filter(pk=ad.pk).exists()

        withdraw_consent(user)

        assert not ListingsQuery.build_queryset(params).filter(pk=ad.pk).exists()

    def test_deleted_ad_404s_from_detail(self, user, category, city) -> None:
        """A withdrawn seller's ad 404s from ``ad_detail``."""
        ad = create_test_ad(
            user,
            category,
            city,
            title=_TITLE,
            description=_DESCRIPTION,
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        assert client.get(reverse("ads:detail", args=[ad.id])).status_code == 200

        withdraw_consent(user)

        assert client.get(reverse("ads:detail", args=[ad.id])).status_code == 404
