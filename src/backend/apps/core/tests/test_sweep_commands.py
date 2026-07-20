"""
Integration tests for scheduler sweep and purge management commands.

Covers TASK_049 (lifecycle sweeps: archive_sweep, delete_sweep,
consent_hard_delete, sweep_drafts, cleanup_login_tokens), TASK_037
(purge_failed_ads) and TASK_038 (purge_rejected_ads).

These are DB-backed tests using real PostgreSQL per project spec.
Each command is exercised in both --dry-run (no mutation) and real
execution (mutating) modes, and assertions verify idempotency and
correct retention-window filtering.
"""

import pytest
from datetime import timedelta
from django.core.management import call_command
from django.utils import timezone

from apps.ads.models import Ad, AdImage
from apps.analytics.models import AnalyticsEvent
from apps.core.enums import AdStatus, AdvisoryLockId
from apps.moderation.models import ModeratorActionLog
from apps.users.models import LoginToken, User

pytestmark = pytest.mark.django_db


@pytest.fixture
def seller() -> User:
    """Create a seller user for ad fixtures."""
    return User.objects.create(
        telegram_id=900000001,
        password="x",
    )


@pytest.fixture
def category():
    """Create a leaf category for ad fixtures."""
    from apps.categories.models import Category

    return Category.objects.create(
        name="Test Category",
        slug="test-category",
    )


@pytest.fixture
def city():
    """Create a city for ad fixtures."""
    from apps.locations.models import City

    return City.objects.create(
        country_code="BA",
        name="Test City",
        region="Test Region",
        slug="test-city",
    )


def _make_ad(seller, category, city, **kwargs) -> Ad:
    """Create an Ad with required FK fields, overriding any kwargs.

    Timestamp fields (created_at, published_at, moderation_failed_at,
    rejected_at) use auto_now_add/auto_now in the model, so they cannot be
    set at creation time. Any such field passed in kwargs is applied via a
    post-create UPDATE, which bypasses the model's automatic timestamping and
    lets tests control retention-window boundaries precisely.
    """
    timestamp_fields = {"created_at", "published_at", "moderation_failed_at", "rejected_at"}
    timestamps = {k: v for k, v in kwargs.items() if k in timestamp_fields}
    data = {k: v for k, v in kwargs.items() if k not in timestamp_fields}
    defaults = {
        "user": seller,
        "title": "Valid Title",
        "description": "Valid description text",
        "category": category,
        "city": city,
        "category_name": category.name,
        "status": AdStatus.PUBLISHED,
    }
    defaults.update(data)
    ad = Ad.objects.create(**defaults)
    if timestamps:
        Ad.objects.filter(pk=ad.pk).update(**timestamps)
    return ad


class TestArchiveSweep:
    """Tests for archive_sweep command (advisory lock 1, 60-day window)."""

    def test_dry_run_does_not_mutate(self, seller, category, city):

        stale = _make_ad(
            seller,
            category,
            city,
            status=AdStatus.PUBLISHED,
            published_at=timezone.now() - timedelta(days=90),
        )
        call_command("archive_sweep", "--dry-run")
        stale.refresh_from_db()
        assert stale.status == AdStatus.PUBLISHED

    def test_archives_published_older_than_60_days(self, seller, category, city):

        stale = _make_ad(
            seller,
            category,
            city,
            status=AdStatus.PUBLISHED,
            published_at=timezone.now() - timedelta(days=90),
        )
        fresh = _make_ad(
            seller,
            category,
            city,
            status=AdStatus.PUBLISHED,
            published_at=timezone.now() - timedelta(days=10),
        )
        call_command("archive_sweep")
        stale.refresh_from_db()
        fresh.refresh_from_db()
        assert stale.status == AdStatus.ARCHIVED
        assert stale.archived_at is not None
        assert fresh.status == AdStatus.PUBLISHED

    def test_idempotent_on_rerun(self, seller, category, city):

        stale = _make_ad(
            seller,
            category,
            city,
            status=AdStatus.PUBLISHED,
            published_at=timezone.now() - timedelta(days=90),
        )
        call_command("archive_sweep")
        stale.refresh_from_db()
        assert stale.status == AdStatus.ARCHIVED
        # Re-running should not error and count should be zero.
        call_command("archive_sweep")
        assert Ad.objects.filter(status=AdStatus.ARCHIVED).count() == 1

    def test_lock_id_is_archive_sweep(self):
        assert AdvisoryLockId.ARCHIVE_SWEEP == 1


