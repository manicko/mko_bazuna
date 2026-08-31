"""
Media service for Telegram bot photo handling.

Validates photos and generates storage keys per spec.
"""

import io
import logging
import time
import uuid

from PIL import Image, ImageOps
import os
from django.conf import settings

logger = logging.getLogger(__name__)


# JPEG magic bytes for validation
JPEG_MAGIC_BYTES = [b"\xff\xd8\xff"]


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
                return


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
    buf = io.BytesIO()
    img.save(buf, format="JPEG", optimize=True)
    return buf.getvalue()
