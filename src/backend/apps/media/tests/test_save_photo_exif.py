"""
Integration test verifying that EXIF is stripped from files written to staging (MED-006).

While ``test_media_security.py::TestExifStripping`` unit-tests ``strip_photo_exif``
in isolation, this test exercises the strip-and-persist path end-to-end:
EXIF-bearing JPEG bytes go in, and the bytes on disk must be stripped.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from django.test import override_settings
from PIL import Image
from PIL.ExifTags import Base as ExifBase

from apps.media.services.filesystem import STAGING_PREFIX, strip_photo_exif

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _save_to_staging(media_root: Path, filename: str, photo_bytes: bytes) -> str:
    """Replicate the bot's ``save_photo`` inline: strip EXIF, write to staging/.

    Returns the staging storage key (``staging/<filename>``).
    """
    stripped = strip_photo_exif(photo_bytes)
    storage_key = f"{STAGING_PREFIX}{filename}"
    staging_path = media_root / storage_key
    staging_path.parent.mkdir(parents=True, exist_ok=True)
    staging_path.write_bytes(stripped)
    return storage_key


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
    """EXIF must be stripped from bytes persisted to the staging subdir."""

    def test_save_photo_strips_exif_on_disk(self, tmp_path, jpeg_with_exif):
        """Bytes written to disk via strip_photo_exif + staging write contain no EXIF."""
        media_root = tmp_path / "media"
        media_root.mkdir()
        with override_settings(MEDIA_ROOT=media_root):
            storage_key = _save_to_staging(media_root, "exif-test.jpg", jpeg_with_exif)

        written_path = media_root / storage_key
        assert written_path.exists(), "file was not written to disk"

        written_bytes = written_path.read_bytes()

        # The written bytes must still be a valid JPEG.
        assert written_bytes.startswith(b"\xff\xd8\xff"), (
            "Written file is not a valid JPEG"
        )

        # Re-open and verify EXIF tags are gone.
        img = Image.open(io.BytesIO(written_bytes))
        exif_data = img.getexif()
        assert ExifBase.Make not in exif_data, "EXIF Make tag survived stripping"
        assert ExifBase.Model not in exif_data, "EXIF Model tag survived stripping"
        assert ExifBase.GPSInfo not in exif_data, "EXIF GPSInfo tag survived stripping"

        # The stripped output must differ from the input (proves stripping ran).
        assert written_bytes != jpeg_with_exif, (
            "EXIF was not stripped from written bytes"
        )

    def test_save_photo_writes_to_staging_subdir(self, tmp_path, jpeg_with_exif):
        """Files are written to the staging/ subdir with the staging key prefix."""
        media_root = tmp_path / "media"
        media_root.mkdir()
        with override_settings(MEDIA_ROOT=str(media_root)):
            storage_key = _save_to_staging(media_root, "test-stg.jpg", jpeg_with_exif)

        # Returned key carries the staging prefix
        assert storage_key == f"{STAGING_PREFIX}test-stg.jpg"

        # File written inside staging/ subdir (not flat in MEDIA_ROOT)
        assert (media_root / STAGING_PREFIX / "test-stg.jpg").exists()
        assert not (media_root / "test-stg.jpg").exists(), (
            "file should be in staging/, not flat in MEDIA_ROOT"
        )
