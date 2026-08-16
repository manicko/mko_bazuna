"""
Media service unit tests — validation, storage-key generation, and file deletion (TST-007).

Verifies:
- ``validate_jpeg_bytes`` rejects invalid/empty/short payloads
- ``validate_photo`` rejects oversized files, oversized dimensions, non-JPEG
- ``generate_storage_key`` returns a UUID v4 + ``.jpg`` with no PII
- ``delete_photo`` swallows OSError subtypes and retries transient failures

No database interaction required — pure unit tests.
"""

import io
import logging
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PIL import Image

from telegram_bot.services.media import (
    DELETE_PHOTO_MAX_ATTEMPTS,
    delete_photo,
    generate_storage_key,
    validate_jpeg_bytes,
    validate_photo,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def valid_jpeg_bytes() -> bytes:
    """Generate a small valid JPEG image (~200x200)."""
    img = Image.new("RGB", (200, 200), color="green")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Test — validate_jpeg_bytes
# ---------------------------------------------------------------------------


class TestValidateJpegBytes:
    """validate_jpeg_bytes — JPEG magic-byte detection."""

    def test_valid_jpeg(self, valid_jpeg_bytes: bytes) -> None:
        """A valid JPEG returns True."""
        assert validate_jpeg_bytes(valid_jpeg_bytes) is True

    def test_invalid_format(self) -> None:
        """Non-JPEG bytes return False."""
        data = b"this is not a JPEG"
        assert validate_jpeg_bytes(data) is False

    def test_png_bytes(self) -> None:
        """PNG header (\x89PNG) returns False."""
        data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
        assert validate_jpeg_bytes(data) is False

    def test_gif_bytes(self) -> None:
        """GIF header returns False."""
        data = b"GIF89a" + b"\x00" * 20
        assert validate_jpeg_bytes(data) is False

    def test_empty_bytes(self) -> None:
        """Empty bytes return False."""
        assert validate_jpeg_bytes(b"") is False

    def test_short_bytes(self) -> None:
        """Fewer than 3 bytes return False."""
        assert validate_jpeg_bytes(b"\xff\xd8") is False


# ---------------------------------------------------------------------------
# Test — validate_photo
# ---------------------------------------------------------------------------


class TestValidatePhoto:
    """validate_photo — file-level and dimension validation."""

    def test_valid_photo(self, valid_jpeg_bytes: bytes) -> None:
        """A valid JPEG within limits returns (True, None)."""
        is_valid, error = validate_photo(valid_jpeg_bytes)
        assert is_valid is True
        assert error is None

    def test_oversize_file(self) -> None:
        """A JPEG larger than 2 MB returns an oversize error."""
        data = b"\xff\xd8\xff" + b"\x00" * (2 * 1024 * 1024 + 1)
        is_valid, error = validate_photo(data)
        assert is_valid is False
        assert error is not None
        assert "too large" in error.lower()

    def test_non_jpeg_format(self) -> None:
        """Non-JPEG payload returns an invalid-format error."""
        data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        is_valid, error = validate_photo(data)
        assert is_valid is False
        assert error is not None
        assert "format" in error.lower()

    def test_oversize_width(self) -> None:
        """An image wider than 2560 px returns a dimension error."""
        img = Image.new("RGB", (3000, 100), color="yellow")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        data = buf.getvalue()

        is_valid, error = validate_photo(data)
        assert is_valid is False
        assert error is not None
        assert "dimension" in error.lower()

    def test_oversize_height(self) -> None:
        """An image taller than 2560 px returns a dimension error."""
        img = Image.new("RGB", (100, 3000), color="cyan")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        data = buf.getvalue()

        is_valid, error = validate_photo(data)
        assert is_valid is False
        assert error is not None
        assert "dimension" in error.lower()

    def test_custom_max_dimensions(self) -> None:
        """Custom max_width/max_height parameters are respected."""
        img = Image.new("RGB", (800, 600), color="magenta")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        data = buf.getvalue()

        # Pass (600, 500) so height exceeds limit
        is_valid, error = validate_photo(data, max_width=600, max_height=500)
        assert is_valid is False
        assert error is not None
        assert "dimension" in error.lower()

    def test_corrupt_image_data(self) -> None:
        """Bytes that pass magic check but are not valid JPEG raise an error."""
        # Magic bytes prefix followed by garbage
        data = b"\xff\xd8\xff" + b"\x00" * 200
        is_valid, error = validate_photo(data)
        assert is_valid is False
        assert error is not None
        # The error raised by Pillow for corrupt data should be caught
        assert error == "Failed to process image."


# ---------------------------------------------------------------------------
# Test — generate_storage_key
# ---------------------------------------------------------------------------


class TestGenerateStorageKey:
    """generate_storage_key — UUID v4 + .jpg without PII."""

    UUID_V4_RE = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\.jpg$",
        re.IGNORECASE,
    )

    def test_ends_with_dot_jpg(self) -> None:
        """Storage key ends with .jpg."""
        key = generate_storage_key()
        assert key.endswith(".jpg")

    def test_uuid_v4_format(self) -> None:
        """Storage key matches UUID v4 format."""
        key = generate_storage_key()
        assert self.UUID_V4_RE.match(key) is not None

    def test_unique_keys(self) -> None:
        """Two calls return different storage keys."""
        key1 = generate_storage_key()
        key2 = generate_storage_key()
        assert key1 != key2

    def test_no_pii_in_key(self) -> None:
        """Storage key contains no personally identifiable information.

        The key should be strictly a UUID v4 + ``.jpg``, with no
        extra metadata or user identifiers embedded.
        """
        key = generate_storage_key()
        assert self.UUID_V4_RE.match(key) is not None
        # Strip the extension and ensure the UUID part matches UUID v4
        uuid_part = key[:-4]
        parts = uuid_part.split("-")
        assert len(parts) == 5
        # Version nibble at position 14 (0-indexed) must be '4'
        assert uuid_part[14] == "4"


