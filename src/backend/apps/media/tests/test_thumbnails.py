"""
Unit tests for ThumbnailService.

Tests cover all three size variants, aspect ratio preservation for
non-square images, progressive JPEG output, and invalid input handling.
No database interaction required — uses pytest-style with temporary
directories.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from apps.core.enums import ThumbnailSizeStrEnum
from apps.media.services.thumbnails import ThumbnailService


def _make_test_image(width: int, height: int) -> bytes:
    """Create a simple RGB test image and return its JPEG bytes.

    Args:
        width: Image width in pixels.
        height: Image height in pixels.

    Returns:
        JPEG-encoded image content as bytes.
    """
    image = Image.new("RGB", (width, height), color=(64, 128, 192))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=95)
    buffer.seek(0)
    return buffer.getvalue()


class TestThumbnailService:
    """Tests for ThumbnailService thumbnail generation."""

    def test_small_thumbnail_generation(self, tmp_path: Path) -> None:
        """SMALL variant produces a 240x180 thumbnail."""
        photo_bytes = _make_test_image(1920, 1080)
        service = ThumbnailService(storage_dir=str(tmp_path))
        result = service.generate_thumbnails(photo_bytes, "photo.jpg")

        thumb_path = tmp_path / result[ThumbnailSizeStrEnum.SMALL]
        assert thumb_path.exists()

        with Image.open(thumb_path) as img:
            assert img.width <= 240
            assert img.height <= 180
            assert img.format == "JPEG"

    def test_medium_thumbnail_generation(self, tmp_path: Path) -> None:
        """MEDIUM variant produces a 640x480 thumbnail."""
        photo_bytes = _make_test_image(1920, 1080)
        service = ThumbnailService(storage_dir=str(tmp_path))
        result = service.generate_thumbnails(photo_bytes, "photo.jpg")

        thumb_path = tmp_path / result[ThumbnailSizeStrEnum.MEDIUM]
        assert thumb_path.exists()

        with Image.open(thumb_path) as img:
            assert img.width <= 640
            assert img.height <= 480
            assert img.format == "JPEG"

    def test_large_thumbnail_generation(self, tmp_path: Path) -> None:
        """LARGE variant produces a 1280x960 thumbnail."""
        photo_bytes = _make_test_image(1920, 1080)
        service = ThumbnailService(storage_dir=str(tmp_path))
        result = service.generate_thumbnails(photo_bytes, "photo.jpg")

        thumb_path = tmp_path / result[ThumbnailSizeStrEnum.LARGE]
        assert thumb_path.exists()

        with Image.open(thumb_path) as img:
            assert img.width <= 1280
            assert img.height <= 960
            assert img.format == "JPEG"

    def test_aspect_ratio_preservation(self, tmp_path: Path) -> None:
        """Non-square (wide) image preserves aspect ratio inside box."""
        photo_bytes = _make_test_image(2000, 1000)
        service = ThumbnailService(storage_dir=str(tmp_path))
        result = service.generate_thumbnails(photo_bytes, "wide.jpg")

        thumb_path = tmp_path / result[ThumbnailSizeStrEnum.SMALL]
        with Image.open(thumb_path) as img:
            w, h = img.size
            # Must fit within 240x180 box
            assert w <= 240
            assert h <= 180
            # Must preserve 2:1 aspect ratio (2000:1000)
            # Allow off-by-one from thumbnail() rounding
            assert abs(w / h - 2.0) < 0.1, (
                f"Aspect ratio {w}/{h} = {w/h:.3f} differs from 2.0"
            )

    def test_progressive_jpeg_output(self, tmp_path: Path) -> None:
        """Generated JPEG thumbnails are progressive."""
        photo_bytes = _make_test_image(800, 600)
        service = ThumbnailService(storage_dir=str(tmp_path))
        result = service.generate_thumbnails(photo_bytes, "prog.jpg")

        thumb_path = tmp_path / result[ThumbnailSizeStrEnum.MEDIUM]
        with Image.open(thumb_path) as img:
            # Pillow stores progressive flag as int 1, not True
            assert img.info.get("progressive"), (
                "Expected progressive JPEG output"
            )

    def test_invalid_image_handling(self, tmp_path: Path) -> None:
        """Invalid image bytes raises ValueError."""
        service = ThumbnailService(storage_dir=str(tmp_path))
        try:
            service.generate_thumbnails(b"not-an-image-data", "bad.jpg")
        except UnidentifiedImageError:
            pass
        except Exception as exc:
            msg = f"Expected UnidentifiedImageError, got {type(exc).__name__}: {exc}"
            raise AssertionError(msg) from exc
        else:
            msg = "Expected UnidentifiedImageError was not raised"
            raise AssertionError(msg)