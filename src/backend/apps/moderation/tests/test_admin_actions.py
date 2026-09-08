"""
Unit tests for moderation admin actions (AD-001).

Verifies that approve_ad, reject_ad, and soft_delete_ad route all status
changes through the state machine (transition_to / set_published /
set_rejected) instead of direct field assignment. Also validates the
transition matrix edges introduced by the fix: ON_MODERATION_FAILED ->
REJECTED, and that PUBLISHED/ARCHIVED -> REJECTED raises ValueError.
"""

from __future__ import annotations

import inspect
from unittest.mock import patch

import pytest
from apps.ads.models import Ad
from apps.core.enums import AdStatus
from apps.moderation.admin_actions import (
    approve_ad,
    bulk_approve,
    bulk_ban_users,
    bulk_delete,
    bulk_reject,
    reject_ad,
    soft_delete_ad,
)
from apps.users.models import User
from conftest import create_test_ad, create_test_ads_bulk

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Tests: approve_ad routing
# ---------------------------------------------------------------------------


class TestApproveAdRouting:
    """Verify approve_ad delegates to set_published, not direct assignment."""

    @patch("apps.moderation.admin_actions.set_published")
    def test_approve_ad_routes_through_set_published(
        self, mock_set_published, seller, category, city
    ):
        """approve_ad calls set_published() instead of assigning fields directly."""
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)
        moderator = User.objects.create(
            telegram_id=900000204, chat_id=900000204, password="x"
        )
        approve_ad(ad, moderator.id)

        mock_set_published.assert_called_once_with(ad, moderator_id=moderator.id)
        # The ad must NOT have been transitioned by the old code path
        ad.refresh_from_db()
        assert ad.status == AdStatus.ON_MODERATION

    def test_approve_ad_only_from_moderation(self, seller, category, city):
        """approve_ad is a no-op when the ad is not in ON_MODERATION."""
        ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)
        moderator = User.objects.create(
            telegram_id=900000205, chat_id=900000205, password="x"
        )
        with patch("apps.moderation.admin_actions.set_published") as mock_set:
            approve_ad(ad, moderator.id)
            mock_set.assert_not_called()

        ad.refresh_from_db()
        assert ad.status == AdStatus.DRAFT


# ---------------------------------------------------------------------------
# Tests: reject_ad routing and matrix
# ---------------------------------------------------------------------------


class TestRejectAdRouting:
    """Verify reject_ad delegates to set_rejected and respects the matrix."""

    @patch("apps.moderation.admin_actions.set_rejected")
    def test_reject_ad_routes_through_set_rejected(
        self, mock_set_rejected, seller, category, city
    ):
        """reject_ad calls set_rejected() instead of assigning fields directly."""
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)
        moderator_id = seller.id + 100

        reject_ad(ad, moderator_id, "spam content")

        mock_set_rejected.assert_called_once_with(
            ad, moderator_id=moderator_id, reason="spam content"
        )
        ad.refresh_from_db()
        assert ad.status == AdStatus.ON_MODERATION

    def test_reject_ad_from_moderation_succeeds(self, seller, category, city):
        """reject_ad transitions ON_MODERATION -> REJECTED."""
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)
        moderator = User.objects.create(
            telegram_id=900000200, chat_id=900000200, password="x"
        )
        reject_ad(ad, moderator.id, "policy violation")

        ad.refresh_from_db()
        assert ad.status == AdStatus.REJECTED
        assert ad.rejected_at is not None
        assert ad.moderated_by_id == moderator.id

    def test_reject_ad_from_moderation_failed_succeeds(self, seller, category, city):
        """reject_ad transitions ON_MODERATION_FAILED -> REJECTED (new matrix edge)."""
        ad = create_test_ad(
            seller, category, city, status=AdStatus.ON_MODERATION_FAILED
        )
        moderator = User.objects.create(
            telegram_id=900000201, chat_id=900000201, password="x"
        )
        reject_ad(ad, moderator.id, "manual review")

        ad.refresh_from_db()
        assert ad.status == AdStatus.REJECTED
        assert ad.rejected_at is not None
        assert ad.moderated_by_id == moderator.id
        # ON_MODERATION_FAILED timestamp must be cleared (mutually exclusive)
        assert ad.moderation_failed_at is None

    def test_reject_ad_from_published_raises(self, seller, category, city):
        """reject_ad on PUBLISHED raises ValueError (forbidden transition)."""
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        moderator = User.objects.create(
            telegram_id=900000202, chat_id=900000202, password="x"
        )
        with pytest.raises(ValueError, match="Invalid transition"):
            reject_ad(ad, moderator.id, "not allowed")

        ad.refresh_from_db()
        assert ad.status == AdStatus.PUBLISHED

    def test_reject_ad_from_archived_raises(self, seller, category, city):
        """reject_ad on ARCHIVED raises ValueError (forbidden transition)."""
        ad = create_test_ad(seller, category, city, status=AdStatus.ARCHIVED)
        moderator = User.objects.create(
            telegram_id=900000203, chat_id=900000203, password="x"
        )
        with pytest.raises(ValueError, match="Invalid transition"):
            reject_ad(ad, moderator.id, "not allowed")

        ad.refresh_from_db()
        assert ad.status == AdStatus.ARCHIVED

    def test_reject_ad_already_rejected_noop(self, seller, category, city):
        """reject_ad on REJECTED is a no-op."""
        ad = create_test_ad(seller, category, city, status=AdStatus.REJECTED)
        original_rejected_at = ad.rejected_at

        with patch("apps.moderation.admin_actions.set_rejected") as mock_set:
            reject_ad(ad, seller.id, "not allowed")
            mock_set.assert_not_called()

        ad.refresh_from_db()
        assert ad.status == AdStatus.REJECTED
        assert ad.rejected_at == original_rejected_at


