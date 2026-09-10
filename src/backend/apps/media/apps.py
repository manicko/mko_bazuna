"""
Media app for photo thumbnail generation and media processing.
"""

from PIL import Image

from django.apps import AppConfig


class MediaConfig(AppConfig):
    name = "apps.media"
    verbose_name = "Media"

    def ready(self) -> None:
        """Set Pillow's decompression-bomb ceiling.

        ``validate_photo`` enforces a 2MB byte cap and a 2560×2560 dimension
        cap, but ``Image.open()`` + ``ImageOps.exif_transpose()`` in
        ``validate_photo`` and ``strip_photo_exif`` trigger a full pixel decode
        *before* the dimension check.  Setting ``MAX_IMAGE_PIXELS`` just above
        the 2560² policy ceiling ensures Pillow raises
        ``DecompressionBombError`` for oversized images instead of silently
        allocating a multi-hundred-MB buffer.
        """
        # 2560 × 2560 × 2 = 13,107,200 — twice the max allowed dimension area,
        # allowing a small safety margin above the 2560×2560 policy ceiling.
        Image.MAX_IMAGE_PIXELS = 2560 * 2560 * 2
