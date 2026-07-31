#!/usr/bin/env python3
"""Download seed photos from Unsplash (primary) and Pexels (fallback) per category.

Usage:
    # Copy seed-images-config.example.json → seed-images-config.json, fill in API keys
    uv run python scripts/download_seed_photos.py          # single pass
    uv run python scripts/download_seed_photos.py --all     # loop until limits exhausted
    uv run python scripts/download_seed_photos.py --category avtomobili  # single category

Workflow per category:
    1. Load query_hierarchy.json → get objects/contexts/styles for this category
    2. Compose random query: "{object} {context} {style}"
    3. Request random page (1–20) from API
    4. Pick random image not yet downloaded
    5. Download → compress → save to fixtures/images/{slug}_NN.jpg
    6. Update photo_manifest.json and downloaded_ids.json
    7. Stop when API rate limit reached or enough photos collected
"""

from __future__ import annotations

import io
import json
import logging
import random
import sys
import time
from pathlib import Path
from typing import Any

import requests
from PIL import Image

logger = logging.getLogger(__name__)

# ─── Paths ─────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
FIXTURES_IMAGES_DIR = PROJECT_ROOT / "src" / "backend" / "apps" / "seed" / "fixtures" / "images"
QUERY_HIERARCHY_PATH = FIXTURES_IMAGES_DIR / "query_hierarchy.json"
DOWNLOADED_IDS_PATH = FIXTURES_IMAGES_DIR / "downloaded_ids.json"
MANIFEST_PATH = FIXTURES_IMAGES_DIR / "photo_manifest.json"
CONFIG_PATH = SCRIPT_DIR / "seed-images-config.json"
CONFIG_EXAMPLE_PATH = SCRIPT_DIR / "seed-images-config.example.json"

# ─── Config loading ─────────────────────────────────────────────────────────


def load_config() -> dict[str, Any]:
    """Load seed-images-config.json with fallback to example defaults.

    The real config file (seed-images-config.json) is gitignored and holds
    API keys. If it doesn't exist, falls back to the example file which
    has empty keys — the user sees a clear error message.
    """
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)

    if CONFIG_EXAMPLE_PATH.exists():
        logger.warning(
            "Config not found at %s. "
            "Copy seed-images-config.example.json → seed-images-config.json "
            "and fill in your API keys.",
            CONFIG_PATH,
        )
        with open(CONFIG_EXAMPLE_PATH, encoding="utf-8") as f:
            return json.load(f)

    logger.error("No config file found. Create scripts/seed-images-config.json from the example.")
    return {}

# ─── API clients ───────────────────────────────────────────────────────────


class PhotoSource:
    """Base for photo API clients."""

    NAME: str = ""

    def __init__(self, api_key: str, config: dict[str, Any]) -> None:
        self.api_key = api_key
        self.config = config
        self._request_count = 0
        self._limit = 9999
        self.downloaded_ids: set[str] = set()

    @property
    def exhausted(self) -> bool:
        return self._request_count >= self._limit

    def search(self, query: str, per_page: int = 30, page: int = 1) -> list[dict[str, Any]]:
        """Search for photos and return list of photo metadata dicts."""
        raise NotImplementedError

    def download_url(self, photo: dict[str, Any]) -> str:
        """Extract download URL from photo metadata."""
        raise NotImplementedError

    def photo_id(self, photo: dict[str, Any]) -> str:
        """Extract unique ID from photo metadata."""
        raise NotImplementedError


class UnsplashClient(PhotoSource):
    """Unsplash API client (search endpoint, public authentication)."""

    NAME = "unsplash"

    def __init__(self, access_key: str, config: dict[str, Any]) -> None:
        super().__init__(access_key, config)
        self._limit = config.get("unsplash_safe_limit", 45)

    def search(self, query: str, per_page: int = 30, page: int = 1) -> list[dict[str, Any]]:
        if self.exhausted:
            logger.warning("Unsplash rate limit reached, skipping")
            return []

        url = "https://api.unsplash.com/search/photos"
        headers = {"Authorization": f"Client-ID {self.api_key}"}
        params = {"query": query, "per_page": min(per_page, 30), "page": page}

        resp = requests.get(url, headers=headers, params=params, timeout=self.config.get("request_timeout_sec", 30))
        self._request_count += 1
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", [])

    def download_url(self, photo: dict[str, Any]) -> str:
        # Use raw URL for highest quality (Unsplash compresses it server-side)
        urls = photo.get("urls", {})
        return urls.get("raw", urls.get("full", urls.get("regular", "")))

    def photo_id(self, photo: dict[str, Any]) -> str:
        return f"unsplash_{photo.get('id', '')}"


