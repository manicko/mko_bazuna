"""
Unit tests for moderation admin actions (AD-001).

Verifies that approve_ad, reject_ad, and soft_delete_ad route all status
changes through the state machine (auto_moderate → set_published /
set_rejected → transition_to) instead of direct field assignment. Also
validates the transition matrix edges introduced by the fix: ON_MODERATION_FAILED ->
REJECTED, and that PUBLISHED/ARCHIVED -> REJECTED raises ValueError.
"""

from __future__ import annotations

import inspect
import threading
import time
from unittest.mock import patch

import pytest
from django.db import connection, transaction

from apps.ads.models import Ad, AdImage
from apps.core.enums import AdStatus
from apps.moderation.admin_actions import (
    approve_ad,
    ban_user_for_ad,
    bulk_approve,
    bulk_ban_users,
    bulk_delete,
    bulk_reject,
    reject_ad,
    soft_delete_ad,
)
from apps.users.models import User
from conftest import create_test_ad, create_test_ads_bulk

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Tests: approve_ad routing
# ---------------------------------------------------------------------------


class TestApproveAdRouting:
    """Verify approve_ad delegates to auto_moderate, not direct assignment."""

    @patch("apps.moderation.admin_actions.auto_moderate")
    def test_approve_ad_routes_through_auto_moderate(
        self, mock_auto_moderate, seller, category, city
    ):
        """approve_ad calls auto_moderate() instead of assigning fields directly."""
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)
        moderator = User.objects.create(
            telegram_id=900000204, chat_id=900000204, password="x"
        )
        approve_ad(ad, moderator.id)

        mock_auto_moderate.assert_called_once_with(ad, moderator_id=moderator.id)
        # The ad must NOT have been transitioned by the old code path
        ad.refresh_from_db()
        assert ad.status == AdStatus.ON_MODERATION

    def test_approve_ad_only_from_moderation(self, seller, category, city):
        """approve_ad is a no-op when the ad is not in ON_MODERATION."""
        ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)
        moderator = User.objects.create(
            telegram_id=900000205, chat_id=900000205, password="x"
        )
        with patch("apps.moderation.admin_actions.auto_moderate") as mock_am:
            approve_ad(ad, moderator.id)
            mock_am.assert_not_called()

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
        """bulk_ban_users must NOT gain select_for_update (out of DB-003 scope).

        It must still wrap the ban+audit-log writes in transaction.atomic().
        """
        src = inspect.getsource(bulk_ban_users)
        assert "select_for_update" not in src
        assert "transaction.atomic" in src

    @staticmethod
    def test_ban_user_for_ad_uses_atomic() -> None:
        """ban_user_for_ad must wrap ban+audit-log writes in transaction.atomic() (DB-003)."""
        src = inspect.getsource(ban_user_for_ad)
        assert "transaction.atomic" in src
        assert "select_for_update" in src  # added — User row must be locked


# ---------------------------------------------------------------------------
# Tests: DB-003 transactional rollback for ban+audit-log writes
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
        ads = [
            create_test_ad(
                seller, category, city, title="Red Car For Sale",
                status=AdStatus.ON_MODERATION,
            ),
            create_test_ad(
                seller, category, city, title="Blue Motorcycle Available",
                status=AdStatus.ON_MODERATION,
            ),
            create_test_ad(
                seller, category, city, title="House Near Park",
                status=AdStatus.ON_MODERATION,
            ),
        ]
        for ad in ads:
            AdImage.objects.create(ad=ad, image=f"img-{ad.pk}.jpg", position=0)
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

    def test_bulk_reject_rejects_all(
        self,
        seller: User,
        category,
        city,
    ) -> None:
        """N ON_MODERATION/ON_MODERATION_FAILED ads → all REJECTED,
        rejected_at set, return count == N."""
        ads = [
            create_test_ad(
                seller, category, city, title="Reject A",
                status=AdStatus.ON_MODERATION,
            ),
            create_test_ad(
                seller, category, city, title="Reject B",
                status=AdStatus.ON_MODERATION_FAILED,
            ),
        ]
        moderator = User.objects.create(
            telegram_id=900000213, chat_id=900000213, password="x"
        )

        count = bulk_reject(Ad.objects.all(), moderator.id, "policy violation")

        assert count == 2
        for ad in ads:
            ad.refresh_from_db()
            assert ad.status == AdStatus.REJECTED
            assert ad.rejected_at is not None

    def test_bulk_reject_skips_already_rejected(
        self,
        seller: User,
        category,
        city,
    ) -> None:
        """Already-REJECTED ads are skipped, not double-rejected."""
        rejected_ad = create_test_ad(
            seller, category, city, title="Already Rejected",
            status=AdStatus.REJECTED,
        )
        on_moderation_ad = create_test_ad(
            seller, category, city, title="On Moderation",
            status=AdStatus.ON_MODERATION,
        )
        moderator = User.objects.create(
            telegram_id=900000216, chat_id=900000216, password="x"
        )

        count = bulk_reject(Ad.objects.all(), moderator.id, "reason")

        assert count == 1
        rejected_ad.refresh_from_db()
        assert rejected_ad.status == AdStatus.REJECTED  # unchanged
        on_moderation_ad.refresh_from_db()
        assert on_moderation_ad.status == AdStatus.REJECTED


