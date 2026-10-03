"""
Thumbnail generation service using Pillow.

Generates three size variants (SMALL, MEDIUM, LARGE) from uploaded photo bytes
with EXIF orientation correction, LANCZOS resampling, and **per-file atomic
publishing**.

Atomicity is claimed **per file**, not per call: every file that appears at a
final path is either absent or complete, never truncated.  A partial *set* of
thumbnails (some sizes present, others missing) is a detectable and repairable
state; a truncated file is not, because nothing can distinguish it from a good
one.  Honouring a set-level guarantee would require deleting already-published
files on a mid-set failure -- a strictly worse property (a deletion race
against a concurrent reader) that still would not hold across a crash between
two publishes.  This module deliberately does **not** claim crash durability:
no ``fsync`` of the temp file or its directory is performed, so a power loss
may lose a just-published file.  That gap is identical to the historical writer.
"""

from __future__ import annotations

import io
import os
import uuid
from typing import Final

from PIL import Image, ImageOps, UnidentifiedImageError

from apps.core.enums import ThumbnailSizeStrEnum, WriteMode

# Suffix for in-progress temp files.  A leading dot keeps them hidden on POSIX
# and, combined with the ``.tmp`` extension, guarantees a temp name never
# matches ``KEY_FORMAT_REGEX`` (which requires a ``.jpg`` suffix) or an
# ``AdImage`` key column -- so a leaked temp can never be mistaken for a real
# thumbnail.  Such a leaked temp is unreferenced and reclaimed by the hourly
# orphan sweep (or, under ``staging/``, by the 2 h staging TTL).
TEMP_SUFFIX: Final[str] = ".tmp"

# File mode for the temp file.  ``tempfile.mkstemp`` is deliberately NOT used:
# it creates the file ``0o600``, and after a hard link / rename the published
# file would inherit that mode.  nginx serves ``/media/`` as a different uid
# from the app, so a ``0o600`` file would 403 every image on the site.
# ``0o666`` subject to umask reproduces the historical ``os.open`` behaviour
# exactly (observed ``0o755`` in this project's container).
TEMP_FILE_MODE: Final[int] = 0o666


class ThumbnailService:
    """Service for generating thumbnail image variants from uploaded photos."""

    QUALITY = 85
    FORMAT = "JPEG"
    RESAMPLING = Image.Resampling.LANCZOS
    PROGRESSIVE = True
    SIZES: dict[ThumbnailSizeStrEnum, tuple[int, int]] = {
        ThumbnailSizeStrEnum.SMALL: (240, 180),
        ThumbnailSizeStrEnum.MEDIUM: (640, 480),
        ThumbnailSizeStrEnum.LARGE: (1280, 960),
    }

    def __init__(self, storage_dir: str) -> None:
        """Initialize with the target directory for thumbnail file output.

        Args:
            storage_dir: Absolute path to the directory where thumbnail
                files will be written.
        """
        self.storage_dir = storage_dir

    def generate_thumbnails(
        self,
        photo_bytes: bytes,
        original_key: str,
        *,
        mode: WriteMode = WriteMode.CREATE_ONLY,
    ) -> dict[ThumbnailSizeStrEnum, str]:
        """Generate all thumbnail variants from raw photo bytes.

        Corrects EXIF orientation, resizes to each configured size while
        preserving aspect ratio, and publishes each variant to ``storage_dir``
        atomically (per file).  The temp file is written in the destination
        directory and then either hard-linked (``CREATE_ONLY``) or renamed
        (``REPLACE``) onto the final path.

        Args:
            photo_bytes: Raw image file content as bytes.
            original_key: Original storage key (e.g. ``"<uuid>.jpg"``).
            mode: Publication semantics.  ``CREATE_ONLY`` (default) refuses to
                overwrite an existing thumbnail; ``REPLACE`` overwrites, for
                repair callers.

        Returns:
            Mapping from thumbnail size enum to generated storage key
            (e.g. ``"<uuid>-small.jpg"``).

        Raises:
            ValueError: If the provided bytes cannot be decoded as an image.
            FileExistsError: If a thumbnail file already exists at the
                target path and ``mode`` is ``CREATE_ONLY``.
        """
        stem, _ = os.path.splitext(original_key)

        try:
            image = Image.open(io.BytesIO(photo_bytes))
        except UnidentifiedImageError:
            raise ValueError("Provided bytes cannot be decoded as an image.") from None
        corrected = ImageOps.exif_transpose(image)
        if corrected is None:
            corrected = image
        image = corrected.convert("RGB")

        thumbnails: dict[ThumbnailSizeStrEnum, str] = {}

        for size_enum, dimensions in self.SIZES.items():
            key = f"{stem}-{size_enum.value}.jpg"
            thumbnails[size_enum] = key
            target_path = os.path.join(self.storage_dir, key)

            resized = image.copy()
            resized.thumbnail(dimensions, self.RESAMPLING)

            buffer = io.BytesIO()
            resized.save(
                buffer,
                format=self.FORMAT,
                quality=self.QUALITY,
                progressive=self.PROGRESSIVE,
            )
            buffer.seek(0)

            self._publish(buffer.getvalue(), target_path, mode)

        return thumbnails

    @staticmethod
    def _publish(content: bytes, target_path: str, mode: WriteMode) -> None:
        """Atomically publish ``content`` at ``target_path``.

        Writes ``content`` to a unique temp file in the **destination
        directory** (a cross-device move would degrade to a non-atomic copy),
        then publishes it:

        - ``CREATE_ONLY``: ``os.link`` the temp onto the target.  POSIX
          ``link(2)`` creates the new link **atomically** and raises ``EEXIST``
          if the target exists, which Python maps to ``FileExistsError`` -- so
          the create-or-fail contract and atomicity are both preserved with no
          TOCTOU window.  The temp is unlinked in a ``finally``.
        - ``REPLACE``: ``os.replace`` the temp onto the target, consuming the
          temp.  Python documents that an existing destination file is
          "replaced silently", which is exactly the repair intent.

        The temp file never survives a successful or a failed call.  A
        ``SIGKILL`` between temp creation and publication can still leave one
        temp behind; it is unreferenced and reclaimed by the existing sweep.

        Args:
            content: Complete file content to publish.
            target_path: Final path of the published file.
            mode: ``CREATE_ONLY`` or ``REPLACE``.
        """
        target_dir = os.path.dirname(target_path)
        temp_path = os.path.join(
            target_dir,
            f".{os.path.basename(target_path)}.{uuid.uuid4().hex}{TEMP_SUFFIX}",
        )

        fd = os.open(
            temp_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            TEMP_FILE_MODE,
        )
        try:
            os.write(fd, content)
        finally:
            os.close(fd)

        try:
            if mode is WriteMode.REPLACE:
                os.replace(temp_path, target_path)
            else:
                os.link(temp_path, target_path)
        finally:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