class TestDeleteSweep:
    """Tests for delete_sweep command (advisory lock 2, 120-day window)."""

    def test_dry_run_does_not_delete(self, seller, category, city):

        old = _make_ad(
            seller,
            category,
            city,
            status=AdStatus.ARCHIVED,
            published_at=timezone.now() - timedelta(days=200),
        )
        AdImage.objects.create(ad=old, image=AdImage.generate_storage_key())
        call_command("delete_sweep", "--dry-run")
        assert Ad.objects.filter(pk=old.pk).exists()

    def test_deletes_archived_older_than_120_days(self, seller, category, city):

        old = _make_ad(
            seller,
            category,
            city,
            status=AdStatus.ARCHIVED,
            published_at=timezone.now() - timedelta(days=200),
        )
        AdImage.objects.create(ad=old, image=AdImage.generate_storage_key())
        recent = _make_ad(
            seller,
            category,
            city,
            status=AdStatus.ARCHIVED,
            published_at=timezone.now() - timedelta(days=30),
        )
        call_command("delete_sweep")
        assert not Ad.objects.filter(pk=old.pk).exists()
        assert Ad.objects.filter(pk=recent.pk).exists()

    def test_cascades_ad_images(self, seller, category, city):

        old = _make_ad(
            seller,
            category,
            city,
            status=AdStatus.ARCHIVED,
            published_at=timezone.now() - timedelta(days=200),
        )
        img = AdImage.objects.create(ad=old, image=AdImage.generate_storage_key())
        call_command("delete_sweep")
        assert not AdImage.objects.filter(pk=img.pk).exists()

    def test_lock_id_is_delete_sweep(self):
        assert AdvisoryLockId.DELETE_SWEEP == 2


class TestSweepDrafts:
    """Tests for sweep_drafts command (advisory lock 4, 30-minute window)."""

    def test_dry_run_does_not_delete(self, seller, category, city):

        old = _make_ad(
            seller,
            category,
            city,
            status=AdStatus.DRAFT,
            created_at=timezone.now() - timedelta(minutes=90),
        )
        call_command("sweep_drafts", "--dry-run")
        assert Ad.objects.filter(pk=old.pk).exists()

    def test_deletes_drafts_older_than_30_minutes(self, seller, category, city):

        old = _make_ad(
            seller,
            category,
            city,
            status=AdStatus.DRAFT,
            created_at=timezone.now() - timedelta(minutes=90),
        )
        recent = _make_ad(
            seller,
            category,
            city,
            status=AdStatus.DRAFT,
            created_at=timezone.now() - timedelta(minutes=5),
        )
        call_command("sweep_drafts")
        assert not Ad.objects.filter(pk=old.pk).exists()
        assert Ad.objects.filter(pk=recent.pk).exists()

    def test_does_not_touch_published_drafts(self, seller, category, city):

        # Published ads with old created_at must survive the draft sweep.
        _make_ad(
            seller,
            category,
            city,
            status=AdStatus.PUBLISHED,
            created_at=timezone.now() - timedelta(days=10),
        )
        call_command("sweep_drafts")
        assert Ad.objects.filter(status=AdStatus.PUBLISHED).count() == 1

    def test_lock_id_is_sweep_drafts(self):
        assert AdvisoryLockId.SWEEP_DRAFTS == 4


