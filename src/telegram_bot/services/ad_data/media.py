"""Media I/O helpers for the Telegram bot ad-creation service.

Handles bounded photo download from Telegram and atomic staging-file writes
to the filesystem (bot -> backend direction).
"""

import asyncio
import io
import logging
import os

from aiogram import Bot
from django.conf import settings

from apps.media.services.filesystem import (
    STAGING_PREFIX,
    generate_storage_key,
    strip_photo_exif,
)

logger = logging.getLogger(__name__)

__all__ = [
    "download_photo",
    "save_photo",
]


# Byte cap for the bounded download writer. Must match
# ``handlers.ad_create.MAX_PHOTO_BYTES`` (2 MB). Defined locally rather than
# imported to avoid a circular import (ad_data.media is imported by photos.py,
# which already imports MAX_PHOTO_BYTES from handlers.ad_create). The +1 makes
# the writer reject any payload that reaches the cap exactly.
_PHOTO_DOWNLOAD_CAP = 2 * 1024 * 1024 + 1


class _DownloadTooLarge(Exception):
    """Raised when a Telegram download exceeds the photo byte cap."""


class _BoundedBytesWriter:
    """Bounds the total bytes written through it.

    Passed as aiogram's ``destination`` so that its per-chunk
    ``write(chunk)`` calls abort as soon as the cap is crossed, never
    buffering the full payload in memory. Composes an ``io.BytesIO`` and
    delegates the file-like methods aiogram's downloader calls (``write``,
    ``flush``, ``seek``, ``getvalue``).
    """

    def __init__(self, cap: int) -> None:
        self._cap = cap
        self._buffer = io.BytesIO()

    def write(self, data: bytes) -> int:
        if self._buffer.tell() + len(data) > self._cap:
            raise _DownloadTooLarge
        return self._buffer.write(data)

    def flush(self) -> None:
        self._buffer.flush()

    def seek(self, offset: int, whence: int = 0) -> int:
        return self._buffer.seek(offset, whence)

    def getvalue(self) -> bytes:
        return self._buffer.getvalue()


async def download_photo(file_id: str, bot: Bot) -> bytes | None:
    """Download photo bytes from Telegram.

    Uses a bounded ``_BoundedBytesWriter`` as aiogram's download destination
    so that an oversized file (e.g. when Telegram omits ``file_size``) aborts
    as soon as the cap is exceeded instead of buffering the entire payload in
    memory (MED-002).
    """
    try:
        writer = _BoundedBytesWriter(_PHOTO_DOWNLOAD_CAP)
        file = await bot.download(file_id, destination=writer)
        return file.getvalue() if file is not None else None
    except _DownloadTooLarge:
        logger.warning("Photo download %s exceeded byte cap; rejected", file_id)
        return None
    except Exception as e:
        logger.error("Failed to download photo %s: %s", file_id, e)
        return None


async def save_photo(storage_key: str, photo_bytes: bytes) -> str:
    """Save photo to filesystem via thread executor to avoid blocking the event loop.

    Strips EXIF/metadata and re-encodes the image before persisting to disk.

    Files are written to the ``staging/`` subdirectory of ``MEDIA_ROOT`` so
    that in-flight uploads are protected from the orphan sweep.  The returned
    key carries the ``staging/`` prefix and is promoted to permanent storage
    by ``submit_ad`` before AdImage rows are created.

    Uses ``os.open`` with ``O_CREAT|O_EXCL`` to guarantee atomic writes; on
    ``FileExistsError`` regenerates the storage key and retries.

    Returns:
        The final storage key used (may differ from the input on collision).
        The key carries the ``staging/`` prefix — ``submit_ad`` promotes it to
        permanent storage before creating AdImage rows.
    """

    def _write(path: str, data: bytes) -> None:
        cleaned = strip_photo_exif(data)

        os.makedirs(os.path.dirname(path), exist_ok=True)

        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)

        try:
            os.write(fd, cleaned)
        finally:
            os.close(fd)

    key = storage_key

    while True:
        staging_key = f"{STAGING_PREFIX}{key}"
        media_path = os.path.join(settings.MEDIA_ROOT, staging_key)

        try:
            await asyncio.to_thread(_write, media_path, photo_bytes)

            return staging_key

        except FileExistsError:
            logger.warning("Storage key collision: %s, regenerating", key)

            key = generate_storage_key()
