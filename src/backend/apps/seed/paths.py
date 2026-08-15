"""Canonical path constants for the seed app (Django-free).

These helpers intentionally avoid importing Django so they can be used both
from Django-loaded modules (e.g. ``generators.images``) and from the standalone
download script (``scripts/download_seed_photos.py``).

The single source of truth for every fixture path lives here. If you add a new
fixture file to ``apps/seed/fixtures/images/`` add its path constant here and
import it wherever it is consumed.
"""

from __future__ import annotations

from pathlib import Path

#: Root directory for seed photo fixtures (bundled JPEGs, manifests, state).
FIXTURES_IMAGES_DIR: Path = (
    Path(__file__).resolve().parent / "fixtures" / "images"
)

#: Per-category query definitions for the Unsplash/Pexels download script.
QUERY_HIERARCHY_PATH: Path = FIXTURES_IMAGES_DIR / "query_hierarchy.json"

#: Tracking previously-downloaded photo IDs (Unsplash/Pexels) to skip re-downloads.
DOWNLOADED_IDS_PATH: Path = FIXTURES_IMAGES_DIR / "downloaded_ids.json"

#: Mapping of category slug → list of photo filenames, consumed by ``ImageGenerator``.
MANIFEST_PATH: Path = FIXTURES_IMAGES_DIR / "photo_manifest.json"
