"""
Integration test for the full ``save_photo`` -> disk -> ``generate_thumbnails``
-> ``AdImage`` thumbnail pipeline (coverage gap C-09).

No test previously exercises this *entire* chain:

* ``test_save_photo_exif.py`` tests ``save_photo`` EXIF stripping only (no
  thumbnails are produced).
* ``test_save_photo_integration.py`` (telegram_bot/tests) tests the
  ``generate_thumbnails`` -> ``AdImage`` path via ``update_ad_and_moderate`` but
  *bypasses* ``save_photo`` -- it writes the bytes manually to ``tmp_path``.

This module calls ``save_photo`` for real (an EXIF-bearing JPEG in, an
EXIF-free JPEG persisted to ``MEDIA_ROOT``), then reads that file back from
disk and runs it through the real ``ThumbnailService``, then persists the
returned storage keys on an ``AdImage`` row via ``AdImageService.create_or_skip``
-- mirroring the production finalisation path in
``telegram_bot/handlers/ad_create.py`` (photo written at the collection step,
then read + thumbnailed + persisted at finalisation).

Lives under ``apps/media/tests/`` so it reuses the canonical ``seller`` /
``category`` / ``city`` fixtures and ``create_test_ad`` helper from the root
``src/backend/conftest.py`` (discoverable because this package is nested
under ``src/backend/``).
"""

from __future__ import annotations

import asyncio
import io
from collections.abc import Generator
from pathlib import Path

import pytest
from PIL import Image
from django.test import override_settings

from apps.ads.models import Ad
from apps.ads.services.images import AdImageService
from apps.core.enums import AdStatus, ThumbnailSizeStrEnum
from apps.media.services.thumbnails import ThumbnailService
from telegram_bot.handlers.ad_create import save_photo
from telegram_bot.services.media import generate_storage_key

from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]

# EXIF Orientation tag (0x0112 = 274). Embedding it in the input image lets us
# prove that ``save_photo`` strips metadata *before* the thumbnail pipeline sees
# the bytes, and that no Orientation tag leaks into the thumbnails.
_ORIENTATION_TAG = 0x0112


def _make_jpeg_with_exif(width: int = 800, height: int = 600) -> bytes:
    """Return JPEG bytes carrying an EXIF Orientation tag (no GPS/owner data)."""
    buf = io.BytesIO()
    img = Image.new("RGB", (width, height), color=(64, 128, 192))
    exif = img.getexif()
    exif[_ORIENTATION_TAG] = 6  # rotated 90 degrees CW -> needs transpose
    img.save(buf, format="JPEG", quality=95, exif=exif.tobytes())
    buf.seek(0)
    return buf.getvalue()


def _save_and_thumbnail(media_root, photo_bytes):
    """Drive the full ``save_photo`` -> disk -> ``generate_thumbnails`` chain.

    Returns ``(storage_key, on_disk_bytes, thumbnail_keys)``.
    """
    storage_key = asyncio.run(save_photo(generate_storage_key(), photo_bytes))

    original_path = media_root / storage_key
    assert original_path.exists(), "save_photo did not persist the file to disk"
    on_disk_bytes = original_path.read_bytes()

    service = ThumbnailService(str(media_root))
    thumbnail_keys = service.generate_thumbnails(on_disk_bytes, storage_key)

    return storage_key, on_disk_bytes, thumbnail_keys


class TestSavePhotoThumbnailIntegration:
    """End-to-end: ``save_photo`` -> disk -> thumbnails -> ``AdImage``."""

    @pytest.fixture
    def media_root(self, tmp_path) -> Generator[Path]:
        """Isolated ``MEDIA_ROOT`` override for each test."""
        root = tmp_path / "media"
        root.mkdir()
        with override_settings(MEDIA_ROOT=str(root)):
            yield root

    def test_save_photo_persists_exif_free_file_then_thumbnails_generated(
        self, media_root
    ) -> None:
        """``save_photo`` writes an EXIF-free JPEG the thumbnailer reads from disk."""
        photo_bytes = _make_jpeg_with_exif(800, 600)

        storage_key, on_disk_bytes, thumbnail_keys = _save_and_thumbnail(
            media_root, photo_bytes
        )

        # 1. save_photo persisted the EXIF-stripped file to disk.
        assert on_disk_bytes.startswith(b"\xff\xd8\xff"), (
            "written file is not a valid JPEG"
        )
        assert on_disk_bytes != photo_bytes, (
            "save_photo did not re-encode/strip the input"
        )

        img = Image.open(io.BytesIO(on_disk_bytes))
        exif = img.getexif()
        assert _ORIENTATION_TAG not in exif, "EXIF Orientation survived save_photo"
        assert img.format == "JPEG"

        # 2. generate_thumbnails produced a key for every ThumbnailSizeStrEnum member.
        for size in ThumbnailSizeStrEnum:
            assert size in thumbnail_keys, f"missing thumbnail for {size}"

        # 3. Each thumbnail follows the '<stem>-<size>.jpg' pattern and exists on disk.
        stem = storage_key.rsplit(".", 1)[0]
        for size in ThumbnailSizeStrEnum:
            key = thumbnail_keys[size]
            assert key == f"{stem}-{size.value}.jpg", (
                f"unexpected key for {size}: {key}"
            )
            thumb_path = media_root / key
            assert thumb_path.is_file(), f"thumbnail file not written: {key}"
            with Image.open(thumb_path) as thumb:
                assert thumb.format == "JPEG"
                thumb.verify()

    def test_full_chain_populates_adimage_thumbnail_fields(
        self, seller, category, city, media_root
    ) -> None:
        """``save_photo`` -> ``generate_thumbnails`` keys land on ``AdImage.thumbnail_*``."""
        ad: Ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        photo_bytes = _make_jpeg_with_exif(1920, 1080)

        storage_key, _on_disk_bytes, thumbnail_keys = _save_and_thumbnail(
            media_root, photo_bytes
        )

        ad_image = AdImageService.create_or_skip(
            ad=ad,
            image=storage_key,
            telegram_file_id="AgADBQ",
            position=0,
            thumbnail_small=thumbnail_keys[ThumbnailSizeStrEnum.SMALL],
            thumbnail_medium=thumbnail_keys[ThumbnailSizeStrEnum.MEDIUM],
            thumbnail_large=thumbnail_keys[ThumbnailSizeStrEnum.LARGE],
        )

        for size in ThumbnailSizeStrEnum:
            field_name = f"thumbnail_{size.value}"
            field_value = getattr(ad_image, field_name)
            key = thumbnail_keys[size]
            assert field_value == key, (
                f"{field_name} mismatch: {field_value!r} != {key!r}"
            )
            assert field_value is not None
            assert field_value.endswith(f"-{size.value}.jpg"), (
                f"{field_name} does not follow '<uuid>-{size.value}.jpg': {field_value}"
            )
            # Every thumbnail referenced by the AdImage exists on disk.
            assert (media_root / field_value).is_file(), (
                f"thumbnail file for {field_name} missing on disk: {field_value}"
            )
