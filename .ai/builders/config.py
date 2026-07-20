"""Shared configuration for semantic map builders.

This module centralizes paths and detection rules used by both the Python
(`back/py_map.py`) and TypeScript (`front/ts_map.ts`) semantic map builders.

Path derivation is relative to this file so the whole ``.ai/builders``
directory can be copied into another project and reused without changes:

    .ai/builders/config.py      -> PROJECT_ROOT is three levels up
    .ai/builders/back/py_map.py -> Python source indexer
    .ai/builders/front/ts_map.ts-> TypeScript source indexer (optional)
"""

from __future__ import annotations

from pathlib import Path

# ----------------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent.parent  # .ai/builders -> .ai -> repo

SRC_ROOT = PROJECT_ROOT / "src"

OUTPUT_BACK = PROJECT_ROOT / ".ai" / "structure" / "back"
OUTPUT_FRONT = PROJECT_ROOT / ".ai" / "structure" / "front"

# TypeScript source root. Defaults to a conventional `frontend` directory.
# May be None on projects that have no TypeScript frontend.
TS_SRC_ROOT: Path | None = PROJECT_ROOT / "frontend"

# Where the TypeScript builder writes its JSON output.
TS_OUTPUT = PROJECT_ROOT / ".ai" / "structure" / "front"

# Gate the TypeScript builder. Set to True on projects that actually ship a
# TS frontend. Mko Bazuna uses Django templates (HTMX MPA) only, so this is
# False by default and ts_map.ts is never invoked.
ENABLE_TS = False

# ----------------------------------------------------------------------------
# Filtering
# ----------------------------------------------------------------------------

# File extensions excluded from scanning (binary artifacts and docs).
IGNORE_EXTENSIONS = {".pyc", ".pyo", ".pyd", ".md"}

# Directories always skipped, even when git is unavailable.
IGNORE_DIRS = {".venv", "node_modules", "__pycache__", ".git", "dist", "build"}

# ----------------------------------------------------------------------------
# Layer detection (order matters: first match wins)
# ----------------------------------------------------------------------------

# Each entry is (layer_name, marker). A marker is a substring that, when
# present in a POSIX-style file path, assigns that layer. Entries are tested
# top-to-bottom; the first match determines the layer.
LAYER_PATTERNS: list[tuple[str, str]] = [
    ("api", "/apps/api/"),
    ("handler", "/bot/handlers/"),
    ("state", "/bot/states/"),
    ("filter", "/bot/filters/"),
    ("service", "/services/"),
    ("model", "/models.py"),
    ("model", "/models/"),
    ("config", "/config/"),
]

DEFAULT_LAYER = "other"