class PexelsClient(PhotoSource):
    """Pexels API client (search endpoint)."""

    NAME = "pexels"

    def __init__(self, api_key: str, config: dict[str, Any]) -> None:
        super().__init__(api_key, config)
        self._limit = config.get("pexels_safe_limit", 150)

    def search(self, query: str, per_page: int = 30, page: int = 1) -> list[dict[str, Any]]:
        if self.exhausted:
            logger.warning("Pexels rate limit reached, skipping")
            return []

        url = "https://api.pexels.com/v1/search"
        headers = {"Authorization": self.api_key}
        params = {"query": query, "per_page": min(per_page, 80), "page": page}

        resp = requests.get(url, headers=headers, params=params, timeout=self.config.get("request_timeout_sec", 30))
        self._request_count += 1
        resp.raise_for_status()
        data = resp.json()
        return data.get("photos", [])

    def download_url(self, photo: dict[str, Any]) -> str:
        # Pexels provides a 'src' dict with various sizes
        src = photo.get("src", {})
        return src.get("original", src.get("large2x", src.get("large", "")))

    def photo_id(self, photo: dict[str, Any]) -> str:
        return f"pexels_{photo.get('id', '')}"


# ─── Core logic ────────────────────────────────────────────────────────────


def load_downloaded_ids() -> set[str]:
    """Load set of already-downloaded photo IDs."""
    if not DOWNLOADED_IDS_PATH.exists():
        return set()
    with open(DOWNLOADED_IDS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return set(data.get("downloaded_ids", []))


def save_downloaded_ids(ids: set[str]) -> None:
    """Persist downloaded photo IDs to disk."""
    DOWNLOADED_IDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DOWNLOADED_IDS_PATH, "w", encoding="utf-8") as f:
        json.dump({"downloaded_ids": sorted(ids)}, f, indent=2)


def load_manifest() -> dict[str, Any]:
    """Load existing photo manifest."""
    if not MANIFEST_PATH.exists():
        return {"version": 1, "categories": {}, "default": {"photos": []}}
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_manifest(manifest: dict[str, Any]) -> None:
    """Persist photo manifest to disk."""
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)


def compose_query(hierarchy: dict[str, Any]) -> str:
    """Compose a random search query from a hierarchy entry.

    Combines random(object) + random(context) + random(style).
    Returns a lowercase, stripped query string.
    """
    obj = random.choice(hierarchy.get("objects", ["item"]))
    ctx = random.choice(hierarchy.get("contexts", [""]))
    style = random.choice(hierarchy.get("styles", [""]))
    parts = [obj, ctx, style]
    return " ".join(p.strip() for p in parts if p.strip()).lower()


def next_available_page(photo_source: PhotoSource, query: str) -> int:
    """Try random pages 1-20 and return the first page with unseen results.

    Makes up to 3 attempts to find a page with ≥1 unseen photo.
    """
    for _attempt in range(3):
        page = random.randint(1, 20)
        results = photo_source.search(query, page=page)
        unseen = [r for r in results if photo_source.photo_id(r) not in photo_source.downloaded_ids]
        if unseen:
            return page
    # Fallback: just return a random page
    return random.randint(1, 5)


def pick_photo(photo_source: PhotoSource, query: str) -> dict[str, Any] | None:
    """Search for a photo matching the query, skipping already-downloaded IDs.

    Returns photo metadata dict or None if nothing new found.
    """
    page = next_available_page(photo_source, query)
    results = photo_source.search(query, page=page)
    if not results:
        return None

    unseen = [r for r in results if photo_source.photo_id(r) not in photo_source.downloaded_ids]
    if not unseen:
        return None

    return random.choice(unseen)


