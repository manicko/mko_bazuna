"""
Integration test verifying that save_photo strips EXIF on the written file (MED-006).

While ``test_media_security.py::TestExifStripping`` unit-tests ``strip_photo_exif``
in isolation, this test exercises the full ``save_photo`` path end-to-end:
EXIF-bearing JPEG bytes go in, and the bytes on disk must be stripped.
"""

from __future__ import annotations

import asyncio
import io

import pytest
from django.test import override_settings
from PIL import Image
from PIL.ExifTags import Base as ExifBase

from telegram_bot.services.ad_data import save_photo

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


@pytest.fixture
def jpeg_with_exif() -> bytes:
    """Generate a small JPEG image with embedded EXIF metadata.

    Uses Pillow's native ``Image.Exif()`` API to build a well-formed EXIF
    segment, avoiding brittle hand-rolled TIFF IFD byte construction.
    """
    exif = Image.Exif()
    exif[ExifBase.Make] = "CameraMaker"
    exif[ExifBase.Model] = "CameraModel"
    buf = io.BytesIO()
    img = Image.new("RGB", (100, 100), color="red")
    img.save(buf, format="JPEG", exif=exif.tobytes())
    return buf.getvalue()


class TestSavePhotoExifStripping:
    """save_photo must strip EXIF metadata from bytes written to disk."""

    def test_save_photo_strips_exif_on_disk(self, tmp_path, jpeg_with_exif):
        """Bytes written to disk by save_photo contain no EXIF metadata."""
        media_root = tmp_path / "media"
        media_root.mkdir()
        with override_settings(MEDIA_ROOT=media_root):
            storage_key = asyncio.run(save_photo("exif-test.jpg", jpeg_with_exif))

        written_path = media_root / storage_key
        assert written_path.exists(), "save_photo did not write the file to disk"

        written_bytes = written_path.read_bytes()

        # The written bytes must still be a valid JPEG.
        assert written_bytes.startswith(b"\xff\xd8\xff"), (
            "Written file is not a valid JPEG"
        )

        # Re-open and verify EXIF tags are gone.
        img = Image.open(io.BytesIO(written_bytes))
        exif_data = img.getexif()
        assert ExifBase.Make not in exif_data, "EXIF Make tag survived save_photo"
        assert ExifBase.Model not in exif_data, "EXIF Model tag survived save_photo"
        assert ExifBase.GPSInfo not in exif_data, "EXIF GPSInfo tag survived save_photo"

        # The stripped output must differ from the input (proves stripping ran).
        assert written_bytes != jpeg_with_exif, (
            "EXIF was not stripped from written bytes"
        )

    def test_save_photo_writes_to_staging_subdir(self, tmp_path, jpeg_with_exif):
        """save_photo writes to the staging/ subdir and returns a staging key."""
        from apps.media.services.filesystem import STAGING_PREFIX

        media_root = tmp_path / "media"
        media_root.mkdir()
        with override_settings(MEDIA_ROOT=str(media_root)):
            storage_key = asyncio.run(save_photo("test-stg.jpg", jpeg_with_exif))

        # Returned key carries the staging prefix
        assert storage_key == f"{STAGING_PREFIX}test-stg.jpg"

        # File written inside staging/ subdir (not flat in MEDIA_ROOT)
        assert (media_root / STAGING_PREFIX / "test-stg.jpg").exists()
        assert not (media_root / "test-stg.jpg").exists(), (
            "file should be in staging/, not flat in MEDIA_ROOT"
        )
