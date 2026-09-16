"""
Media filesystem utilities for image validation and storage.

Validates photos and generates storage keys per spec.
"""

import errno
import io
import logging
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from django.conf import settings
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)


# JPEG magic bytes for validation
JPEG_MAGIC_BYTES = [b"\xff\xd8\xff"]

# Shared storage-key format validator.
# Matches: <two-alnum><alnum-or-._->* optionally followed by
# (/<two-alnum><alnum-or-._->*)* then .jpg
# Examples: "abc12345-...-uuid.jpg", "seed/kvartiry_01.jpg",
# "seed/kvartiry_01-small.jpg", "<uuid>-small.jpg",
# "staging/<uuid>.jpg", "staging/<uuid>-small.jpg"
KEY_FORMAT_REGEX = (
    r"^[A-Za-z0-9][A-Za-z0-9][A-Za-z0-9._-]*"
    r"(/[A-Za-z0-9][A-Za-z0-9._-]*)*\.jpg$"
)

# Staging subdirectory for in-flight uploads. Files live here between upload
# and ad submission, protected from the orphan sweep by TTL reclamation.
STAGING_SUBDIR = "staging"
STAGING_PREFIX = f"{STAGING_SUBDIR}/"


def move_staging_to_permanent(photos: list[dict[str, Any]]) -> None:
    """Promote in-flight staging files to permanent MEDIA_ROOT storage.

    Iterates every key field on each photo dict (``storage_key`` and all
    ``thumbnail_*`` variants), strips the ``staging/`` prefix, and atomically
    renames the file from ``staging/<key>`` to ``<key>``.  Keys that do not
    carry the staging prefix (e.g. seed data or test fixtures that write
    directly to permanent storage) are left untouched.

    Uses ``os.replace`` (atomic on the same filesystem) with a
    ``shutil.move`` fallback for the ``EXDEV`` cross-filesystem edge case.

    The caller is responsible for running this *before* any
    ``transaction.atomic()`` block so that a DB rollback leaves the permanent
    files as unreferenced orphans (reclaimed by the normal orphan sweep)
    rather than re-desynchronising the filesystem and database.

    Args:
        photos: List of photo dicts (as built by the FSM ``process_photos``
            handler).  Modified **in place** — each staging key is replaced
            with its permanent counterpart.
    """
    key_fields = ("storage_key", "thumbnail_small", "thumbnail_medium", "thumbnail_large")
    for photo in photos:
        for field in key_fields:
            key = photo.get(field)
            if not key or not key.startswith(STAGING_PREFIX):
                continue
            permanent_key = key.removeprefix(STAGING_PREFIX)
            staging_path = os.path.join(settings.MEDIA_ROOT, key)
            permanent_path = os.path.join(settings.MEDIA_ROOT, permanent_key)
            if os.path.exists(staging_path):
                try:
                    os.replace(staging_path, permanent_path)
                except OSError as exc:
                    if exc.errno == errno.EXDEV:
                        shutil.move(staging_path, permanent_path)
                    else:
                        raise
            photo[field] = permanent_key


def assert_storage_key_contained(storage_key: str) -> None:
    """Validate that *storage_key* is a safe relative path within MEDIA_ROOT.

    Rejects NUL bytes, absolute paths (leading ``/``), and parent-directory
    (``..``) segments, then canonicalises both MEDIA_ROOT and the resolved
    file path and asserts containment as a final defence-in-depth measure.

    Raises:
        ValueError: if *storage_key* violates any containment rule.  This is
            a data-integrity / security error — it is **not** an
            ``OSError`` and is allowed to propagate so sweep/cron operators
            surface poisoning rather than silently operating outside
            MEDIA_ROOT.
    """
    if "\x00" in storage_key:
        raise ValueError(f"Storage key contains NUL byte: {storage_key!r}")

    if storage_key.startswith("/"):
        raise ValueError(f"Storage key must be relative, not absolute: {storage_key!r}")

    if ".." in Path(storage_key).parts:
        raise ValueError(
            f"Storage key contains parent-directory segment: {storage_key!r}"
        )

    real_media_root = os.path.realpath(str(settings.MEDIA_ROOT))
    real_path = os.path.realpath(os.path.join(str(settings.MEDIA_ROOT), storage_key))

    if real_path != real_media_root and not real_path.startswith(
        real_media_root + os.sep
    ):
        raise ValueError(f"Storage key resolves outside MEDIA_ROOT: {storage_key!r}")


def validate_jpeg_bytes(data: bytes) -> bool:
    """Validate that bytes represent a valid JPEG image by magic bytes."""
    if len(data) < 3:
        return False
    return any(data.startswith(magic) for magic in JPEG_MAGIC_BYTES)


