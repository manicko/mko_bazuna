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
from PIL import Image
from PIL.ExifTags import Base as ExifBase
from django.test import override_settings

from telegram_bot.handlers.ad_create import save_photo

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


@pytest.fixture
def jpeg_with_exif() -> bytes:
    """Generate a small JPEG image with embedded EXIF metadata.

    Uses manual TIFF IFD construction because Pillow 12.x's ``Exif.tobytes()``
    requires a file pointer that is not available on in-memory images.
    """
    import struct

    tiff_header = b"II\x2a\x00\x08\x00\x00\x00"
    make_str = b"CameraMaker\x00"
    model_str = b"CameraModel\x00"

    num_entries = 3
    ifd_size = 2 + num_entries * 12 + 4
    data_offset = 8 + ifd_size

    make_offset = data_offset
    model_offset = make_offset + len(make_str)
    gps_ifd_offset = model_offset + len(model_str)

    def _tiff_tag(tag_id: int, data_type: int, count: int, value: int) -> bytes:
        return struct.pack("<HHLL", tag_id, data_type, count, value)

    entries = b""
    entries += _tiff_tag(ExifBase.Make, 2, len(make_str), make_offset)
    entries += _tiff_tag(ExifBase.Model, 2, len(model_str), model_offset)
    entries += _tiff_tag(ExifBase.GPSInfo, 4, 1, gps_ifd_offset)

    gps_ifd = struct.pack("<H", 0) + struct.pack("<L", 0)

    exif_data = (
        tiff_header
        + struct.pack("<H", num_entries)
        + entries
        + struct.pack("<L", 0)
        + make_str
        + model_str
        + gps_ifd
    )
    exif_segment = b"Exif\x00\x00" + exif_data

    buf = io.BytesIO()
    img = Image.new("RGB", (100, 100), color="red")
    img.save(buf, format="JPEG", exif=exif_segment)
    return buf.getvalue()


class TestSavePhotoExifStripping:
    """save_photo must strip EXIF metadata from bytes written to disk."""

    def test_save_photo_strips_exif_on_disk(self, tmp_path, jpeg_with_exif):
        """Bytes written to disk by save_photo contain no EXIF metadata."""
        media_root = tmp_path / "media"
        media_root.mkdir()
        with override_settings(MEDIA_ROOT=media_root):
            storage_key, sha256 = asyncio.run(
                save_photo("exif-test.jpg", jpeg_with_exif, user_id=None)
            )

        written_path = media_root / storage_key
        assert written_path.exists(), "save_photo did not write the file to disk"

        written_bytes = written_path.read_bytes()

        # The written bytes must still be a valid JPEG.
        assert written_bytes.startswith(b"\xff\xd8\xff"), "Written file is not a valid JPEG"

        # Re-open and verify EXIF tags are gone.
        img = Image.open(io.BytesIO(written_bytes))
        exif_data = img.getexif()
        assert ExifBase.Make not in exif_data, "EXIF Make tag survived save_photo"
        assert ExifBase.Model not in exif_data, "EXIF Model tag survived save_photo"
        assert ExifBase.GPSInfo not in exif_data, "EXIF GPSInfo tag survived save_photo"

        # The stripped output must differ from the input (proves stripping ran).
        assert written_bytes != jpeg_with_exif, "EXIF was not stripped from written bytes"

        # SHA-256 must be over the cleaned bytes (deterministic, non-empty).
        assert sha256, "save_photo did not return a SHA-256 digest"
        assert len(sha256) == 64, "SHA-256 must be a 64-char hex digest"