def download_and_compress(
    photo_source: PhotoSource,
    photo: dict[str, Any],
    output_path: Path,
    config: dict[str, Any],
) -> bool:
    """Download a photo, compress it, and save as JPEG.

    Args:
        photo_source: The API client used.
        photo: Photo metadata dict from the API.
        output_path: Full path to save the JPEG.
        config: Full config dict (for max_image_size_bytes, jpeg_quality, etc.).

    Returns:
        True on success, False on failure.
    """
    timeout = config.get("request_timeout_sec", 30)
    max_size = config.get("max_image_size_bytes", 100_000)
    quality_start = config.get("jpeg_quality", 75)
    max_dim = config.get("max_dimension_px", 1080)

    url = photo_source.download_url(photo)
    if not url:
        logger.warning("No download URL for photo %s", photo_source.photo_id(photo))
        return False

    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning("Failed to download %s: %s", url, e)
        return False

    try:
        img = Image.open(io.BytesIO(resp.content))
    except Exception as e:
        logger.warning("Failed to open image: %s", e)
        return False

    # Convert to RGB if needed (RGBA, P-mode, etc.)
    if img.mode != "RGB":
        img = img.convert("RGB")

    # Resize if too large
    if img.width > max_dim or img.height > max_dim:
        ratio = min(max_dim / img.width, max_dim / img.height)
        new_size = (int(img.width * ratio), int(img.height * ratio))
        img = img.resize(new_size, Image.LANCZOS)

    # Progressive JPEG compression with size target
    quality = quality_start
    for _ in range(3):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
        size = buf.tell()
        if size <= max_size or quality <= 30:
            buf.seek(0)
            with open(output_path, "wb") as f:
                f.write(buf.read())
            return True
        quality -= 15

    # Final fallback at any quality
    img.save(output_path, format="JPEG", quality=quality, optimize=True, progressive=True)
    return True


def update_manifest_for_category(
    manifest: dict[str, Any],
    category_slug: str,
    filename: str,
    width: int,
    height: int,
) -> None:
    """Add a photo entry to the manifest for a given category."""
    categories = manifest.setdefault("categories", {})
    if category_slug not in categories:
        categories[category_slug] = {"photos": []}
    categories[category_slug]["photos"].append({
        "filename": filename,
        "width": width,
        "height": height,
    })
    logger.info("Added %s -> %s to manifest", category_slug, filename)


def get_next_sequence_number(category_slug: str, manifest: dict[str, Any]) -> int:
    """Determine the next sequence number for a category's photos."""
    categories = manifest.get("categories", {})
    cat_data = categories.get(category_slug, {})
    existing = cat_data.get("photos", [])
    # Extract highest number from existing filenames
    max_num = 0
    for entry in existing:
        fname = entry.get("filename", "")
        stem = Path(fname).stem
        # filename format: {slug}_NN.jpg
        parts = stem.split("_")
        if len(parts) >= 2:
            try:
                num = int(parts[-1])
                if num > max_num:
                    max_num = num
            except ValueError:
                continue
    return max_num + 1


def process_category(
    category_slug: str,
    hierarchy: dict[str, Any],
    photo_source: PhotoSource,
    manifest: dict[str, Any],
    config: dict[str, Any],
) -> int:
    """Download photos for a single category.

    Args:
        category_slug: The category identifier (e.g., 'kvartiry').
        hierarchy: Query hierarchy entry for this category.
        photo_source: API client instance.
        manifest: Photo manifest dict (mutated in place).
        config: Full config dict.

    Returns:
        Number of photos successfully downloaded.
    """
    photos_per_category = config.get("photos_per_category", 3)
    start_seq = get_next_sequence_number(category_slug, manifest)
    downloaded = 0
    attempts = 0
    max_attempts = photos_per_category * 5  # prevent infinite loops

    while downloaded < photos_per_category and attempts < max_attempts and not photo_source.exhausted:
        attempts += 1
        query = compose_query(hierarchy)

        logger.debug("[%s] query=%s attempt=%d/%d", category_slug, query, attempts, max_attempts)

        photo = pick_photo(photo_source, query)
        if photo is None:
            # No new photo found for this query, try a different query next time
            continue

        pid = photo_source.photo_id(photo)
        photo_source.downloaded_ids.add(pid)

        seq = start_seq + downloaded
        filename = f"{category_slug}_{seq:02d}.jpg"
        output_path = FIXTURES_IMAGES_DIR / filename

        if output_path.exists():
            logger.warning("File %s already exists, skipping", filename)
            downloaded += 1
            continue

        if not download_and_compress(photo_source, photo, output_path, config):
            continue

        # Get image dimensions for manifest
        try:
            with Image.open(output_path) as img:
                width, height = img.size
        except Exception:
            width, height = 0, 0

        update_manifest_for_category(manifest, category_slug, filename, width, height)
        downloaded += 1
        logger.info("[%s] downloaded %d/%d: %s", category_slug, downloaded, photos_per_category, filename)

        # Small delay to be polite to the API
        time.sleep(0.5)

    return downloaded