def validate_photo(
    photo_bytes: bytes, max_width: int = 2560, max_height: int = 2560
) -> tuple[bool, str | None]:
    """
    Validate a photo meets requirements.

    Returns (is_valid, error_message) tuple.
    - JPEG format validation
    - Dimensions check (max 2560px)
    - Size check (~2MB max)

    Args:
        photo_bytes: Raw photo bytes from Telegram
        max_width: Maximum width in pixels
        max_height: Maximum height in pixels

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check magic bytes
    if not validate_jpeg_bytes(photo_bytes):
        return False, "Invalid image format. Only JPEG photos are accepted."

    # Check approximate size (~2MB max)
    if len(photo_bytes) > 2 * 1024 * 1024:
        return False, "Photo too large. Maximum size is approximately 2MB."

    try:
        # Validate dimensions using PIL
        img = Image.open(io.BytesIO(photo_bytes))
        # Apply exif_transpose to correct orientation before dimension check
        img = ImageOps.exif_transpose(img)
        width, height = img.size

        if width > max_width or height > max_height:
            return (
                False,
                f"Photo too large. Maximum dimensions: {max_width}x{max_height} pixels.",
            )
    except Exception as e:
        logger.warning(f"Failed to open image for validation: {e}")
        return False, "Failed to process image."

    return True, None


def generate_storage_key() -> str:
    """Generate a UUID v4 storage key for anonymity."""
    return f"{uuid.uuid4()}.jpg"


DELETE_PHOTO_MAX_ATTEMPTS = 3
DELETE_PHOTO_BASE_DELAY = 0.1


def delete_photo(storage_key: str) -> None:
    """
    Delete a photo file from the media storage.

    Removes the file at ``os.path.join(settings.MEDIA_ROOT, storage_key)``.
    Succeeds silently if the file does not exist.

    Transient ``OSError`` subtypes (e.g. ``PermissionError``) are retried with
    exponential backoff. ``FileNotFoundError`` is terminal — it means the file
    is already gone and retrying would not help. After the final attempt all
    failures are logged and swallowed so that sweep/cron jobs are never
    aborted by an orphaned file.

    Args:
        storage_key: Relative storage key (e.g. ``"<uuid>.jpg"``).
    """
    assert_storage_key_contained(storage_key)
    path = os.path.join(settings.MEDIA_ROOT, storage_key)
    for attempt in range(DELETE_PHOTO_MAX_ATTEMPTS):
        try:
            os.remove(path)
            logger.info(f"Deleted photo: {storage_key}")
            return
        except FileNotFoundError:
            logger.warning(f"Photo not found (already deleted): {storage_key}")
            return
        except OSError as exc:
            if attempt < DELETE_PHOTO_MAX_ATTEMPTS - 1:
                delay = DELETE_PHOTO_BASE_DELAY * (2**attempt)
                logger.warning(
                    f"Retryable error deleting photo {storage_key} "
                    f"(attempt {attempt + 1}/{DELETE_PHOTO_MAX_ATTEMPTS}): {exc}"
                )
                time.sleep(delay)
            else:
                logger.error(
                    f"Failed to delete photo {storage_key} after "
                    f"{DELETE_PHOTO_MAX_ATTEMPTS} attempts: {exc}"
                )
                _record_deletion_error(storage_key, exc)
                return


def _record_deletion_error(storage_key: str, exc: OSError) -> None:
    """Best-effort persistence of a deletion failure for escalation (ME-003).

    Wrapped in try/except so it **never** raises — ``delete_photo`` must
    preserve its "never raise" contract so that sweep/cron jobs are never
    aborted by an orphaned file or a downstream DB write failure.
    """
    try:
        from apps.media.models import MediaDeletionError

        MediaDeletionError.objects.create(
            storage_key=storage_key,
            error_type=type(exc).__name__,
            error_message=str(exc)[:1000],
            attempts=DELETE_PHOTO_MAX_ATTEMPTS,
        )
    except Exception:
        logger.exception("Failed to persist MediaDeletionError for %s", storage_key)


def strip_photo_exif(photo_bytes: bytes) -> bytes:
    """
    Strip EXIF/metadata from a JPEG photo and re-encode it.

    Applies exif_transpose to correct orientation, removes EXIF data,
    and saves with optimize=True. This also hardens against malicious JPEGs.

    Args:
        photo_bytes: Raw JPEG bytes

    Returns:
        Cleaned JPEG bytes with no EXIF metadata
    """
    img = Image.open(io.BytesIO(photo_bytes))
    img = ImageOps.exif_transpose(img)
    img.info.pop("exif", None)
    img.info.pop("icc_profile", None)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", optimize=True)
    return buf.getvalue()
