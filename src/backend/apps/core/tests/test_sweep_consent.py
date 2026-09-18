"""
Split from test_sweep_commands.py: Tests for the consent_hard_delete command.

Consent hard-delete annihilates user accounts whose consent was revoked more
than 30 days ago, nulling their foreign keys in analytics and moderation logs,
guarded by an advisory lock (lock id 3).
"""

from __future__ import annotations

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
from apps.moderation.models import ModeratorActionLog
from apps.users.models import User
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


class TestConsentHardDelete:
    """Tests for consent_hard_delete command (advisory lock 3, 30-day window)."""

    def test_dry_run_does_not_delete(self, seller):

        seller.consent_revoked_at = timezone.now() - timedelta(days=60)
        seller.save()
        call_command("consent_hard_delete", "--dry-run")
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
            "apps.core.management.commands.consent_hard_delete.delete_photo",
            _record,
        )

        call_command("consent_hard_delete")

        expected = img.storage_keys()
        assert sorted(deleted_keys) == sorted(expected)
        assert not User.objects.filter(pk=seller.pk).exists()

    def test_lock_id_is_consent_hard_delete(self):
        assert AdvisoryLockId.CONSENT_HARD_DELETE == 3

    def test_crash_between_updates_and_delete_rolls_back(self, seller, monkeypatch):
        """Crash during mutation rolls back atomically - user and history preserved."""
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

        # Patch User.objects.filter to return a mock that crashes on delete
        # but allows count() and values_list()
        class _CrashOnDeleteQuerySet:
            def __init__(self, target_pk):
                self._target_pk = target_pk

            def count(self):
                return 1

            def values_list(self, *args, **kwargs):
                return [self._target_pk]

            def delete(self):
                raise RuntimeError("Simulated crash during delete")

            def exists(self):
                return True

        original_filter = User.objects.filter
        monkeypatch.setattr(
            User.objects,
            "filter",
            lambda *args, **kwargs: _CrashOnDeleteQuerySet(seller.pk),
        )

        with pytest.raises(RuntimeError, match="Simulated crash during delete"):
            call_command("consent_hard_delete")

        # Restore original filter so post-crash assertions use real DB
        monkeypatch.setattr(User.objects, "filter", original_filter)

        # Verify atomicity: user still exists, history not nulled
        assert User.objects.filter(pk=seller.pk).exists()
        event.refresh_from_db()
        assert event.user_id == seller.pk
        log.refresh_from_db()
        assert log.user_id == seller.pk
