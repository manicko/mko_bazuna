"""
Unit tests for AdImageService (QLT-012).

Verifies:
- create_or_skip creates a new row when no duplicate exists
- create_or_skip returns the existing duplicate (same SHA-256, same seller)
- create_or_skip creates a new row for a different seller (no false dedup)
- create_or_skip creates a row with empty sha256 when the file is absent
- the dedup skip is logged
"""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from django.test import override_settings
from django.utils import timezone

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_media_root() -> Generator[Path]:
    """Create a temporary MEDIA_ROOT isolated from the real media volume."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def seller() -> object:
    """Create a seller user for ad fixtures."""
    from apps.users.models import User

    return User.objects.create(
        telegram_id=900000030,
        chat_id=900000030,
        password="x",
    )


@pytest.fixture
def seller2() -> object:
    """Create a second seller user."""
    from apps.users.models import User

    return User.objects.create(
        telegram_id=900000031,
        chat_id=900000031,
        password="x",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ad(seller: object) -> object:
    """Create a minimal PUBLISHED ad owned by *seller*."""
    from apps.ads.models import Ad
    from apps.core.enums import AdStatus

    return Ad.objects.create(
        user=seller,
        title="Test Ad",
        description="Test description",
        category=None,
        city=None,
        category_name="Test Category",
        status=AdStatus.PUBLISHED,
        published_at=timezone.now(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAdImageServiceCreateOrSkip:
    """Tests for AdImageService.create_or_skip()."""

    def test_creates_new_image_with_hash(self, seller, isolated_media_root):
        """When no duplicate exists, a new row is created with sha256 set."""
        from apps.ads.services.images import AdImageService

        ad = _make_ad(seller)
        key = "photo-a.jpg"
        file_path = isolated_media_root / key
        file_path.write_bytes(b"identical-pixel-data-a")

        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            result = AdImageService.create_or_skip(ad, key, position=0)

        assert result.pk is not None
        assert result.image == key
        assert result.sha256 != ""
        assert result.position == 0

    def test_returns_existing_duplicate_same_user(
        self, seller, isolated_media_root, caplog
    ):
        """Same SHA-256 + same seller → returns existing row, no new row."""
        from apps.ads.models import AdImage
        from apps.ads.services.images import AdImageService

        ad_a = _make_ad(seller)
        key = "dup-photo.jpg"
        file_path = isolated_media_root / key
        file_path.write_bytes(b"identical-byte-content")

        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            first = AdImageService.create_or_skip(ad_a, key, position=0)
            second = AdImageService.create_or_skip(ad_a, key, position=1)

        assert second is not None
        assert second.pk == first.pk
        assert AdImage.objects.count() == 1

        # The third call must also be inside override_settings so the file is
        # found on disk and the SHA-256 is computed (otherwise dedup is skipped).
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            with caplog.at_level(logging.INFO):
                third = AdImageService.create_or_skip(ad_a, key, position=2)

        assert third.pk == first.pk
        assert any("dedup" in record.message.lower() for record in caplog.records)

    def test_creates_new_image_different_user(
        self, seller, seller2, isolated_media_root
    ):
        """Same SHA-256 but different seller → new row created (no false dedup)."""
        from apps.ads.models import AdImage
        from apps.ads.services.images import AdImageService

        ad_a = _make_ad(seller)
        ad_b = _make_ad(seller2)
        key = "shared-photo.jpg"
        file_path = isolated_media_root / key
        file_path.write_bytes(b"identical-byte-content")

        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            first = AdImageService.create_or_skip(ad_a, key, position=0)
            second = AdImageService.create_or_skip(ad_b, key, position=0)

        assert first.pk != second.pk
        assert AdImage.objects.count() == 2

    def test_file_missing_creates_empty_hash(self, seller, isolated_media_root):
        """When the file is absent, sha256 is empty and a row is still created."""
        from apps.ads.services.images import AdImageService

        ad = _make_ad(seller)
        key = "nonexistent.jpg"

        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            result = AdImageService.create_or_skip(ad, key, position=0)

        assert result.pk is not None
        assert result.sha256 == ""