class TestCleanupLoginTokens:
    """Tests for cleanup_login_tokens command (advisory lock 5)."""

    def _make_token(self, **kwargs) -> LoginToken:
        defaults = {
            "token_hash": f"hash_{LoginToken.objects.count()}_{id(kwargs)}",
            "telegram_id": 900000002,
            "expires_at": timezone.now() - timezone.timedelta(hours=1),
        }
        defaults.update(kwargs)
        return LoginToken.objects.create(**defaults)

    def test_dry_run_does_not_delete(self):

        expired = self._make_token(expires_at=timezone.now() - timedelta(hours=1))
        call_command("cleanup_login_tokens", "--dry-run")
        assert LoginToken.objects.filter(pk=expired.pk).exists()

    def test_deletes_expired_tokens(self):

        # Expired token (expires_at in the past) is deleted.
        expired = self._make_token(expires_at=timezone.now() - timedelta(hours=1))
        # Valid (unexpired, unconsumed) token is preserved.
        valid = self._make_token(expires_at=timezone.now() + timedelta(hours=1))
        call_command("cleanup_login_tokens")
        assert not LoginToken.objects.filter(pk=expired.pk).exists()
        assert LoginToken.objects.filter(pk=valid.pk).exists()

    def test_preserves_recently_consumed_tokens(self):

        # consumed_at is set but created_at is recent (auto_now_add), so the
        # "consumed >24h ago" branch must NOT fire. With a future expiry the
        # expired branch also does not fire -> token is preserved.
        consumed_recent = self._make_token(
            expires_at=timezone.now() + timedelta(hours=1),
            consumed_at=timezone.now() - timedelta(hours=1),
        )
        call_command("cleanup_login_tokens")
        assert LoginToken.objects.filter(pk=consumed_recent.pk).exists()

    def test_preserves_fresh_unconsumed_tokens(self):

        token = self._make_token(
            expires_at=timezone.now() + timedelta(hours=1),
            consumed_at=None,
        )
        call_command("cleanup_login_tokens")
        assert LoginToken.objects.filter(pk=token.pk).exists()

    def test_lock_id_is_cleanup_login_tokens(self):
        assert AdvisoryLockId.CLEANUP_LOGIN_TOKENS == 5


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
        fresh = User.objects.create(telegram_id=900000003, password="x")
        call_command("consent_hard_delete")
        assert not User.objects.filter(pk=seller.pk).exists()
        assert User.objects.filter(pk=fresh.pk).exists()

    def test_nulls_analytics_event_user(self, seller):

        seller.consent_revoked_at = timezone.now() - timedelta(days=60)
        seller.save()
        event = AnalyticsEvent.objects.create(event_type="search_performed", user=seller)
        call_command("consent_hard_delete")
        event.refresh_from_db()
        assert event.user_id is None

    def test_nulls_moderator_action_log_user(self, seller):

        seller.consent_revoked_at = timezone.now() - timedelta(days=60)
        seller.save()
        log = ModeratorActionLog.objects.create(
            user=seller,
            action_type="ban_account",
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

    def test_lock_id_is_consent_hard_delete(self):
        assert AdvisoryLockId.CONSENT_HARD_DELETE == 3


class TestPurgeFailedAds:
    """Tests for purge_failed_ads command (advisory lock 6, 7-day window)."""

    def test_dry_run_does_not_delete(self, seller, category, city):

        old = _make_ad(
            seller,
            category,
            city,
            status=AdStatus.ON_MODERATION_FAILED,
            moderation_failed_at=timezone.now() - timedelta(days=10),
        )
        call_command("purge_failed_ads", "--dry-run")
        assert Ad.objects.filter(pk=old.pk).exists()

    def test_purges_failed_ads_older_than_7_days(self, seller, category, city):

        old = _make_ad(
            seller,
            category,
            city,
            status=AdStatus.ON_MODERATION_FAILED,
            moderation_failed_at=timezone.now() - timedelta(days=10),
        )
        recent = _make_ad(
            seller,
            category,
            city,
            status=AdStatus.ON_MODERATION_FAILED,
            moderation_failed_at=timezone.now() - timedelta(days=2),
        )
        call_command("purge_failed_ads")
        assert not Ad.objects.filter(pk=old.pk).exists()
        assert Ad.objects.filter(pk=recent.pk).exists()

    def test_does_not_purge_other_statuses(self, seller, category, city):

        rejected = _make_ad(
            seller,
            category,
            city,
            status=AdStatus.REJECTED,
            rejected_at=timezone.now() - timedelta(days=200),
        )
        call_command("purge_failed_ads")
        assert Ad.objects.filter(pk=rejected.pk).exists()

    def test_lock_id_is_purge_failed_ads(self):
        assert AdvisoryLockId.PURGE_FAILED_ADS == 6


class TestPurgeRejectedAds:
    """Tests for purge_rejected_ads command (advisory lock 7, 90-day window)."""

    def test_dry_run_does_not_delete(self, seller, category, city):

        old = _make_ad(
            seller,
            category,
            city,
            status=AdStatus.REJECTED,
            rejected_at=timezone.now() - timedelta(days=120),
        )
        call_command("purge_rejected_ads", "--dry-run")
        assert Ad.objects.filter(pk=old.pk).exists()

    def test_purges_rejected_ads_older_than_90_days(self, seller, category, city):

        old = _make_ad(
            seller,
            category,
            city,
            status=AdStatus.REJECTED,
            rejected_at=timezone.now() - timedelta(days=120),
        )
        recent = _make_ad(
            seller,
            category,
            city,
            status=AdStatus.REJECTED,
            rejected_at=timezone.now() - timedelta(days=30),
        )
        call_command("purge_rejected_ads")
        assert not Ad.objects.filter(pk=old.pk).exists()
        assert Ad.objects.filter(pk=recent.pk).exists()

    def test_preserves_moderation_log_with_ad_set_null(self, seller, category, city):

        old = _make_ad(
            seller,
            category,
            city,
            status=AdStatus.REJECTED,
            rejected_at=timezone.now() - timedelta(days=120),
        )
        log = ModeratorActionLog.objects.create(
            ad=old,
            user=seller,
            action_type="reject",
            reason="internal",
        )
        call_command("purge_rejected_ads")
        log.refresh_from_db()
        assert ModeratorActionLog.objects.filter(pk=log.pk).exists()
        assert log.ad_id is None

    def test_lock_id_is_purge_rejected_ads(self):
        assert AdvisoryLockId.PURGE_REJECTED_ADS == 7