# ─── Entry point ───────────────────────────────────────────────────────────


def main() -> None:
    """Run the seed photo download workflow."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # Load config with API keys from seed-images-config.json
    config = load_config()
    unsplash_key: str = config.get("UNSPLASH_ACCESS_KEY", "")
    pexels_key: str = config.get("PEXELS_API_KEY", "")
    use_unsplash: bool = config.get("unsplash", True)
    use_pexels: bool = config.get("pexels", True)

    # Parse CLI args
    args = sys.argv[1:]
    single_category: str | None = None
    loop_all = False

    for arg in args:
        if arg.startswith("--category="):
            single_category = arg.split("=", 1)[1]
        elif arg == "--all":
            loop_all = True

    # Load query hierarchy
    if not QUERY_HIERARCHY_PATH.exists():
        logger.error("Query hierarchy not found at %s", QUERY_HIERARCHY_PATH)
        logger.error("Run the seed-content-generation LLM task first to create it.")
        sys.exit(1)

    with open(QUERY_HIERARCHY_PATH, encoding="utf-8") as f:
        hierarchy_data: dict[str, Any] = json.load(f)

    # Load state
    downloaded_ids = load_downloaded_ids()
    manifest = load_manifest()

    # Determine which categories to process
    if single_category:
        if single_category not in hierarchy_data:
            logger.error("Category '%s' not found in query hierarchy", single_category)
            sys.exit(1)
        categories_to_process = [single_category]
    else:
        categories_to_process = list(hierarchy_data.keys())
        random.shuffle(categories_to_process)

    # Determine photo source order
    photo_sources: list[PhotoSource] = []
    if use_unsplash and unsplash_key:
        photo_sources.append(UnsplashClient(unsplash_key, config))
    if use_pexels and pexels_key:
        photo_sources.append(PexelsClient(pexels_key, config))

    if not photo_sources:
        sources_enabled = []
        if not use_unsplash:
            sources_enabled.append("unsplash=disabled")
        elif not unsplash_key:
            sources_enabled.append("unsplash=no-key")
        if not use_pexels:
            sources_enabled.append("pexels=disabled")
        elif not pexels_key:
            sources_enabled.append("pexels=no-key")
        logger.error(
            "No photo sources configured (%s). "
            "Check seed-images-config.json.",
            ", ".join(sources_enabled),
        )
        sys.exit(1)

    # Main loop
    total_downloaded = 0
    pass_number = 0

    while True:
        pass_number += 1
        logger.info("=== Pass %d: %d categories to process ===", pass_number, len(categories_to_process))

        for cat_slug in categories_to_process:
            hierarchy = hierarchy_data.get(cat_slug, {})
            if not hierarchy:
                logger.warning("No hierarchy entry for %s, skipping", cat_slug)
                continue

            for source in photo_sources:
                if source.exhausted:
                    continue

                source.downloaded_ids = downloaded_ids
                n = process_category(cat_slug, hierarchy, source, manifest, config)
                if n > 0:
                    total_downloaded += n

            if total_downloaded > 0 and total_downloaded % 10 == 0:
                # Save progress periodically
                save_downloaded_ids(downloaded_ids)
                save_manifest(manifest)

        # Save after each pass
        save_downloaded_ids(downloaded_ids)
        save_manifest(manifest)
        logger.info("Pass %d complete. Total downloaded: %d", pass_number, total_downloaded)

        if not loop_all:
            break

        # Check if we exhausted all sources or have enough per category
        all_exhausted = all(s.exhausted for s in photo_sources)
        if all_exhausted:
            logger.info("All API rate limits reached. Stopping.")
            break

        # Brief pause between passes
        logger.info("Waiting 5 seconds before next pass...")
        time.sleep(5)

    logger.info("Done. Downloaded %d photos total.", total_downloaded)
    print(f"\nDownloaded {total_downloaded} photos. Manifest: {MANIFEST_PATH}")


if __name__ == "__main__":
    main()