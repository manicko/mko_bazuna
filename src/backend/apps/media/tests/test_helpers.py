"""
Shared test helpers for media tests.

These helpers factor out duplicated boilerplate that appeared across
``test_save_photo_exif.py`` and ``test_thumbnail_integration.py``: both modules
strip EXIF from JPEG bytes, write them to a ``staging/`` subdir, then return the
storage key. Centralising the logic avoids drift between the two call sites
(09-MEDIA-012).
"""

from __future__ import annotations

from pathlib import Path

from apps.media.services.filesystem import (
    STAGING_PREFIX,
    generate_storage_key,
    strip_photo_exif,
)


def make_test_jpeg(width: int = 800, height: int = 600, color=(64, 128, 192)) -> bytes:
    """Return minimal valid JPEG bytes for tests.

    Args:
        width: Image width in pixels.
        height: Image height in pixels.
        color: RGB tuple for the solid fill.

    Returns:
        JPEG-encoded image content as bytes.
    """
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (width, height), color=color).save(
        buffer, format="JPEG"
    )
    return buffer.getvalue()


def save_to_staging(
    media_root: Path, filename: str, photo_bytes: bytes
) -> str:
    """Strip EXIF, write to ``staging/`` under *media_root*, and return the key.

    Replicates the bot's inline ``save_photo`` flow: strip EXIF via
    :func:`strip_photo_exif`, then persist the cleaned bytes to the
    ``staging/`` subdir.  Used by tests that need a staging file on disk.

    Args:
        media_root: Absolute path to ``MEDIA_ROOT``.
        filename: The base filename (no ``staging/`` prefix) for the file.
        photo_bytes: Raw JPEG bytes (may contain EXIF).

    Returns:
        The staging storage key (``staging/<filename>``).
    """
    stripped = strip_photo_exif(photo_bytes)
    storage_key = f"{STAGING_PREFIX}{filename}"
    staging_path = media_root / storage_key
    staging_path.parent.mkdir(parents=True, exist_ok=True)
    staging_path.write_bytes(stripped)
    return storage_key


def save_and_read_back_staging(
    media_root: Path, photo_bytes: bytes
) -> tuple[str, bytes]:
    """Strip EXIF, write to ``staging/``, read back, and return both.

    A thinner variant of the old ``_save_and_thumbnail`` helper that does
    **not** run ``ThumbnailService`` — callers that need thumbnails should use
    :func:`save_to_staging` and then invoke ``ThumbnailService`` themselves.

    Args:
        media_root: Absolute path to ``MEDIA_ROOT``.
        photo_bytes: Raw JPEG bytes (may contain EXIF).

    Returns:
        ``(storage_key, on_disk_bytes)`` — the staging key and the bytes
        read back from disk.
    """
    storage_key = f"{STAGING_PREFIX}{generate_storage_key()}"
    stripped = strip_photo_exif(photo_bytes)
    staging_path = media_root / storage_key
    staging_path.parent.mkdir(parents=True, exist_ok=True)
    staging_path.write_bytes(stripped)

    on_disk_bytes = staging_path.read_bytes()
    return storage_key, on_disk_bytes


__all__ = [
    "make_test_jpeg",
    "save_to_staging",
    "save_and_read_back_staging",
]
