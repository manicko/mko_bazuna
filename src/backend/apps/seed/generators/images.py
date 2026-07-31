"""ImageGenerator for seed data — creates bundled demo photos and AdImage records."""

from __future__ import annotations

import io
import logging
import os
import uuid
from typing import Any

from django.conf import settings

from apps.ads.models import Ad, AdImage
from apps.media.services.thumbnails import ThumbnailService
from apps.seed.generators.base import BaseGenerator

logger = logging.getLogger(__name__)

# Small SVG-based JPEG placeholder data (valid JPEG header + small grey image)
# Generated once and shared across all ads
_SEED_IMAGE_POOL: list[bytes] | None = None


def _generate_placeholder_jpeg(width: int, height: int, seed_offset: int) -> bytes:
    """Generate a simple solid-color JPEG using Pillow.

    Args:
        width: Image width in pixels.
        height: Image height in pixels.
        seed_offset: Offset for color variation.

    Returns:
        JPEG bytes.
    """
    from PIL import Image as PILImage

    # Generate a subtle color variation for variety
    r = (50 + seed_offset * 30) % 200
    g = (100 + seed_offset * 50) % 200
    b = (150 + seed_offset * 70) % 200

    img = PILImage.new("RGB", (width, height), (r, g, b))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    buf.seek(0)
    return buf.getvalue()


def _get_seed_image_pool() -> list[bytes]:
    """Return a pool of generated JPEG images for seed data.

    Generates 5 placeholder images with different sizes and colors.
    """
    global _SEED_IMAGE_POOL
    if _SEED_IMAGE_POOL is None:
        pool: list[bytes] = []
        sizes = [
            (800, 600),
            (1024, 768),
            (640, 480),
            (1200, 800),
            (900, 600),
        ]
        for i, (w, h) in enumerate(sizes):
            pool.append(_generate_placeholder_jpeg(w, h, i))
        _SEED_IMAGE_POOL = pool
    return _SEED_IMAGE_POOL


class ImageGenerator(BaseGenerator):
    """Generates AdImage records for seed ads using bundled placeholder images.

    Phase 1 — Pre-process: Generate placeholder images, write to MEDIA_ROOT/seed/,
    generate thumbnails via ThumbnailService.

    Phase 2 — Assign: For each ad, select 1-3 random images, create AdImage records
    with proper position ordering.
    """

    def __init__(self, config: dict[str, Any], ads: list[Ad]) -> None:
        """Initialize the image generator.

        Args:
            config: Parsed seed configuration dict.
            ads: List of Ad instances (must already be saved to DB).
        """
        super().__init__(config)
        self.ads = ads

    def generate(self) -> list[AdImage]:
        """Generate AdImage records for all seed ads.

        Pre-processes images once, then assigns them to ads.

        Returns:
            List of AdImage instances ready for bulk_create.
        """
        image_pool = _get_seed_image_pool()
        seed_dir = self._ensure_seed_dir()
        thumbnail_service = ThumbnailService(storage_dir=seed_dir)

        # Phase 1: Pre-process images
        image_keys = self._preprocess_images(image_pool, seed_dir, thumbnail_service)

        # Phase 2: Assign images to ads
        image_count_config = self.config.get("image_count", {"min": 1, "max": 3})
        min_images = image_count_config.get("min", 1)
        max_images = image_count_config.get("max", 3)

        ad_images: list[AdImage] = []
        for ad in self.ads:
            num_images = self.faker.random_int(min_images, max_images)
            selected = self.faker.random_elements(
                image_keys,
                length=num_images,
                unique=True,
            )
            for position, key in enumerate(selected, start=1):
                ad_img = AdImage(
                    ad=ad,
                    image=key,
                    position=position,
                    thumbnail_small=self._thumbnail_key(key, "small"),
                    thumbnail_medium=self._thumbnail_key(key, "medium"),
                    thumbnail_large=self._thumbnail_key(key, "large"),
                )
                ad_images.append(ad_img)

        return ad_images

    def _ensure_seed_dir(self) -> str:
        """Create MEDIA_ROOT/seed/ directory and return its path."""
        media_root = settings.MEDIA_ROOT
        if isinstance(media_root, str):
            seed_dir = os.path.join(media_root, "seed")
        else:
            seed_dir = str(media_root / "seed")
        os.makedirs(seed_dir, exist_ok=True)
        return seed_dir

    def _preprocess_images(
        self,
        image_pool: list[bytes],
        seed_dir: str,
        thumbnail_service: ThumbnailService,
    ) -> list[str]:
        """Pre-process all pool images: write originals, generate thumbnails.

        Args:
            image_pool: List of JPEG bytes.
            seed_dir: Target directory for seed images.
            thumbnail_service: ThumbnailService instance.

        Returns:
            List of storage keys (e.g., "<uuid>.jpg") for the pool images.
        """
        keys: list[str] = []
        for _i, img_bytes in enumerate(image_pool):
            key = f"{uuid.uuid4()}.jpg"
            original_path = os.path.join(seed_dir, key)

            # Write original image
            with open(original_path, "wb") as f:
                f.write(img_bytes)

            # Generate thumbnails - use O_EXCL safe path by checking existence
            # Since ThumbnailService uses O_EXCL, clean up first if re-running
            thumb_small = os.path.join(seed_dir, f"{os.path.splitext(key)[0]}-small.jpg")
            if os.path.exists(thumb_small):
                # Thumbnails already exist — skip regeneration
                keys.append(key)
                continue

            try:
                thumbnail_service.generate_thumbnails(img_bytes, key)
            except FileExistsError:
                logger.warning("Thumbnails already exist for %s, skipping", key)

            keys.append(key)

        return keys

    @staticmethod
    def _thumbnail_key(original_key: str, size: str) -> str:
        """Generate thumbnail key from original key and size suffix."""
        stem, _ = os.path.splitext(original_key)
        return f"{stem}-{size}.jpg"