# ---------------------------------------------------------------------------
# Test — delete_photo
# ---------------------------------------------------------------------------


class TestDeletePhoto:
    """delete_photo — file deletion with bounded retry on OSError."""

    @pytest.fixture(autouse=True)
    def _isolate_media_root(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Redirect MEDIA_ROOT to a temp dir and capture WARNING+ logs.

        Keeps these tests as pure unit tests: ``delete_photo`` only reads
        ``settings.MEDIA_ROOT`` (lazily evaluated), so swapping the module-level
        ``settings`` reference avoids any Django configuration dependency.
        """
        caplog.set_level(logging.WARNING)
        monkeypatch.setattr(
            "telegram_bot.services.media.settings",
            SimpleNamespace(MEDIA_ROOT=tmp_path),
        )

    def test_delete_photo_file_not_found_silent(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A missing file is swallowed with a warning; no exception escapes."""
        with patch(
            "telegram_bot.services.media.os.remove",
            side_effect=FileNotFoundError("no such file"),
        ) as mock_remove:
            delete_photo("missing.jpg")  # must not raise
        assert mock_remove.call_count == 1
        assert "already deleted" in caplog.text

    def test_delete_photo_file_not_found_does_not_retry(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """FileNotFoundError is terminal — os.remove called once, no retry."""
        with patch(
            "telegram_bot.services.media.os.remove",
            side_effect=FileNotFoundError("no such file"),
        ) as mock_remove, patch(
            "telegram_bot.services.media.time.sleep"
        ) as mock_sleep:
            delete_photo("missing.jpg")
        assert mock_remove.call_count == 1
        assert mock_sleep.call_count == 0
        assert "Retryable error" not in caplog.text

    def test_delete_photo_handles_os_error(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """PermissionError on every attempt: swallowed, error logged, no raise."""
        with patch(
            "telegram_bot.services.media.os.remove",
            side_effect=PermissionError("denied"),
        ) as mock_remove, patch("telegram_bot.services.media.time.sleep"):
            delete_photo("locked.jpg")  # must not raise
        assert mock_remove.call_count == DELETE_PHOTO_MAX_ATTEMPTS
        assert "Failed to delete" in caplog.text

    def test_delete_photo_retries_on_temporary_failure(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Transient OSError then success: retries succeed; warning logged."""
        with patch(
            "telegram_bot.services.media.os.remove",
            side_effect=[PermissionError("denied"), None],
        ) as mock_remove, patch(
            "telegram_bot.services.media.time.sleep"
        ) as mock_sleep:
            delete_photo("flaky.jpg")
        assert mock_remove.call_count == 2
        assert mock_sleep.call_count == 1
        assert "Retryable error" in caplog.text
