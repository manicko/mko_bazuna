"""
Integration test for the full ``strip_photo_exif`` -> disk -> ``generate_thumbnails``
-> ``AdImage`` thumbnail pipeline (coverage gap C-09).

No test previously exercises this *entire* chain:

* ``test_save_photo_exif.py`` tests EXIF stripping only (no
  thumbnails are produced).
* ``test_save_photo_integration.py`` (telegram_bot/tests) tests the
  ``generate_thumbnails`` -> ``AdImage`` path via ``submit_ad`` but
  *bypasses* EXIF stripping -- it writes the bytes manually to ``tmp_path``.

This module strips EXIF, writes the cleaned bytes to ``MEDIA_ROOT``, then reads
that file back from disk and runs it through the real ``ThumbnailService``,
then persists the returned storage keys on an ``AdImage`` row via
``AdImageService.create_or_skip`` -- mirroring the production finalisation path
in ``telegram_bot/handlers/ad_create.py`` (photo stripped at the collection
step, then read + thumbnailed + persisted at finalisation).

Lives under ``apps/media/tests/`` so it reuses the canonical ``seller`` /
``category`` / ``city`` fixtures and ``create_test_ad`` helper from the root
``src/backend/conftest.py`` (discoverable because this package is nested
under ``src/backend/``).
"""

from __future__ import annotations

import io
from collections.abc import Generator
from pathlib import Path

import pytest
from django.test import override_settings
from PIL import Image

from apps.ads.models import Ad
from apps.ads.services.images import AdImageService
from apps.core.enums import AdStatus, ThumbnailSizeStrEnum
from apps.media.services.filesystem import (
    STAGING_PREFIX,
    generate_storage_key,
    strip_photo_exif,
)
from apps.media.services.thumbnails import ThumbnailService
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

# EXIF Orientation tag (0x0112 = 274). Embedding it in the input image lets us
# prove that ``strip_photo_exif`` removes metadata *before* the thumbnail
# pipeline sees the bytes, and that no Orientation tag leaks into the
# thumbnails.
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
    """Drive the full ``strip_photo_exif`` -> disk -> ``generate_thumbnails`` chain.

    Strips EXIF from *photo_bytes*, writes the result to the ``staging/``
    subdir of *media_root*, then runs it through ``ThumbnailService``.

    Returns ``(storage_key, on_disk_bytes, thumbnail_keys)``.
    """
    storage_key = f"{STAGING_PREFIX}{generate_storage_key()}"
    stripped = strip_photo_exif(photo_bytes)
    staging_path = media_root / storage_key
    staging_path.parent.mkdir(parents=True, exist_ok=True)
    staging_path.write_bytes(stripped)

    on_disk_bytes = staging_path.read_bytes()

    service = ThumbnailService(str(media_root))
    thumbnail_keys = service.generate_thumbnails(on_disk_bytes, storage_key)

    return storage_key, on_disk_bytes, thumbnail_keys


class TestSavePhotoThumbnailIntegration:
    """End-to-end: strip_photo_exif -> disk -> thumbnails -> ``AdImage``."""

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
        """An EXIF-free JPEG is persisted to disk for the thumbnailer to read."""
        photo_bytes = _make_jpeg_with_exif(800, 600)

        storage_key, on_disk_bytes, thumbnail_keys = _save_and_thumbnail(
            media_root, photo_bytes
        )

        # 1. EXIF-stripped file persisted to disk via strip_photo_exif + staging write.
        assert on_disk_bytes.startswith(b"\xff\xd8\xff"), (
            "written file is not a valid JPEG"
        )
        assert on_disk_bytes != photo_bytes, "input was not stripped/re-encoded"

        img = Image.open(io.BytesIO(on_disk_bytes))
        exif = img.getexif()
        assert _ORIENTATION_TAG not in exif, "EXIF Orientation survived stripping"
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
        """``strip_photo_exif`` -> ``generate_thumbnails`` keys land on ``AdImage.thumbnail_*``."""
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
