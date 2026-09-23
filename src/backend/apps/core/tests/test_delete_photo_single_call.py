"""
Regression guard verifying that delete_photo is called exactly once per
storage key across all sweep commands and withdraw_consent (ENT-005).

Before ENT-005, sweep commands called delete_photo in a redundant loop
after transaction.atomic(), duplicating the signal's on_commit callback.
Each storage key must be passed to delete_photo exactly once — no more,
no fewer.

Parametrized across:
  - delete_sweep        (ARCHIVED ads > 60 days, lock 2)
  - purge_failed_ads    (ON_MODERATION_FAILED ads > 7 days, lock 6)
  - purge_rejected_ads  (REJECTED ads > 90 days, lock 7)
  - purge_deleted_ads   (DELETED ads > 120 days, lock 11)
  - sweep_drafts        (DRAFT ads > 30 min, lock 4)
  - consent_hard_delete (users, consent revoked > 30 days, lock 3)

Service:
  - withdraw_consent    (soft-deletes user ads, DRAFT AdImage cleanup)

Control:
  - sweep_orphaned_media (calls delete_photo directly — NOT via signal)
"""

from __future__ import annotations

import tempfile
from collections.abc import Generator
from datetime import timedelta
from pathlib import Path

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from apps.ads.models import Ad, AdImage
from apps.core.enums import AdStatus
from apps.users.models import User
from apps.users.services.deletion import withdraw_consent
from conftest import create_test_ad

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.integration,
]


# Storage keys for an AdImage with image + 3 thumbnails
_IMAGE_KEY = "regression-test.jpg"
_THUMB_KEYS = [
    "regression-test-small.jpg",
    "regression-test-medium.jpg",
    "regression-test-large.jpg",
]
_ALL_KEYS = [_IMAGE_KEY, *_THUMB_KEYS]


def _make_ad_with_image(user, category, city, status: AdStatus) -> AdImage:
    """Create an ad + AdImage with all 4 storage keys set."""
    ad = create_test_ad(user, category, city, status=status)
    return AdImage.objects.create(
        ad=ad,
        image=_IMAGE_KEY,
        thumbnail_small=_THUMB_KEYS[0],
        thumbnail_medium=_THUMB_KEYS[1],
        thumbnail_large=_THUMB_KEYS[2],
    )


def _backdate(ad_pk: int, field: str, delta: timedelta) -> None:
    """Backdate a timestamp field on an ad (auto_now_add / status ts)."""
    Ad.objects.filter(pk=ad_pk).update(**{field: timezone.now() - delta})


def _assert_once_per_key(deleted_keys: list[str], expected: list[str]) -> None:
    """Assert delete_photo was called exactly once per key (no duplicates)."""
    assert len(deleted_keys) == len(expected), (
        f"Expected {len(expected)} delete_photo calls, got {len(deleted_keys)}"
    )
    assert sorted(deleted_keys) == sorted(expected), (
        f"Key mismatch: expected {sorted(expected)}, got {sorted(deleted_keys)}"
    )
    for key in expected:
        assert deleted_keys.count(key) == 1, (
            f"delete_photo called {deleted_keys.count(key)} times for {key!r}, expected exactly 1"
        )


