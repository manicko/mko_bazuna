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
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramServerError
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


def _backfill_migration_module():
    """Import the shipped ``0004`` backfill migration module.

    The module name starts with a digit, so a static ``import`` is impossible;
    ``importlib`` loads the real artefact the deploy runs rather than an inline
    replay that would stay green if the migration were rewritten.
    """
    import importlib

    return importlib.import_module(
        "apps.search.migrations.0004_backfill_delivered_at"
    )


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


class TestImmediateRetryMarksDelivered:
    """A transient failure followed by a successful retry writes the receipt.

    Mirrors the daily ``send_alerts`` path, which marks after retry success. The
    immediate path must do the same, or the pair stays ``delivered_at IS NULL``
    and the next daily digest re-sends an already-delivered alert (03-DB-007).
    """

    @pytest.mark.django_db(transaction=True)
    def test_retry_success_records_receipt_and_excludes_from_digest(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        import asyncio

        # ``transaction=True`` commits the row so the ``sync_to_async`` delivery
        # thread (a different DB connection) can see it: under the default
        # per-test transaction the mark's UPDATE would match zero rows and the
        # receipt would silently be lost.
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        saved_search = SavedSearch.objects.create(user=buyer, is_active=True)
        row = SavedSearchNotification.objects.create(saved_search=saved_search, ad=ad)
        assert row.delivered_at is None

        transient = TelegramServerError(
            message="internal server error", method=MagicMock()
        )
        payload = {
            "chat_id": 12345,
            "text": "test message",
            "reply_markup": None,
            "pair": (saved_search.id, ad.id),
        }

        with patch("apps.search.services.immediate_alerts.Bot") as mock_bot_cls:
            mock_bot = mock_bot_cls.return_value
            mock_bot.send_message = AsyncMock(side_effect=[transient, None])
            mock_bot.session.close = AsyncMock()

            from apps.search.services.immediate_alerts import _send_payloads

            with patch(
                "apps.search.services.immediate_alerts.asyncio.sleep",
                new=AsyncMock(),
            ):
                asyncio.run(_send_payloads("test-token", [payload]))

            # The primary send failed and the retry succeeded — two attempts.
            assert mock_bot.send_message.await_count == 2

        row.refresh_from_db()
        assert row.delivered_at is not None
        # The daily matcher now excludes the pair (no duplicate re-send).
        assert find_matching_ads(saved_search) == []


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
        The real migration's forward function is imported and executed, so the
        shipped artefact — not an inline replay — is what is pinned.
        """
        from django.apps import apps as django_apps

        migration = _backfill_migration_module()

        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        saved_search = SavedSearch.objects.create(user=buyer, is_active=True)
        row = SavedSearchNotification.objects.create(saved_search=saved_search, ad=ad)

        migration.backfill_delivered_at(django_apps, None)

        row.refresh_from_db()
        assert row.delivered_at == row.sent_at
        # And the row stays excluded, exactly as before the deploy.
        assert find_matching_ads(saved_search) == []

    def test_backfill_reverse_is_noop(self) -> None:
        """The shipped migration's reverse is ``RunPython.noop``.

        A reverse that NULLed ``delivered_at`` would re-arm the mass
        re-notification the backfill exists to prevent.
        """
        from django.db import migrations

        operation = _backfill_migration_module().Migration.operations[0]
        assert isinstance(operation, migrations.RunPython)
        assert operation.reverse_code is migrations.RunPython.noop

