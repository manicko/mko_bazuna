"""
Split from test_sweep_commands.py: Tests for the consent_hard_delete command.

Consent hard-delete annihilates user accounts whose consent was revoked more
than 30 days ago, nulling their foreign keys in analytics and moderation logs,
guarded by an advisory lock (lock id 3).
"""

from __future__ import annotations

import logging
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.ads.models import AdImage
from apps.analytics.models import AnalyticsEvent
from apps.core.enums import (
    AdStatus,
    AdvisoryLockId,
    AnalyticsEventType,
    ModeratorActionType,
)
from apps.core.models import SupportTicket
from apps.moderation.models import ModeratorActionLog
from apps.users.models import User
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestConsentHardDelete:
    """Tests for consent_hard_delete command (advisory lock 3, 30-day window)."""

    def test_dry_run_does_not_delete(self, seller, caplog: pytest.LogCaptureFixture) -> None:
        seller.consent_revoked_at = timezone.now() - timedelta(days=60)
        seller.save()
        with caplog.at_level(
            logging.INFO,
            logger="apps.core.management.commands.consent_hard_delete",
        ):
            call_command("consent_hard_delete", "--dry-run")
        assert "DRY RUN: Would hard-delete 1 users with consent revoked over 30 days ago" in caplog.text
        assert User.objects.filter(pk=seller.pk).exists()

    def test_hard_deletes_users_past_grace_period(self, seller):

        seller.consent_revoked_at = timezone.now() - timedelta(days=60)
        seller.save()
        fresh = User.objects.create(
            telegram_id=900000003, chat_id=900000003, password="x"
        )
        call_command("consent_hard_delete")
        assert not User.objects.filter(pk=seller.pk).exists()
        assert User.objects.filter(pk=fresh.pk).exists()

    def test_nulls_analytics_event_user(self, seller):

        seller.consent_revoked_at = timezone.now() - timedelta(days=60)
        seller.save()
        event = AnalyticsEvent.objects.create(
            event_type=AnalyticsEventType.SEARCH_PERFORMED, user=seller
        )
        call_command("consent_hard_delete")
        event.refresh_from_db()
        assert event.user_id is None

    def test_nulls_moderator_action_log_user(self, seller):

        seller.consent_revoked_at = timezone.now() - timedelta(days=60)
        seller.save()
        log = ModeratorActionLog.objects.create(
            user=seller,
            action_type=ModeratorActionType.BAN_ACCOUNT,
            reason="internal",
        )
        call_command("consent_hard_delete")
        log.refresh_from_db()
        assert log.user_id is None

    def test_does_not_delete_within_grace_period(self, seller):

        seller.consent_revoked_at = timezone.now() - timedelta(days=10)
        seller.save()
        call_command("consent_hard_delete")
        assert User.objects.filter(pk=seller.pk).exists()

    @pytest.mark.django_db(transaction=True)
    def test_collects_thumbnail_keys_for_media_cleanup(
        self, seller, category, city, monkeypatch
    ):
        """Hard-delete sweep passes all storage keys (image + thumbnails) to delete_photo.

        Verifies PC-004: the sweep uses AdImage.storage_keys() so thumbnail
        derivatives are not orphaned on disk alongside the main image.
        """
        seller.consent_revoked_at = timezone.now() - timedelta(days=60)
        seller.save()
        ad = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.PUBLISHED,
        )
        img = AdImage.objects.create(
            ad=ad,
            image="test-uuid-hardcmd.jpg",
            thumbnail_small="test-uuid-hardcmd-small.jpg",
            thumbnail_medium="test-uuid-hardcmd-medium.jpg",
            thumbnail_large="test-uuid-hardcmd-large.jpg",
        )

        deleted_keys: list[str] = []

        def _record(storage_key: str) -> None:
            deleted_keys.append(storage_key)

        monkeypatch.setattr(
            "apps.media.signals.delete_photo",
            _record,
        )

        call_command("consent_hard_delete")

        expected = img.storage_keys()
        assert sorted(deleted_keys) == sorted(expected)
        assert not User.objects.filter(pk=seller.pk).exists()

    def test_lock_id_is_consent_hard_delete(self):
        assert AdvisoryLockId.CONSENT_HARD_DELETE == 3

    @pytest.mark.django_db(transaction=True)
    def test_crash_between_updates_and_delete_rolls_back(self, seller) -> None:
        """Crash during user deletion rolls back atomically - user and history preserved.

        Uses a real ``pre_delete`` signal handler on ``User`` (instead of a
        monkey-patched fake queryset) so the production ``queryset.delete()``
        code path runs in full -- the Collector, the ``pre_delete`` dispatch, and
        the savepoint rollback -- exercising the exact guarantee being tested:
        a crash between the null-UPDATE phase and the user DELETE rolls back
        everything inside ``handle()``'s ``transaction.atomic()``.
        """
        from django.db.models.signals import pre_delete

        seller.consent_revoked_at = timezone.now() - timedelta(days=60)
        seller.save()
        event = AnalyticsEvent.objects.create(
            event_type=AnalyticsEventType.SEARCH_PERFORMED, user=seller
        )
        log = ModeratorActionLog.objects.create(
            user=seller,
            action_type=ModeratorActionType.BAN_ACCOUNT,
            reason="internal",
        )
        ticket = SupportTicket.objects.create(
            user=seller,
            chat_id=seller.chat_id,
            telegram_id=seller.telegram_id,
            text="rollback ticket",
        )

        def _raise_on_user_delete(sender, instance, **kwargs):
            if instance.pk == seller.pk:
                raise RuntimeError("Simulated crash during user delete")

        pre_delete.connect(_raise_on_user_delete, sender=User)
        try:
            with pytest.raises(RuntimeError, match="Simulated crash during user delete"):
                call_command("consent_hard_delete")

            # Verify atomicity: all mutations inside handle()'s atomic() rolled back
            assert User.objects.filter(pk=seller.pk).exists()
            event.refresh_from_db()
            assert event.user_id == seller.pk
            log.refresh_from_db()
            assert log.user_id == seller.pk
            assert SupportTicket.objects.filter(pk=ticket.pk).exists()
        finally:
            pre_delete.disconnect(_raise_on_user_delete, sender=User)

    def test_hard_delete_cascades_support_tickets_and_spares_others(self, seller):
        """A hard-deleted user's ticket goes with them; another user's survives."""
        seller.consent_revoked_at = timezone.now() - timedelta(days=60)
        seller.save()
        other = User.objects.create(
            telegram_id=900000777, chat_id=900000777, password="x"
        )
        mine = SupportTicket.objects.create(
            user=seller,
            chat_id=seller.chat_id,
            telegram_id=seller.telegram_id,
            text="mine",
        )
        theirs = SupportTicket.objects.create(
            user=other,
            chat_id=other.chat_id,
            telegram_id=other.telegram_id,
            text="theirs",
        )

        call_command("consent_hard_delete")

        assert not User.objects.filter(pk=seller.pk).exists()
        assert not SupportTicket.objects.filter(pk=mine.pk).exists()
        assert SupportTicket.objects.filter(pk=theirs.pk).exists()

    @pytest.mark.django_db(transaction=True)
    def test_log_reports_user_count_not_cascade_total(
        self, seller, category, city, monkeypatch, caplog
    ):
        """Log says 'Hard-deleted 1 users' not the cascaded total.

        Verifies B5: consent_hard_delete logs len(user_ids) as the user count
        (not the queryset.delete() cascade total), with the cascaded total
        reported separately. Creates multiple ads+AdImages per user so the
        cascaded total is provably larger than the user count.
        """
        seller.consent_revoked_at = timezone.now() - timedelta(days=60)
        seller.save()

        # Create 3 ads, each with an AdImage -- cascade will delete
        # 1 user + 3 ads + 3 AdImages = 7 rows (cascaded > user count)
        for i in range(3):
            ad = create_test_ad(
                seller,
                category,
                city,
                title=f"Ad {i}",
                status=AdStatus.PUBLISHED,
            )
            AdImage.objects.create(
                ad=ad,
                image=f"test-uuid-b6-{i}.jpg",
                thumbnail_small=f"test-uuid-b6-{i}-small.jpg",
                thumbnail_medium=f"test-uuid-b6-{i}-medium.jpg",
                thumbnail_large=f"test-uuid-b6-{i}-large.jpg",
            )

        # Patch delete_photo to avoid real filesystem writes
        deleted_keys: list[str] = []

        def _record(key: str) -> None:
            deleted_keys.append(key)

        monkeypatch.setattr(
            "apps.media.signals.delete_photo",
            _record,
        )

        with caplog.at_level("INFO"):
            call_command("consent_hard_delete")

        # The log must say "Hard-deleted 1 users" (len(user_ids)),
        # NOT "Hard-deleted 7 users" (the cascaded total)
        assert "Hard-deleted 1 users" in caplog.text
        # The cascaded total is logged separately
        assert "cascaded" in caplog.text
        assert "rows incl. ads/images" in caplog.text
        # User no longer exists
        assert not User.objects.filter(pk=seller.pk).exists()
