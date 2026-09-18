"""
Side-effect tests for moderation logging and admin functions.

Verifies that the moderation functions create the expected audit rows:
  - set_published()      -> ModeratorActionLog (action_type=OTHER)
  - set_rejected()       -> ModeratorActionLog (action_type=REJECT)
  - set_moderation_failed() -> ModeratorActionLog (action_type=OTHER)
  - reject_ad()          -> ModeratorActionLog (action_type=REJECT) + REJECTED status
  - approve_ad()         -> AdModerationPriority record present

Tests call the real (unmocked) functions to exercise the full
atomic status-transition + audit-log write chain (DB-002).
"""

from __future__ import annotations

import pytest

from apps.core.enums import AdStatus, ModeratorActionType
from apps.moderation.admin_actions import approve_ad, reject_ad
from apps.moderation.models import (
    AdModerationPriority,
    ModerationCriteria,
    ModeratorActionLog,
)
from apps.moderation.services.moderation_log import (
    set_moderation_failed,
    set_published,
    set_rejected,
)
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


@pytest.fixture
def moderation_criteria():
    """Ensure ModerationCriteria singleton exists with a safe max_ads_per_user."""
    criteria = ModerationCriteria.get_singleton()
    criteria.max_ads_per_user = 10
    criteria.save()
    return criteria


# ---------------------------------------------------------------------------
# Tests: ModeratorActionLog creation by moderation_log functions
# ---------------------------------------------------------------------------


class TestModerationLogSideEffects:
    """Verify ModeratorActionLog rows are created by moderation_log functions."""

    def test_set_published_logs(
        self, moderation_criteria, seller, category, city
    ) -> None:
        """set_published with a moderator_id creates a ModeratorActionLog
        with action_type=OTHER.
        """
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        set_published(ad, moderator_id=seller.id)

        log = ModeratorActionLog.objects.filter(ad_id=ad.id).first()
        assert log is not None
        assert log.action_type == ModeratorActionType.OTHER
        assert log.reason == "Manually published by moderator"

    def test_set_rejected_logs(
        self, moderation_criteria, seller, category, city
    ) -> None:
        """set_rejected creates a ModeratorActionLog with action_type=REJECT."""
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        set_rejected(ad, moderator_id=seller.id, reason="policy violation")

        log = ModeratorActionLog.objects.filter(ad_id=ad.id).first()
        assert log is not None
        assert log.action_type == ModeratorActionType.REJECT
        assert log.reason == "policy violation"

    def test_set_moderation_failed_logs(
        self, moderation_criteria, seller, category, city
    ) -> None:
        """set_moderation_failed creates a ModeratorActionLog with action_type=OTHER."""
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        set_moderation_failed(ad)

        log = ModeratorActionLog.objects.filter(ad_id=ad.id).first()
        assert log is not None
        assert log.action_type == ModeratorActionType.OTHER
        assert log.reason == "Auto-moderation failed"


# ---------------------------------------------------------------------------
# Tests: reject_ad unmocked side effects
# ---------------------------------------------------------------------------


class TestRejectAdSideEffects:
    """Verify reject_ad creates a ModeratorActionLog and transitions to REJECTED."""

    def test_reject_ad_creates(
        self, moderation_criteria, seller, category, city
    ) -> None:
        """reject_ad (unmocked) creates a ModeratorActionLog with REJECT and
        transitions the ad to REJECTED.

        Unlike test_reject_ad_routes_through_set_rejected (which mocks
        set_rejected), this test exercises the full atomic chain: status
        transition + audit-log write.
        """
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        reject_ad(ad, moderator_id=seller.id, reason="policy violation")

        ad.refresh_from_db()
        assert ad.status == AdStatus.REJECTED
        assert ad.rejected_at is not None

        log = ModeratorActionLog.objects.filter(ad_id=ad.id).first()
        assert log is not None
        assert log.action_type == ModeratorActionType.REJECT
        assert log.reason == "policy violation"


# ---------------------------------------------------------------------------
# Tests: approve_ad priority side effect
# ---------------------------------------------------------------------------


class TestApproveAdPriority:
    """Verify approve_ad preserves/creates AdModerationPriority for the ad."""

    def test_approve_ad_creates_priority(
        self, moderation_criteria, seller, category, city
    ) -> None:
        """approve_ad on an ON_MODERATION ad results in an AdModerationPriority
        row existing for that ad.

        The priority is created by the calculate_ad_priority post_save signal
        when the ad entered ON_MODERATION (via create_test_ad).  This test
        verifies the record survives the approve_ad -> PUBLISHED transition.
        """
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        approve_ad(ad, moderator_id=seller.id)

        ad.refresh_from_db()
        assert ad.status == AdStatus.PUBLISHED

        priority = AdModerationPriority.objects.filter(ad=ad).first()
        assert priority is not None
        assert priority.ad_id == ad.id