# ---------------------------------------------------------------------------
# Tests: soft_delete_ad routing
# ---------------------------------------------------------------------------


class TestSoftDeleteAdRouting:
    """Verify soft_delete_ad routes through transition_to(DELETED)."""

    def test_soft_delete_ad_routes_through_transition_to(self, seller, category, city):
        """soft_delete_ad calls ad.transition_to(DELETED), not direct assignment."""
        ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)
        moderator = User.objects.create(
            telegram_id=900000206, chat_id=900000206, password="x"
        )

        with patch.object(Ad, "transition_to", wraps=ad.transition_to) as spy:
            soft_delete_ad(ad, moderator.id, "spam")
            spy.assert_called_once()
            # Verify the target status argument
            args, kwargs = spy.call_args
            assert args[0] == AdStatus.DELETED

        ad.refresh_from_db()
        assert ad.status == AdStatus.DELETED
        assert ad.deleted_at is not None

    @pytest.mark.parametrize("start_status", [AdStatus.DRAFT, AdStatus.ON_MODERATION])
    def test_soft_delete_any_active_state(self, seller, category, city, start_status):
        """soft_delete_ad transitions DRAFT/ON_MODERATION/PUBLISHED -> DELETED."""
        ad = create_test_ad(seller, category, city, status=start_status)
        moderator = User.objects.create(
            telegram_id=900000207, chat_id=900000207, password="x"
        )

        soft_delete_ad(ad, moderator.id, "policy violation")

        ad.refresh_from_db()
        assert ad.status == AdStatus.DELETED
        assert ad.deleted_at is not None


# ---------------------------------------------------------------------------
# Tests: DB-003 structural guards for bulk locking
# ---------------------------------------------------------------------------


class TestBulkLockingStructure:
    """Structural guards: bulk_approve/reject/delete must lock Ad rows."""

    @staticmethod
    def test_bulk_approve_uses_select_for_update_orderby_atomic() -> None:
        """bulk_approve wraps its fetch-and-transition loop with row locking."""
        src = inspect.getsource(bulk_approve)
        assert "select_for_update" in src
        assert "order_by" in src
        assert "pk" in src
        assert "transaction.atomic" in src

    @staticmethod
    def test_bulk_reject_uses_select_for_update_orderby_atomic() -> None:
        """bulk_reject wraps its fetch-and-transition loop with row locking."""
        src = inspect.getsource(bulk_reject)
        assert "select_for_update" in src
        assert "order_by" in src
        assert "pk" in src
        assert "transaction.atomic" in src

    @staticmethod
    def test_bulk_delete_uses_select_for_update_orderby_atomic() -> None:
        """bulk_delete wraps its fetch-and-transition loop with row locking."""
        src = inspect.getsource(bulk_delete)
        assert "select_for_update" in src
        assert "order_by" in src
        assert "pk" in src
        assert "transaction.atomic" in src

    @staticmethod
    def test_bulk_ban_users_not_locked() -> None:
        """bulk_ban_users must NOT gain select_for_update (out of DB-003 scope)."""
        src = inspect.getsource(bulk_ban_users)
        assert "select_for_update" not in src


# ---------------------------------------------------------------------------
# Tests: DB-003 functional bulk operations
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestBulkOperations:
    """Functional tests for the DB-003 locking bulk helpers."""

    def test_bulk_approve_publishes_all(
        self,
        seller: User,
        category,
        city,
    ) -> None:
        """3 ON_MODERATION ads for one user → all PUBLISHED, return count == 3."""
        ads = create_test_ads_bulk(
            seller,
            category,
            city,
            3,
            status=AdStatus.ON_MODERATION,
        )
        moderator = User.objects.create(
            telegram_id=900000210, chat_id=900000210, password="x"
        )

        count = bulk_approve(Ad.objects.all(), moderator.id)

        assert count == 3
        for ad in ads:
            ad.refresh_from_db()
            assert ad.status == AdStatus.PUBLISHED

    def test_bulk_delete_skips_hard_deleted_row(
        self,
        seller: User,
        category,
        city,
    ) -> None:
        """bulk_delete skips an ad whose row vanished mid-bulk (Ad.DoesNotExist).

        Patches ``Ad.transition_to`` to raise ``Ad.DoesNotExist`` for one ad,
        simulating a concurrent hard-delete sweep that won the race before the
        ``select_for_update()`` lock was acquired.  The bulk must log + skip the
        vanished row and continue processing the rest.
        """
        ads = create_test_ads_bulk(
            seller,
            category,
            city,
            2,
            status=AdStatus.ON_MODERATION,
        )
        moderator = User.objects.create(
            telegram_id=900000211, chat_id=900000211, password="x"
        )

        # The second ad (higher PK, processed second) simulates a hard-delete
        # race: transition_to raises Ad.DoesNotExist for it.
        vanished_pk = ads[1].pk
        original_transition_to = Ad.transition_to

        def patched_transition_to(
            self_ad: Ad,
            target: AdStatus,
            moderator_id: int | None = None,
        ) -> None:
            if self_ad.pk == vanished_pk:
                raise Ad.DoesNotExist("Ad matching query does not exist.")
            return original_transition_to(self_ad, target, moderator_id=moderator_id)

        with patch.object(Ad, "transition_to", patched_transition_to):
            count = bulk_delete(Ad.objects.all(), moderator.id, "hard-delete race")

        assert count == 1
        # First ad: successfully soft-deleted
        ads[0].refresh_from_db()
        assert ads[0].status == AdStatus.DELETED
        assert ads[0].deleted_at is not None
        # Second ad: skipped (DoesNotExist caught per-ad), unchanged
        ads[1].refresh_from_db()
        assert ads[1].status == AdStatus.ON_MODERATION
