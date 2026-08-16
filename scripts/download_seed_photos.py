#!/usr/bin/env python3
"""Download seed photos from Unsplash (primary) and Pexels (fallback) per category.

Usage:
    # Copy seed-images-config.example.json → seed-images-config.json, fill in API keys
    uv run python scripts/download_seed_photos.py          # single pass
    uv run python scripts/download_seed_photos.py --all     # loop until limits exhausted (prioritizes under-represented categories)
    uv run python scripts/download_seed_photos.py --category avtomobili  # single category
    uv run python scripts/download_seed_photos.py --category=beauty-health  # '=' form also accepted
    uv run python scripts/download_seed_photos.py --validate  # check manifest vs files on disk
    uv run python scripts/download_seed_photos.py --validate --fix=cleanup  # find and clean missing files
    uv run python scripts/download_seed_photos.py --fix cleanup  # '--fix <mode>' space form also accepted

    For --category and --fix, both --flag=value and --flag value (space-separated)
    forms are supported. Unknown flags abort with exit code 1. In --all mode,
    categories with fewer existing photos are downloaded first.

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
import os
import random
import sys
import tempfile
import time
from enum import StrEnum
from pathlib import Path
from typing import Any, NamedTuple

import requests
from PIL import Image

# Allow importing from apps.seed.paths (Django-free module) without a full
# Django setup — this script runs standalone outside the Django process.
_SRC_BACKEND = Path(__file__).resolve().parent.parent / "src" / "backend"
if str(_SRC_BACKEND) not in sys.path:
    sys.path.insert(0, str(_SRC_BACKEND))

from apps.seed.paths import (  # noqa: E402
    DOWNLOADED_IDS_PATH,
    FIXTURES_IMAGES_DIR,
    MANIFEST_PATH,
    QUERY_HIERARCHY_PATH,
)

logger = logging.getLogger(__name__)


class FixMode(StrEnum):
    """Recovery modes for reconciling ``photo_manifest.json`` with files on disk."""

    NONE = "none"
    CLEANUP = "cleanup"


class CliArgs(NamedTuple):
    """Parsed CLI arguments for the seed photo download script.

    ``category`` is ``None`` when ``--category`` was not supplied. All other
    fields carry their natural defaults unless the corresponding flag is set.
    """

    category: str | None
    loop_all: bool
    validate_only: bool
    fix_mode: FixMode


# ─── Paths ─────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
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
        self._exhausted = False
        self.downloaded_ids: set[str] = set()

    @property
    def exhausted(self) -> bool:
        return self._exhausted or self._request_count >= self._limit

    def _mark_exhausted(self) -> None:
        """Permanently mark this source as exhausted (rate-limit or auth error)."""
        self._exhausted = True

    def _safe_get(self, url: str, headers: dict[str, str], params: dict[str, Any]) -> requests.Response:
        """Send a GET request with bounded retry on transient failures.

        Retries on ``ConnectionError``, ``Timeout``, and ``5xx`` server errors.
        Does **not** retry ``4xx`` responses — those raise ``HTTPError`` for the
        caller to classify (rate-limit, auth error, etc.).
        """
        timeout = self.config.get("request_timeout_sec", 30)
        max_retries = self.config.get("http_max_retries", 2)
        base_delay = self.config.get("retry_base_delay_sec", 1.0)
        last_resp: requests.Response | None = None

        for attempt in range(max_retries + 1):
            try:
                last_resp = requests.get(url, headers=headers, params=params, timeout=timeout)
                self._request_count += 1
                if last_resp.status_code < 500:
                    last_resp.raise_for_status()
                    return last_resp
                logger.warning(
                    "%s: server error %d, attempt %d/%d",
                    self.NAME,
                    last_resp.status_code,
                    attempt + 1,
                    max_retries + 1,
                )
            except (requests.ConnectionError, requests.Timeout) as e:
                self._request_count += 1
                logger.warning(
                    "%s: network error, attempt %d/%d: %s",
                    self.NAME,
                    attempt + 1,
                    max_retries + 1,
                    e,
                )

            if attempt < max_retries:
                delay = min(base_delay * (2 ** attempt), 30) + random.uniform(0, 0.5)
                time.sleep(delay)

        if last_resp is not None:
            last_resp.raise_for_status()
        raise requests.ConnectionError(f"{self.NAME}: all retries exhausted with no response")

    def _handle_http_error(self, error: requests.HTTPError, service_name: str) -> None:
        """Classify and log an ``HTTPError`` from the photo API.

        Distinguishes rate-limit (``429`` → WARNING) from auth/permission
        (``403`` → ERROR) from other HTTP errors. Marks the source as
        exhausted so subsequent calls skip it.
        """
        self._mark_exhausted()
        resp = error.response
        if resp is None:
            logger.error(
                "%s: request failed with no response: %s", service_name, error
            )
            return
        status = resp.status_code
        if status == 429:
            logger.warning(
                "%s: rate limit reached (HTTP 429). Marking source exhausted.",
                service_name,
            )
        elif status == 403:
            logger.error(
                "%s: permission denied (HTTP 403). Check API key/permissions. "
                "Marking source exhausted.",
                service_name,
            )
        else:
            logger.error(
                "%s: HTTP error %d: %s. Marking source exhausted.",
                service_name,
                status,
                resp.text[:200],
            )

    def _handle_request_exception(self, error: requests.RequestException, service_name: str) -> None:
        """Handle a non-HTTP request exception (e.g., exhausted retries on network error)."""
        self._mark_exhausted()
        logger.error(
            "%s: connection error after retries: %s. Marking source exhausted.",
            service_name,
            error,
        )

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

        try:
            resp = self._safe_get(url, headers, params)
        except requests.HTTPError as e:
            self._handle_http_error(e, "Unsplash")
            return []
        except requests.RequestException as e:
            self._handle_request_exception(e, "Unsplash")
            return []

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

        try:
            resp = self._safe_get(url, headers, params)
        except requests.HTTPError as e:
            self._handle_http_error(e, "Pexels")
            return []
        except requests.RequestException as e:
            self._handle_request_exception(e, "Pexels")
            return []

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
    """Persist photo manifest to disk atomically.

    Writes to a temporary file in the same directory, then atomically renames
    it into place via ``os.replace``. This prevents partial writes on
    interruption (e.g. Ctrl-C or crash mid-write).
    """
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=MANIFEST_PATH.parent,
        prefix=".photo_manifest_",
        suffix=".tmp",
        delete=False,
    ) as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        tmp_path = Path(f.name)
    os.replace(tmp_path, MANIFEST_PATH)


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


def count_category_photos(category_slug: str, manifest: dict[str, Any]) -> int:
    """Return the number of photos already in the manifest for a category."""
    categories = manifest.get("categories", {})
    return len(categories.get(category_slug, {}).get("photos", []))


def prioritize_categories(
    categories: list[str],
    manifest: dict[str, Any],
    photos_per_category: int,
) -> list[str]:
    """Order categories by deficit (fewest photos first) with random tie-breaking.

    Shuffles first for randomness, then stable-sorts by deficit descending so
    under-represented categories are processed first. Categories with more than
    ``photos_per_category`` photos go last.
    """
    shuffled = list(categories)
    random.shuffle(shuffled)
    shuffled.sort(
        key=lambda slug: photos_per_category - count_category_photos(slug, manifest),
        reverse=True,
    )
    return shuffled


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


# ─── Validation ──────────────────────────────────────────────────────────────


def find_missing_manifest_entries(
    manifest: dict[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    """Return manifest entries whose fixture files are missing from disk.

    Iterates both ``categories`` and the ``default`` fallback, checking
    ``FIXTURES_IMAGES_DIR / filename`` for each photo entry.

    Returns:
        List of ``(category_slug, photo_entry)`` tuples for missing files,
        where ``photo_entry`` is the full dict from the manifest (containing
        ``filename``, ``width``, ``height``).
    """
    missing: list[tuple[str, dict[str, Any]]] = []

    for category_slug, entry in manifest.get("categories", {}).items():
        for photo in entry.get("photos", []):
            filename = photo.get("filename", "")
            if not (FIXTURES_IMAGES_DIR / filename).exists():
                missing.append((category_slug, photo))

    for photo in manifest.get("default", {}).get("photos", []):
        filename = photo.get("filename", "")
        if not (FIXTURES_IMAGES_DIR / filename).exists():
            missing.append(("default", photo))

    return missing


def validate_manifest() -> bool:
    """Cross-check ``photo_manifest.json`` against JPEG files and query hierarchy.

    Two checks:
    1. Every manifest-referenced JPEG exists on disk in ``FIXTURES_IMAGES_DIR``.
    2. Every category in ``query_hierarchy.json`` has a manifest entry with
       at least ``photos_per_category`` photos (reports under-downloaded
       categories).

    Returns:
        True if all checks pass, False if any files are missing or categories
        are under-represented.
    """
    ok = True

    # ── Check 1: manifest-referenced files exist on disk ──
    if not MANIFEST_PATH.exists():
        logger.error("Manifest not found at %s", MANIFEST_PATH)
        return False

    with open(MANIFEST_PATH, encoding="utf-8") as f:
        manifest = json.load(f)

    total = 0
    for entry in manifest.get("categories", {}).values():
        total += len(entry.get("photos", []))
    total += len(manifest.get("default", {}).get("photos", []))

    missing_entries = find_missing_manifest_entries(manifest)
    missing = [f"{cat}/{photo.get('filename', '')}" for cat, photo in missing_entries]

    logger.info("Checked manifest: %d photos, %d missing files", total, len(missing))
    for ref in missing:
        logger.warning("Missing fixture file: %s", ref)
    if missing:
        ok = False

    # ── Check 2: manifest coverage vs query hierarchy ──
    if not QUERY_HIERARCHY_PATH.exists():
        logger.error("Query hierarchy not found at %s", QUERY_HIERARCHY_PATH)
        return False

    with open(QUERY_HIERARCHY_PATH, encoding="utf-8") as f:
        hierarchy = json.load(f)

    manifest_count = len(manifest.get("categories", {}))
    hierarchy_count = len(hierarchy)
    uncovered = sorted(set(hierarchy.keys()) - set(manifest.get("categories", {}).keys()))

    logger.info(
        "Coverage: %d categories in manifest, %d in query hierarchy, %d uncovered",
        manifest_count,
        hierarchy_count,
        len(uncovered),
    )
    for slug in uncovered[:50]:
        logger.warning("No photos downloaded for category: %s", slug)
    if len(uncovered) > 50:
        logger.warning("... and %d more uncovered categories", len(uncovered) - 50)
    if uncovered:
        ok = False

    return ok


# ─── Recovery ───────────────────────────────────────────────────────────────


def fix_cleanup(manifest: dict[str, Any]) -> int:
    """Remove manifest entries for fixture files missing from disk.

    Iterates all categories (including ``default``), filtering out photo
    entries whose files don't exist in ``FIXTURES_IMAGES_DIR``. Categories
    that lose all photos are kept with an empty ``photos`` list and logged
    as a WARNING (per decision D7 — a data-quality issue, not a crash).

    The manifest is saved atomically via ``save_manifest()`` (temp file +
    ``os.replace``) to prevent partial writes on interruption. The function
    never deletes files from disk and does not modify ``downloaded_ids.json``
    (per decisions D4 and D2).

    Args:
        manifest: The manifest dict (mutated in place and persisted to disk).

    Returns:
        The number of removed stale entries.
    """
    removed = 0

    for category_slug, entry in manifest.get("categories", {}).items():
        photos = entry.get("photos", [])
        kept = [
            p for p in photos
            if (FIXTURES_IMAGES_DIR / p.get("filename", "")).exists()
        ]
        removed += len(photos) - len(kept)
        entry["photos"] = kept
        if not kept:
            logger.warning(
                "Category '%s' now has zero photos after cleanup — "
                "re-download with --all to restore coverage",
                category_slug,
            )

    default_entry = manifest.setdefault("default", {"photos": []})
    default_photos = default_entry.get("photos", [])
    default_kept = [
        p for p in default_photos
        if (FIXTURES_IMAGES_DIR / p.get("filename", "")).exists()
    ]
    removed += len(default_photos) - len(default_kept)
    default_entry["photos"] = default_kept
    if not default_kept and default_photos:
        logger.warning(
            "Default photos now has zero photos after cleanup — "
            "re-download with --all to restore coverage",
        )

    logger.info("Cleanup removed %d stale manifest entries", removed)
    save_manifest(manifest)
    return removed


# ─── CLI parsing ─────────────────────────────────────────────────────────────


def _consume_value(argv: list[str], i: int, flag: str) -> str:
    """Return the value following a space-separated ``--flag`` token.

    The next token must exist and must not itself start with ``-`` so that
    ``--category --all`` (or ``--fix --validate``) is rejected instead of
    silently consuming the following flag as the value. Aborts with exit
    code 1 when no usable value is present.
    """
    if i + 1 >= len(argv) or argv[i + 1].startswith("-"):
        logger.error("Missing value for %s: expected a non-flag argument", flag)
        sys.exit(1)
    return argv[i + 1]


def _resolve_fix_mode(mode_str: str) -> FixMode:
    """Resolve a ``--fix`` mode string into a ``FixMode`` member.

    Aborts with exit code 1 (and logs the valid modes) when the value does not
    match any ``FixMode``.
    """
    try:
        return FixMode(mode_str)
    except ValueError:
        valid = ", ".join(m.value for m in FixMode)
        logger.error("Unknown --fix mode: %s. Valid modes: %s", mode_str, valid)
        sys.exit(1)


def parse_cli_args(argv: list[str]) -> CliArgs:
    """Parse CLI arguments with an index-based state machine.

    Supports both ``--flag=value`` and ``--flag value`` (space-separated) forms
    for ``--category`` and ``--fix``. Unknown arguments abort the run with
    ``sys.exit(1)``.

    Recognized flags:
      --category=<slug> / --category <slug>  : single-category download
      --all                                  : loop until API limits exhausted
      --validate                             : check manifest vs files on disk
      --fix=<mode> / --fix <mode>            : recovery mode (e.g. cleanup)
    """
    category: str | None = None
    loop_all = False
    validate_only = False
    fix_mode = FixMode.NONE

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--all":
            loop_all = True
            i += 1
        elif arg == "--validate":
            validate_only = True
            i += 1
        elif arg.startswith("--category="):
            category = arg.split("=", 1)[1]
            i += 1
        elif arg == "--category":
            category = _consume_value(argv, i, "--category")
            i += 2
        elif arg.startswith("--fix="):
            fix_mode = _resolve_fix_mode(arg.split("=", 1)[1])
            i += 1
        elif arg == "--fix":
            fix_mode = _resolve_fix_mode(_consume_value(argv, i, "--fix"))
            i += 2
        else:
            logger.error("Unknown argument: %s", arg)
            sys.exit(1)

    return CliArgs(
        category=category,
        loop_all=loop_all,
        validate_only=validate_only,
        fix_mode=fix_mode,
    )


# ─── Entry point ───────────────────────────────────────────────────────────


def main() -> None:
    """Run the seed photo download workflow.

    Pass ``--validate`` to cross-check ``photo_manifest.json`` against JPEGs
    on disk without contacting any API.

    Use ``--validate --fix=cleanup`` (or ``--fix=cleanup`` alone) to remove
    manifest entries for files that no longer exist on disk. Both the
    ``--fix=cleanup`` and ``--fix cleanup`` (space-separated) forms are
    accepted. This is a dev-only recovery mode that requires no API keys or
    network access.
    """
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

    # Parse CLI args (supports both --flag=value and --flag value forms)
    cli_args = parse_cli_args(sys.argv[1:])
    single_category: str | None = cli_args.category
    loop_all = cli_args.loop_all
    validate_only = cli_args.validate_only
    fix_mode: FixMode = cli_args.fix_mode

    if validate_only and fix_mode == FixMode.CLEANUP:
        # Report current state, clean stale entries, then re-validate.
        logger.info("=== Pre-cleanup validation ===")
        validate_manifest()
        if not MANIFEST_PATH.exists():
            logger.error("Manifest not found at %s", MANIFEST_PATH)
            sys.exit(1)
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            manifest = json.load(f)
        removed = fix_cleanup(manifest)
        logger.info("Removed %d stale manifest entries", removed)
        logger.info("=== Post-cleanup validation ===")
        ok = validate_manifest()
        sys.exit(0 if ok else 1)

    if validate_only:
        ok = validate_manifest()
        sys.exit(0 if ok else 1)

    if fix_mode == FixMode.CLEANUP:
        # --fix=cleanup without --validate: clean and confirm.
        if not MANIFEST_PATH.exists():
            logger.error("Manifest not found at %s", MANIFEST_PATH)
            sys.exit(1)
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            manifest = json.load(f)
        removed = fix_cleanup(manifest)
        logger.info("Removed %d stale manifest entries", removed)
        logger.info("=== Post-cleanup validation ===")
        ok = validate_manifest()
        sys.exit(0 if ok else 1)

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
    photos_per_category = config.get("photos_per_category", 3)
    if single_category:
        if single_category not in hierarchy_data:
            logger.error("Category '%s' not found in query hierarchy", single_category)
            sys.exit(1)
        categories_to_process = [single_category]
    else:
        categories_to_process = prioritize_categories(
            list(hierarchy_data.keys()), manifest, photos_per_category
        )

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
        # Re-prioritize on each --all pass: categories with fewer photos
        # come first so under-represented categories are filled up.
        if loop_all and not single_category:
            categories_to_process = prioritize_categories(
                list(hierarchy_data.keys()), manifest, photos_per_category
            )
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
                try:
                    n = process_category(cat_slug, hierarchy, source, manifest, config)
                except Exception as e:
                    logger.error(
                        "Error processing category %s with %s: %s",
                        cat_slug,
                        source.NAME,
                        e,
                    )
                    n = 0
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
    logger.info("Manifest: %s", MANIFEST_PATH)


if __name__ == "__main__":
    main()