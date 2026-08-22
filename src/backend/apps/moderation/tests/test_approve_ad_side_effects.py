"""
Side-effect tests for the ``approve_ad`` → PUBLISHED signal chain.

Verifies that ``approve_ad`` correctly:
  (a) transitions an ``ON_MODERATION`` ad to ``PUBLISHED`` (via ``set_published``),
  (b) triggers ``deliver_immediate_alerts_on_publish`` when
      ``IMMEDIATE_ALERTS_ENABLED`` is True (via ``transaction.on_commit``),
  (c) does NOT schedule alerts when ``IMMEDIATE_ALERTS_ENABLED`` is False
      (default-safe rollout),
  (d) creates an ``AdModerationPriority`` row when an ad enters ``ON_MODERATION``
      (via the ``calculate_ad_priority`` post_save signal).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.db import transaction
from django.test import override_settings

from apps.core.enums import AdStatus
from apps.moderation.models import AdModerationPriority
from apps.moderation.admin_actions import approve_ad

from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]

# Sentinel used to verify the on_commit callback actually ran.
_ALERT_SEND_CALLED = "deliver_immediate_alerts_send"


class TestApproveAdSideEffects:
    """Tests for the approve_ad → PUBLISHED → alert signal chain."""

    def test_approve_ad_transitions_on_moderation_to_published(
        self, seller, category, city
    ) -> None:
        """``approve_ad`` on an ON_MODERATION ad sets status to PUBLISHED."""
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        approve_ad(ad, moderator_id=seller.id)

        ad.refresh_from_db()
        assert ad.status == AdStatus.PUBLISHED
        assert ad.published_at is not None
        assert ad.original_published_at is not None

    def test_approve_ad_no_alerts_when_immediate_alerts_disabled(
        self, seller, category, city
    ) -> None:
        """When ``IMMEDIATE_ALERTS_ENABLED=False`` (default), no alert is scheduled."""
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        with (
            patch("apps.search.services.immediate_alerts.deliver_immediate_alerts") as mock_deliver,
            patch.object(transaction, "on_commit", side_effect=lambda fn: fn()),
        ):
            approve_ad(ad, moderator_id=seller.id)

        mock_deliver.assert_not_called()

    def test_approve_ad_sends_immediate_alerts_when_enabled(
        self, seller, category, city
    ) -> None:
        """When ``IMMEDIATE_ALERTS_ENABLED=True``, ``deliver_immediate_alerts`` runs after commit."""
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        # Mock on_commit to execute the callback immediately (simulates transaction commit).
        with (
            override_settings(IMMEDIATE_ALERTS_ENABLED=True),
            patch("apps.search.services.immediate_alerts.deliver_immediate_alerts") as mock_deliver,
            patch.object(transaction, "on_commit", side_effect=lambda fn: fn()),
        ):
            approve_ad(ad, moderator_id=seller.id)

        ad.refresh_from_db()
        assert ad.status == AdStatus.PUBLISHED
        mock_deliver.assert_called_once_with(ad.id)

    def test_on_moderation_ad_creates_priority_record(
        self, seller, category, city
    ) -> None:
        """Saving an ON_MODERATION ad triggers the ``calculate_ad_priority`` signal."""
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        priority = AdModerationPriority.objects.filter(ad=ad).first()
        assert priority is not None
        assert priority.ad_id == ad.id

    def test_published_ad_does_not_trigger_priority_signal(
        self, seller, category, city
    ) -> None:
        """``calculate_ad_priority`` only fires for ON_MODERATION, not PUBLISHED."""
        create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)

        # The signal handler checks status != ON_MODERATION and returns early.
        assert AdModerationPriority.objects.count() == 0

    def test_approve_ad_idempotent_on_already_published(
        self, seller, category, city
    ) -> None:
        """Calling ``approve_ad`` on a PUBLISHED ad is a no-op (no error)."""
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)

        with patch("apps.search.services.immediate_alerts.deliver_immediate_alerts") as mock_deliver:
            approve_ad(ad, moderator_id=seller.id)

        ad.refresh_from_db()
        assert ad.status == AdStatus.PUBLISHED
        mock_deliver.assert_not_called()