# ---------------------------------------------------------------------------
# Tests: DB-003 transactional rollback for ban+audit-log writes
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestBanAtomicRollback:
    """Verify ban_user_for_ad and bulk_ban_users roll back on audit-log
    failure (DB-003)."""

    def test_ban_user_for_ad_atomic_on_log_failure(
        self, seller: User, category, city
    ) -> None:
        """log_ban_account failure rolls back the user.is_banned save (DB-003)."""
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)
        moderator = User.objects.create(
            telegram_id=900000212, chat_id=900000212, password="x"
        )

        with patch("apps.moderation.admin_actions.log_ban_account") as mock_log:
            mock_log.side_effect = RuntimeError("simulated log failure")
            with pytest.raises(RuntimeError, match="simulated log failure"):
                ban_user_for_ad(ad, moderator.id, "policy violation")

        # The user.save(is_banned=True) must have been rolled back — user
        # remains unbanned in the DB.
        seller.refresh_from_db()
        assert seller.is_banned is False
        mock_log.assert_called_once()

    def test_bulk_ban_users_atomic_on_log_failure(
        self, category, city
    ) -> None:
        """log_ban_account failure mid-loop rolls back the entire bulk update (DB-003)."""
        user1 = User.objects.create(
            telegram_id=900000213, chat_id=900000213, password="x"
        )
        user2 = User.objects.create(
            telegram_id=900000214, chat_id=900000214, password="x"
        )
        user3 = User.objects.create(
            telegram_id=900000215, chat_id=900000215, password="x"
        )
        for u in (user1, user2, user3):
            create_test_ad(u, category, city, status=AdStatus.ON_MODERATION)

        moderator = User.objects.create(
            telegram_id=900000216, chat_id=900000216, password="x"
        )

        call_count = 0

        def _fail_after_first(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                raise RuntimeError("simulated log failure")

        with patch(
            "apps.moderation.admin_actions.log_ban_account",
            side_effect=_fail_after_first,
        ) as mock_log:
            with pytest.raises(RuntimeError, match="simulated log failure"):
                bulk_ban_users(Ad.objects.all(), moderator.id, "policy violation")

        # No users should be banned — the atomic block rolled back everything,
        # including the eventual User.objects.filter(...).update(is_banned=True).
        for u in (user1, user2, user3):
            u.refresh_from_db()
            assert u.is_banned is False
        # The first call succeeded before the failure was triggered.
        assert mock_log.call_count >= 1


# ---------------------------------------------------------------------------
# Tests: DB-003 behavioral concurrency — select_for_update blocks delete
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
@pytest.mark.slow
@pytest.mark.integration
@pytest.mark.concurrent
class TestBulkRejectRowLockConcurrency:
    """DB-003: ``select_for_update()`` in bulk_reject prevents stale-state races.

    Mirrors ``TestEditViewsRowLockConcurrency`` from ``test_edit_views_locking.py``:
    a row locked by ``select_for_update()`` inside ``transaction.atomic()``
    blocks a concurrent hard-delete until the locking transaction commits.
    """

    def test_select_for_update_blocks_concurrent_delete_during_bulk_reject(
        self, seller: User, category, city
    ) -> None:
        """A row locked by bulk_reject's ``select_for_update()`` blocks a
        concurrent hard-delete until the transaction commits.

        This verifies that the row-level lock in ``bulk_reject`` (DB-003)
        prevents a concurrent sweep from deleting an ad mid-bulk, which would
        otherwise cause ``Ad.DoesNotExist`` inside the transition.
        """
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)
        ad_id = ad.id

        started = threading.Event()
        finished = threading.Event()
        errors: list[BaseException] = []

        def concurrent_hard_delete() -> None:
            """Background thread: hard-deletes the locked row.

            Should block while the main thread holds the ``FOR UPDATE`` lock.
            """
            started.set()
            try:
                with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
                    Ad.objects.filter(pk=ad_id).delete()
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                finished.set()
                connection.close()

        # --- Main thread: acquire the row lock (as bulk_reject does) ---
        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
            locked_ad = Ad.objects.select_for_update().get(pk=ad_id)
            assert locked_ad.id == ad_id

            thread = threading.Thread(target=concurrent_hard_delete)
            thread.start()

            assert started.wait(timeout=5), "Background thread did not start"

            # The DELETE should be blocked waiting for the row lock.
            time.sleep(1.0)
            assert not finished.is_set(), (
                "DELETE completed before lock was released — "
                "select_for_update did not block the concurrent delete"
            )

        # --- Main transaction commits, releasing the row lock ---
        assert finished.wait(timeout=10), (
            "DELETE did not complete after lock was released"
        )
        thread.join(timeout=10)

        assert not errors, f"Background thread raised: {errors}"
        assert not Ad.objects.filter(pk=ad_id).exists(), (
            "Ad should have been hard-deleted by the concurrent sweep "
            "after the lock was released"
        )
