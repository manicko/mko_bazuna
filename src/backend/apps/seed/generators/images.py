"""ImageGenerator for seed data — creates demo photos from bundled manifest and AdImage records."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from django.conf import settings

from apps.ads.models import Ad, AdImage
from apps.core.enums import ThumbnailSizeStrEnum, WriteMode
from apps.media.services.filesystem import strip_photo_exif
from apps.media.services.thumbnails import ThumbnailService
from apps.seed.generators.base import BaseGenerator
from apps.seed.paths import FIXTURES_IMAGES_DIR

logger = logging.getLogger(__name__)

ManifestEntry = dict[str, Any]


class ImageGenerator(BaseGenerator):
    """Generates AdImage records for seed ads using bundled category-tagged photos.

    Loads a photo manifest (photo_manifest.json) that maps category slugs to photo
    filenames. For each ad, selects photos matching the ad's category, falling back
    to a default pool for unknown categories.

    Phase 1 — Pre-process: Load manifest, read JPEG bytes, write to MEDIA_ROOT/seed/,
    generate thumbnails via ThumbnailService.

    Phase 2 — Assign: For each ad, select 1-3 random photos matching the ad's
    category slug, create AdImage records with proper position ordering.
    """

    def __init__(self, config: dict[str, Any], ads: list[Ad]) -> None:
        """Initialize the image generator.

        Args:
            config: Parsed seed configuration dict.
            ads: List of Ad instances (must already be saved to DB).
        """
        super().__init__(config)
        self.ads = ads
        self.photo_pool: dict[str, list[ManifestEntry]] = {}
        self.default_pool: list[ManifestEntry] = []
        self.all_image_keys: list[str] = []
        self._load_manifest()

    def _load_manifest(self) -> None:
        """Load photo_manifest.json and populate photo_pool and default_pool."""
        manifest_path = FIXTURES_IMAGES_DIR / "photo_manifest.json"
        if not manifest_path.exists():
            logger.warning(
                "Photo manifest not found at %s, using empty pool", manifest_path
            )
            self.photo_pool = {}
            self.default_pool = []
            return

        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)

        categories = manifest.get("categories", {})
        for category_slug, entry in categories.items():
            self.photo_pool[category_slug] = entry.get("photos", [])

        default = manifest.get("default", {})
        self.default_pool = default.get("photos", [])

        total_photos = sum(len(photos) for photos in self.photo_pool.values()) + len(
            self.default_pool
        )
        logger.info(
            "Loaded photo manifest: %d categories, %d photos total",
            len(self.photo_pool),
            total_photos,
        )

    def _get_photos_for_category(self, category_slug: str) -> list[ManifestEntry]:
        """Get photos for a given category slug, falling back to default pool.

        Args:
            category_slug: The slug of the ad's category.

        Returns:
            List of manifest entries (dicts with 'filename' key).
        """
        return (
            self.photo_pool.get(category_slug, self.default_pool) or self.default_pool
        )

    def generate(self) -> list[AdImage]:
        """Generate AdImage records for all seed ads.

        Builds the category → photo map from manifest METADATA (no disk I/O),
        then lazily preprocesses only the photos actually selected for ads.
        Photos that are never selected are never read from disk or written to
        MEDIA_ROOT, which makes ``--ads=0`` skip preprocessing entirely.

        Returns:
            List of AdImage instances ready for bulk_create.
        """
        # Build lookup: category_slug -> list of storage keys, filtering to
        # manifest entries whose fixture file exists (identical selection
        # surface to the old eager pipeline, which skipped missing files).
        category_key_map: dict[str, list[str]] = {}
        for cat_slug, photos in self.photo_pool.items():
            for entry in photos:
                storage_key = f"seed/{entry['filename']}"
                if (FIXTURES_IMAGES_DIR / entry["filename"]).exists():
                    category_key_map.setdefault(cat_slug, []).append(storage_key)
        for entry in self.default_pool:
            storage_key = f"seed/{entry['filename']}"
            if not (FIXTURES_IMAGES_DIR / entry["filename"]).exists():
                continue
            # Default pool photos — make them available to all categories
            for cat_slug in self.photo_pool:
                category_key_map.setdefault(cat_slug, []).append(storage_key)
            # Also keep as fallback
            category_key_map.setdefault("__default__", []).append(storage_key)

        # Flat list of all available storage keys, used only as a last-resort
        # fallback in ``_find_category_keys``.
        self.all_image_keys = [
            key for keys in category_key_map.values() for key in keys
        ]

        seed_dir = self._ensure_seed_dir()

        if not self.all_image_keys:
            logger.warning("No photos in manifest, using empty image pool")
            return []

        thumbnail_service = ThumbnailService(storage_dir=seed_dir)

        # Phase 2: Assign images to ads, preprocessing each selected photo
        # lazily so unused photos never touch the disk.
        image_count_config = self.config.get("image_count", {"min": 1, "max": 3})
        min_images = image_count_config.get("min", 1)
        max_images = image_count_config.get("max", 3)

        ad_images: list[AdImage] = []
        warned_missing: set[str] = set()
        for ad in self.ads:
            # Get photos for this ad's category, trying parent categories
            # as fallback (e.g. ads in 'cars' use 'transport' photos if 'cars'
            # has no manifest entry). This prevents random cross-category
            # assignment when a category lacks curated photos.
            category_keys = self._find_category_keys(ad, category_key_map)

            if not category_keys:
                cat_slug = ad.category.slug
                if cat_slug not in warned_missing:
                    warned_missing.add(cat_slug)
                    logger.warning(
                        "No photos for category '%s' (or any parent); "
                        "skipping images for this ad",
                        cat_slug,
                    )
                continue

            num_images = self.faker.random_int(min_images, max_images)
            # Ensure we don't ask for more unique images than available
            num_images = min(num_images, len(category_keys))
            if num_images == 0:
                continue

            selected = self.faker.random_elements(
                category_keys,
                length=num_images,
                unique=True,
            )
            for position, key in enumerate(selected, start=1):
                published = self._preprocess_one(key, seed_dir, thumbnail_service)
                if published is None:
                    continue
                ad_img = AdImage(
                    ad=ad,
                    image=key,
                    position=position,
                    thumbnail_small=published[ThumbnailSizeStrEnum.SMALL],
                    thumbnail_medium=published[ThumbnailSizeStrEnum.MEDIUM],
                    thumbnail_large=published[ThumbnailSizeStrEnum.LARGE],
                )
                ad_images.append(ad_img)

        return ad_images

    def _find_category_keys(
        self,
        ad: Ad,
        category_key_map: dict[str, list[str]],
    ) -> list[str]:
        """Find photo storage keys for an ad's category, with parent fallback.

        Walks up the category tree (via MPTT ``parent``) until a category with
        manifest photos is found. Falls back to the default pool as a last
        resort.

        Args:
            ad: The ad being processed.
            category_key_map: Mapping of category slug → photo storage keys.

        Returns:
            List of storage keys for the best-matching category, or the
            default pool / all available photos as a last-resort fallback.
        """
        # 1. Direct category match
        keys = category_key_map.get(ad.category.slug)
        if keys:
            return keys

        # 2. Walk up the MPTT tree
        node = ad.category.parent
        while node is not None:
            keys = category_key_map.get(node.slug)
            if keys:
                return keys
            node = node.parent

        # 3. Last resort: default pool, then ALL available photos as a
        #    safety net so no ad is ever left without images.
        return category_key_map.get("__default__", []) or self.all_image_keys

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
        manifest_entries: list[ManifestEntry],
        seed_dir: str,
        thumbnail_service: ThumbnailService,
    ) -> list[str]:
        """Pre-process all manifest photos: write originals, generate thumbnails.

        Deprecated eager bulk variant retained for compatibility; it delegates
        to ``_preprocess_one`` and shares the lazy path's verified-files
        contract — a key is returned only when every thumbnail variant has a
        file behind it on disk.

        Args:
            manifest_entries: List of manifest photo entries (each has 'filename').
            seed_dir: Target directory for seed images.
            thumbnail_service: ThumbnailService instance.

        Returns:
            List of storage keys (e.g., "seed/kvartiry_01.jpg") for all processed images.
        """
        keys: list[str] = []
        for entry in manifest_entries:
            storage_key = f"seed/{entry['filename']}"
            if self._preprocess_one(storage_key, seed_dir, thumbnail_service) is not None:
                keys.append(storage_key)
        return keys

    def _thumbnails_present(self, storage_key: str, seed_dir: str) -> bool:
        """True when every thumbnail variant for *storage_key* exists on disk.

        The size set is derived from ``ThumbnailSizeStrEnum`` — the same enum
        ``ThumbnailService`` iterates — so the fast-path gate and the service
        agree on the size set by construction (no hard-coded size list, no
        import of the backfill command's private ``_SIZE_COLUMNS``).
        """
        return all(
            os.path.exists(
                os.path.join(seed_dir, self._thumbnail_name(storage_key, size))
            )
            for size in ThumbnailSizeStrEnum
        )

    def _preprocess_one(
        self,
        storage_key: str,
        seed_dir: str,
        thumbnail_service: ThumbnailService,
    ) -> dict[ThumbnailSizeStrEnum, str] | None:
        """Pre-process a single seed photo on demand.

        Reads the fixture JPEG, writes the original to ``seed_dir``, and
        generates thumbnails. Returns a mapping of thumbnail size to storage
        key only when **every** variant has a file behind it on disk — the
        generator asserts what it wrote, not what it intended.

        When all three variants already exist the mapping is returned without
        calling the service (the extended cache check). Otherwise the missing
        variants are published with ``WriteMode.REPLACE`` (BLOCK 3's repair
        mode): ``CREATE_ONLY`` raises ``FileExistsError`` on the first present
        size (SMALL is first) and aborts the loop before reaching the missing
        one, whereas ``REPLACE`` writes all three deterministically.

        Args:
            storage_key: Original storage key, e.g. ``"seed/kvartiry_01.jpg"``.
            seed_dir: Target directory for seed images.
            thumbnail_service: ThumbnailService instance.

        Returns:
            Mapping from ``ThumbnailSizeStrEnum`` to storage key when every
            variant is present, otherwise ``None`` (missing fixture or a failed
            publish/post-condition).
        """
        filename = storage_key[5:] if storage_key.startswith("seed/") else storage_key
        fixture_path = FIXTURES_IMAGES_DIR / filename
        if not fixture_path.exists():
            logger.warning("Photo file not found: %s, skipping", fixture_path)
            return None

        original_path = os.path.join(seed_dir, filename)

        # Read JPEG bytes from fixture
        with open(fixture_path, "rb") as f:
            img_bytes = f.read()

        # Strip EXIF/metadata (incl. JPEG comment/XMP) before persist —
        # unifies the sanitization contract with the user-upload path.
        img_bytes = strip_photo_exif(img_bytes)

        # Write original image
        with open(original_path, "wb") as f:
            f.write(img_bytes)

        mapping = {
            size: self._thumbnail_key(storage_key, size.value)
            for size in ThumbnailSizeStrEnum
        }

        # Extended cache check: every variant present → nothing to write.
        if self._thumbnails_present(storage_key, seed_dir):
            return mapping

        # Repair path: publish the missing variants with REPLACE so the
        # present ones are rewritten byte-identically and the missing ones
        # are created. Never CREATE_ONLY here — it aborts on the first
        # present size (SMALL) and never reaches the missing one.
        published = thumbnail_service.generate_thumbnails(
            img_bytes, filename, mode=WriteMode.REPLACE
        )
        if set(published) != set(ThumbnailSizeStrEnum):
            logger.error("Thumbnail size set mismatch for %s", filename)
            return None

        # Post-condition: what the service reported must exist on disk.
        if not self._thumbnails_present(storage_key, seed_dir):
            logger.error("Thumbnails missing after publish for %s", filename)
            return None

        return mapping

    @staticmethod
    def _thumbnail_name(storage_key: str, size: ThumbnailSizeStrEnum) -> str:
        """Return the on-disk filename for a thumbnail variant."""
        filename = storage_key[5:] if storage_key.startswith("seed/") else storage_key
        stem, _ = os.path.splitext(filename)
        return f"{stem}-{size.value}.jpg"

    @staticmethod
    def _thumbnail_key(original_key: str, size: str) -> str:
        """Generate thumbnail key from original key and size suffix."""
        # original_key is like "seed/kvartiry_01.jpg"
        # extract filename part after seed/
        if original_key.startswith("seed/"):
            filename = original_key[5:]
        else:
            filename = original_key
        stem, _ = os.path.splitext(filename)
        return f"seed/{stem}-{size}.jpg"
