"""
Tests for the saved-search alert delivery-state contract (03-DB-007).

Covers:
  * ``notification_delivery.mark_delivered``: a single conditional statement
    that records the delivery receipt for one ``(saved_search_id, ad_id)`` pair,
    idempotently.
  * The behaviour-preserving backfill: a row that existed before the backfill
    migration has ``delivered_at == sent_at`` and therefore stays excluded from
    ``find_matching_ads`` (this is what stops a mass re-notification on deploy).
"""

from __future__ import annotations

import logging

import pytest
from django.db.models import F
from django.utils import timezone

from apps.categories.models import Category
from apps.core.enums import AdStatus
from apps.locations.models import City
from apps.search.models import SavedSearch, SavedSearchNotification
from apps.search.services.alert_query import find_matching_ads
from apps.search.services.notification_delivery import mark_delivered
from apps.users.models import User
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestMarkDelivered:
    """``mark_delivered`` records the delivery receipt for one pair."""

    def test_mark_delivered_returns_true_and_sets_timestamp(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        saved_search = SavedSearch.objects.create(user=buyer, is_active=True)
        row = SavedSearchNotification.objects.create(
            saved_search=saved_search, ad=ad
        )
        sent_at = timezone.now()

        assert mark_delivered(saved_search.id, ad.id, sent_at=sent_at) is True

        row.refresh_from_db()
        assert row.delivered_at is not None
        assert row.sent_at is not None

    def test_mark_delivered_is_idempotent_and_conditional(
        self,
        seller: User,
        buyer: User,
        category: Category,
        city: City,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A second call is a no-op returning False and warns with the pair.

        Assertions are on the returned bool and the row's timestamp, not on the
        log text.
        """
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        saved_search = SavedSearch.objects.create(user=buyer, is_active=True)
        row = SavedSearchNotification.objects.create(saved_search=saved_search, ad=ad)

        first = timezone.now()
        with caplog.at_level(logging.WARNING):
            assert mark_delivered(saved_search.id, ad.id, sent_at=first) is True
            row.refresh_from_db()
            assert row.delivered_at is not None
            marked_at = row.delivered_at

            # The losing call must not overwrite the receipt.
            second = first + timezone.timedelta(seconds=5)
            assert mark_delivered(saved_search.id, ad.id, sent_at=second) is False

        row.refresh_from_db()
        assert row.delivered_at == marked_at


class TestBackfillBehaviourPreservation:
    """The backfill keeps pre-existing rows suppressed (03-DB-007 / F-1)."""

    def test_backfill_marks_preexisting_rows_delivered(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        """A pre-existing row has ``delivered_at == sent_at`` after the backfill.

        This is the test that stops a mass re-notification from reaching
        production: with a no-backfill column the filter change would make every
        previously notified pair eligible again and the live, ungated 08:00 UTC
        daily digest would re-notify every subscribed buyer the next day.
        """
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        saved_search = SavedSearch.objects.create(user=buyer, is_active=True)
        row = SavedSearchNotification.objects.create(saved_search=saved_search, ad=ad)

        # Replay the migration's set-based forward operation.
        SavedSearchNotification.objects.filter(delivered_at__isnull=True).update(
            delivered_at=F("sent_at")
        )

        row.refresh_from_db()
        assert row.delivered_at == row.sent_at
        # And the row stays excluded, exactly as before the deploy.
        assert find_matching_ads(saved_search) == []