class TestDeletePhotoSingleCall:
    """Each storage key must reach delete_photo exactly once.

    The AdImage pre_delete signal schedules delete_photo via on_commit after
    transaction.atomic() commits. A redundant post-transaction loop (the bug
    fixed in ENT-005) would have doubled every call.
    """

    @pytest.mark.parametrize(
        ("command_name", "status", "backdate_field", "backdate_delta"),
        [
            pytest.param(
                "delete_sweep",
                AdStatus.ARCHIVED,
                "archived_at",
                timedelta(days=200),
                id="delete_sweep",
            ),
            pytest.param(
                "purge_failed_ads",
                AdStatus.ON_MODERATION_FAILED,
                "moderation_failed_at",
                timedelta(days=10),
                id="purge_failed_ads",
            ),
            pytest.param(
                "purge_rejected_ads",
                AdStatus.REJECTED,
                "rejected_at",
                timedelta(days=120),
                id="purge_rejected_ads",
            ),
            pytest.param(
                "purge_deleted_ads",
                AdStatus.DELETED,
                "deleted_at",
                timedelta(days=200),
                id="purge_deleted_ads",
            ),
            pytest.param(
                "sweep_drafts",
                AdStatus.DRAFT,
                "created_at",
                timedelta(minutes=90),
                id="sweep_drafts",
            ),
        ],
    )
    def test_sweep_command_delete_photo_once_per_key(
        self,
        command_name: str,
        status: AdStatus,
        backdate_field: str,
        backdate_delta: timedelta,
        seller,
        category,
        city,
        monkeypatch,
    ) -> None:
        """Each sweep command passes every storage key to delete_photo exactly once."""
        img = _make_ad_with_image(seller, category, city, status)
        ad_pk = img.ad_id
        _backdate(ad_pk, backdate_field, backdate_delta)

        deleted_keys: list[str] = []
        monkeypatch.setattr(
            "apps.media.signals.delete_photo",
            lambda key: deleted_keys.append(key),
        )

        call_command(command_name)

        _assert_once_per_key(deleted_keys, img.storage_keys())
        assert not Ad.objects.filter(pk=ad_pk).exists()

    def test_consent_hard_delete_delete_photo_once_per_key(
        self, seller, category, city, monkeypatch
    ) -> None:
        """consent_hard_delete passes every storage key to delete_photo exactly once."""
        seller.consent_revoked_at = timezone.now() - timedelta(days=60)
        seller.save()
        img = _make_ad_with_image(seller, category, city, AdStatus.PUBLISHED)

        deleted_keys: list[str] = []
        monkeypatch.setattr(
            "apps.media.signals.delete_photo",
            lambda key: deleted_keys.append(key),
        )

        call_command("consent_hard_delete")

        _assert_once_per_key(deleted_keys, img.storage_keys())
        assert not User.objects.filter(pk=seller.pk).exists()

    def test_withdraw_consent_delete_photo_once_per_key(
        self, user, category, city, monkeypatch
    ) -> None:
        """withdraw_consent passes every DRAFT-ad storage key to delete_photo once.

        DRAFT ads are mid-FSM creations whose images are orphaned on withdrawal.
        The signal's on_commit callback deletes them after the transaction commits.
        """
        img = _make_ad_with_image(user, category, city, AdStatus.DRAFT)

        deleted_keys: list[str] = []
        monkeypatch.setattr(
            "apps.media.signals.delete_photo",
            lambda key: deleted_keys.append(key),
        )

        result = withdraw_consent(user)

        _assert_once_per_key(deleted_keys, img.storage_keys())
        assert set(result) == set(img.storage_keys())
        assert len(result) == len(img.storage_keys())

    # ------------------------------------------------------------------
    # Control: sweep_orphaned_media calls delete_photo directly — NOT via
    # the signal.  This confirms the control path is unaffected by ENT-005.
    # ------------------------------------------------------------------

    @pytest.fixture
    def isolated_media_root(self) -> Generator[Path]:
        """Create a temporary MEDIA_ROOT isolated from the real media volume."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_sweep_orphaned_media_delete_photo_once_per_key(
        self,
        seller,
        category,
        city,
        isolated_media_root,
        monkeypatch,
    ) -> None:
        """Control: sweep_orphaned_media calls delete_photo once per orphan file.

        Unlike the sweep commands above, sweep_orphaned_media does NOT rely on
        the AdImage pre_delete signal. It scans the filesystem for orphaned
        files and calls delete_photo directly in its own loop. This test
        confirms that path is unaffected by ENT-005.
        """
        # One AdImage in the DB → its files are NOT orphans (must be preserved)
        img = _make_ad_with_image(seller, category, city, AdStatus.PUBLISHED)

        # Write physical files for referenced keys + 3 orphan files
        orphan_keys = ["orphan-1.jpg", "orphan-2.jpg", "orphan-3.jpg"]
        for key in [*_ALL_KEYS, *orphan_keys]:
            (isolated_media_root / key).write_bytes(b"data")

        deleted_keys: list[str] = []
        monkeypatch.setattr(
            "apps.media.management.commands.sweep_orphaned_media.delete_photo",
            lambda key: deleted_keys.append(key),
        )

        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            call_command("sweep_orphaned_media")

        _assert_once_per_key(deleted_keys, orphan_keys)
        # Referenced files must survive the orphan sweep
        for key in img.storage_keys():
            assert (isolated_media_root / key).exists(), f"referenced file {key!r} was orphaned"
