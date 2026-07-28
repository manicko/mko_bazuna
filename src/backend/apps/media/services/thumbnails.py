"""
Thumbnail generation service using Pillow.

Generates three size variants (SMALL, MEDIUM, LARGE) from uploaded photo bytes
with EXIF orientation correction, LANCZOS resampling, and atomic writes.
"""

from __future__ import annotations

import io
import os

from PIL import Image, ImageOps

from apps.core.enums import ThumbnailSizeStrEnum


class ThumbnailService:
    """Service for generating thumbnail image variants from uploaded photos."""

    QUALITY = 85
    FORMAT = "JPEG"
    RESAMPLING = Image.Resampling.LANCZOS
    PROGRESSIVE = True
    SIZES: dict[ThumbnailSizeStrEnum, tuple[int, int]] = {
        ThumbnailSizeStrEnum.SMALL: (240, 180),
        ThumbnailSizeStrEnum.MEDIUM: (640, 480),
        ThumbnailSizeStrEnum.LARGE: (1280, 960),
    }

    def __init__(self, storage_dir: str) -> None:
        """Initialize with the target directory for thumbnail file output.

        Args:
            storage_dir: Absolute path to the directory where thumbnail
                files will be written.
        """
        self.storage_dir = storage_dir

    def generate_thumbnails(
        self, photo_bytes: bytes, original_key: str
    ) -> dict[ThumbnailSizeStrEnum, str]:
        """Generate all thumbnail variants from raw photo bytes.

        Corrects EXIF orientation, resizes to each configured size while
        preserving aspect ratio, and writes atomically to ``storage_dir``.

        Args:
            photo_bytes: Raw image file content as bytes.
            original_key: Original storage key (e.g. ``"<uuid>.jpg"``).

        Returns:
            Mapping from thumbnail size enum to generated storage key
            (e.g. ``"<uuid>-small.jpg"``).

        Raises:
            ValueError: If the provided bytes cannot be decoded as an image.
            FileExistsError: If a thumbnail file already exists at the
                target path (O_EXCL prevents overwrite).
        """
        stem, _ = os.path.splitext(original_key)

        image = Image.open(io.BytesIO(photo_bytes))
        corrected = ImageOps.exif_transpose(image)
        if corrected is None:
            corrected = image
        image = corrected.convert("RGB")

        thumbnails: dict[ThumbnailSizeStrEnum, str] = {}

        for size_enum, dimensions in self.SIZES.items():
            key = f"{stem}-{size_enum.value}.jpg"
            thumbnails[size_enum] = key
            target_path = os.path.join(self.storage_dir, key)

            resized = image.copy()
            resized.thumbnail(dimensions, self.RESAMPLING)

            buffer = io.BytesIO()
            resized.save(
                buffer,
                format=self.FORMAT,
                quality=self.QUALITY,
                progressive=self.PROGRESSIVE,
            )
            buffer.seek(0)

            fd = os.open(
                target_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
            try:
                os.write(fd, buffer.getvalue())
            finally:
                os.close(fd)

        return thumbnails