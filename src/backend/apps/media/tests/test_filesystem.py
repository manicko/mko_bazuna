"""
Media service unit tests — validation, storage-key generation, and file deletion (TST-007).

Verifies:
- ``validate_jpeg_bytes`` rejects invalid/empty/short payloads
- ``validate_photo`` rejects oversized files, oversized dimensions, non-JPEG
- ``generate_storage_key`` returns a UUID v4 + ``.jpg`` with no PII
- ``delete_photo`` swallows OSError subtypes and retries transient failures

No database interaction required — pure unit tests.
"""

import errno
import io
import logging
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PIL import Image

from apps.media.services.filesystem import (
    DELETE_PHOTO_MAX_ATTEMPTS,
    assert_storage_key_contained,
    delete_photo,
    generate_storage_key,
    move_staging_to_permanent,
    strip_photo_exif,
    validate_jpeg_bytes,
    validate_photo,
)

pytestmark = [pytest.mark.unit]


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
            "apps.media.services.filesystem.settings",
            SimpleNamespace(MEDIA_ROOT=tmp_path),
        )

    def test_delete_photo_file_not_found_silent(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A missing file is swallowed with a warning; no exception escapes."""
        with patch(
            "apps.media.services.filesystem.os.remove",
            side_effect=FileNotFoundError("no such file"),
        ) as mock_remove:
            delete_photo("missing.jpg")  # must not raise
        assert mock_remove.call_count == 1
        assert "already deleted" in caplog.text

    def test_delete_photo_file_not_found_does_not_retry(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """FileNotFoundError is terminal — os.remove called once, no retry."""
        with (
            patch(
                "apps.media.services.filesystem.os.remove",
                side_effect=FileNotFoundError("no such file"),
            ) as mock_remove,
            patch("apps.media.services.filesystem.time.sleep") as mock_sleep,
        ):
            delete_photo("missing.jpg")
        assert mock_remove.call_count == 1
        assert mock_sleep.call_count == 0
        assert "Retryable error" not in caplog.text

    def test_delete_photo_handles_os_error(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """PermissionError on every attempt: swallowed, error logged, no raise."""
        with (
            patch(
                "apps.media.services.filesystem.os.remove",
                side_effect=PermissionError("denied"),
            ) as mock_remove,
            patch("apps.media.services.filesystem.time.sleep"),
        ):
            delete_photo("locked.jpg")  # must not raise
        assert mock_remove.call_count == DELETE_PHOTO_MAX_ATTEMPTS
        assert "Failed to delete" in caplog.text

    def test_delete_photo_retries_on_temporary_failure(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Transient OSError then success: retries succeed; warning logged."""
        with (
            patch(
                "apps.media.services.filesystem.os.remove",
                side_effect=[PermissionError("denied"), None],
            ) as mock_remove,
            patch("apps.media.services.filesystem.time.sleep") as mock_sleep,
        ):
            delete_photo("flaky.jpg")
        assert mock_remove.call_count == 2
        assert mock_sleep.call_count == 1
        assert "Retryable error" in caplog.text

    @pytest.mark.django_db
    def test_delete_photo_logs_media_deletion_error_on_retry_exhaustion(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When retries are exhausted, a MediaDeletionError row is persisted (ME-003).

        The DB write is best-effort: even if the DB write is blocked (e.g.
        no django_db marker), delete_photo must never raise.
        """
        from apps.media.models import MediaDeletionError

        with (
            patch(
                "apps.media.services.filesystem.os.remove",
                side_effect=PermissionError("denied"),
            ) as mock_remove,
            patch("apps.media.services.filesystem.time.sleep"),
        ):
            delete_photo("locked.jpg")  # must not raise

        assert mock_remove.call_count == DELETE_PHOTO_MAX_ATTEMPTS
        assert "Failed to delete" in caplog.text

        error = MediaDeletionError.objects.get()
        assert error.storage_key == "locked.jpg"
        assert error.error_type == "PermissionError"
        assert error.attempts == DELETE_PHOTO_MAX_ATTEMPTS


# ---------------------------------------------------------------------------
# Test — strip_photo_exif
# ---------------------------------------------------------------------------


class TestStripPhotoExif:
    """``strip_photo_exif`` — EXIF/ICC profile removal and JPEG re-encoding."""

    def test_strips_exif_data(self) -> None:
        """EXIF metadata is removed from the output."""
        img = Image.new("RGB", (200, 200), color="red")
        exif = Image.Exif()
        exif[270] = "Test description"  # ImageDescription
        exif[271] = "Test make"  # Make
        buf = io.BytesIO()
        img.save(buf, format="JPEG", exif=exif.tobytes())
        jpeg_with_exif = buf.getvalue()

        # Verify EXIF is present before stripping
        original_img = Image.open(io.BytesIO(jpeg_with_exif))
        assert len(original_img.getexif()) > 0

        cleaned = strip_photo_exif(jpeg_with_exif)
        cleaned_img = Image.open(io.BytesIO(cleaned))
        assert len(cleaned_img.getexif()) == 0
        assert "exif" not in cleaned_img.info

    def test_strips_icc_profile(self) -> None:
        """ICC profile is removed from the output."""
        img = Image.new("RGB", (100, 100), color="blue")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", icc_profile=b"fake-icc-profile-data")
        jpeg_with_icc = buf.getvalue()

        cleaned = strip_photo_exif(jpeg_with_icc)
        cleaned_img = Image.open(io.BytesIO(cleaned))
        assert "icc_profile" not in cleaned_img.info

    def test_strips_both_exif_and_icc(self) -> None:
        """Both EXIF and ICC profile are stripped simultaneously."""
        img = Image.new("RGB", (150, 150), color="green")
        exif = Image.Exif()
        exif[270] = "Test description"
        buf = io.BytesIO()
        img.save(
            buf,
            format="JPEG",
            exif=exif.tobytes(),
            icc_profile=b"fake-icc-profile",
        )
        jpeg_with_exif_and_icc = buf.getvalue()

        cleaned = strip_photo_exif(jpeg_with_exif_and_icc)
        cleaned_img = Image.open(io.BytesIO(cleaned))
        assert len(cleaned_img.getexif()) == 0
        assert "icc_profile" not in cleaned_img.info

    def test_output_is_valid_jpeg(self, valid_jpeg_bytes: bytes) -> None:
        """Output passes JPEG magic-byte validation."""
        cleaned = strip_photo_exif(valid_jpeg_bytes)
        assert validate_jpeg_bytes(cleaned) is True

    def test_preserves_image_dimensions(self, valid_jpeg_bytes: bytes) -> None:
        """Output image retains the original pixel dimensions."""
        original_img = Image.open(io.BytesIO(valid_jpeg_bytes))
        original_size = original_img.size

        cleaned = strip_photo_exif(valid_jpeg_bytes)
        cleaned_img = Image.open(io.BytesIO(cleaned))
        assert cleaned_img.size == original_size

    def test_no_disk_write(self, valid_jpeg_bytes: bytes, tmp_path: Path) -> None:
        """strip_photo_exif operates purely in memory — no file is created."""
        before = set(tmp_path.iterdir())
        strip_photo_exif(valid_jpeg_bytes)
        after = set(tmp_path.iterdir())
        assert before == after


# ---------------------------------------------------------------------------
# Test — assert_storage_key_contained
# ---------------------------------------------------------------------------


class TestAssertStorageKeyContained:
    """``assert_storage_key_contained`` — path traversal security validation."""

    @pytest.fixture(autouse=True)
    def _isolate_media_root(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Redirect MEDIA_ROOT to a temp dir for deterministic realpath checks."""
        monkeypatch.setattr(
            "apps.media.services.filesystem.settings",
            SimpleNamespace(MEDIA_ROOT=tmp_path),
        )

    def test_rejects_nul_byte(self) -> None:
        """A NUL byte in the storage key raises ValueError."""
        with pytest.raises(ValueError, match="NUL byte"):
            assert_storage_key_contained("evil\x00key.jpg")

    def test_rejects_absolute_path(self) -> None:
        """An absolute path (leading '/') raises ValueError."""
        with pytest.raises(ValueError, match="absolute"):
            assert_storage_key_contained("/etc/passwd.jpg")

    def test_rejects_parent_directory(self) -> None:
        """A leading '..' segment raises ValueError."""
        with pytest.raises(ValueError, match="parent-directory"):
            assert_storage_key_contained("../evil.jpg")

    def test_rejects_nested_parent_directory(self) -> None:
        """A '..' segment anywhere in the path raises ValueError."""
        with pytest.raises(ValueError, match="parent-directory"):
            assert_storage_key_contained("subdir/../../etc/passwd.jpg")

    def test_accepts_valid_relative_key(self) -> None:
        """A simple UUID-like key passes all checks."""
        assert_storage_key_contained("abc12345-6789-0123-4567-89abcdef0123.jpg")

    def test_accepts_subdirectory_key(self) -> None:
        """A key with subdirectories (no '..') passes."""
        assert_storage_key_contained("thumbnails/uuid.jpg")

    def test_rejects_symlink_escape(self, tmp_path: Path) -> None:
        """A symlink that resolves outside MEDIA_ROOT raises ValueError."""
        # Create target outside MEDIA_ROOT
        target = tmp_path.parent / "escape_target.jpg"
        target.write_bytes(b"secret")
        # Create symlink inside MEDIA_ROOT pointing outside
        link = tmp_path / "escape.jpg"
        link.symlink_to(target)

        with pytest.raises(ValueError, match="resolves outside"):
            assert_storage_key_contained("escape.jpg")


# ---------------------------------------------------------------------------
# Test — move_staging_to_permanent
# ---------------------------------------------------------------------------


class TestMoveStagingToPermanent:
    """``move_staging_to_permanent`` — staging prefix removal and file promotion."""

    @pytest.fixture(autouse=True)
    def _isolate_media_root(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Redirect MEDIA_ROOT to a temp dir and create the staging subdir."""
        monkeypatch.setattr(
            "apps.media.services.filesystem.settings",
            SimpleNamespace(MEDIA_ROOT=tmp_path),
        )
        (tmp_path / "staging").mkdir()

    def test_strips_staging_prefix_from_all_fields(self, tmp_path: Path) -> None:
        """Staging prefix is stripped from storage_key and all thumbnail fields."""
        staging_dir = tmp_path / "staging"
        for name in [
            "uuid.jpg",
            "uuid-small.jpg",
            "uuid-medium.jpg",
            "uuid-large.jpg",
        ]:
            (staging_dir / name).write_bytes(b"staged")

        photos = [
            {
                "storage_key": "staging/uuid.jpg",
                "thumbnail_small": "staging/uuid-small.jpg",
                "thumbnail_medium": "staging/uuid-medium.jpg",
                "thumbnail_large": "staging/uuid-large.jpg",
            }
        ]

        move_staging_to_permanent(photos)

        assert photos[0]["storage_key"] == "uuid.jpg"
        assert photos[0]["thumbnail_small"] == "uuid-small.jpg"
        assert photos[0]["thumbnail_medium"] == "uuid-medium.jpg"
        assert photos[0]["thumbnail_large"] == "uuid-large.jpg"

        # Files physically moved to permanent location
        assert (tmp_path / "uuid.jpg").exists()
        assert (tmp_path / "uuid-small.jpg").exists()
        assert (tmp_path / "uuid-medium.jpg").exists()
        assert (tmp_path / "uuid-large.jpg").exists()

    def test_leaves_non_staging_keys_untouched(self, tmp_path: Path) -> None:
        """Keys without the staging prefix are not modified."""
        (tmp_path / "permanent.jpg").write_bytes(b"data")
        (tmp_path / "permanent-small.jpg").write_bytes(b"data")

        photos = [
            {
                "storage_key": "permanent.jpg",
                "thumbnail_small": "permanent-small.jpg",
                "thumbnail_medium": "perm-medium.jpg",
                "thumbnail_large": "perm-large.jpg",
            }
        ]

        move_staging_to_permanent(photos)

        assert photos[0]["storage_key"] == "permanent.jpg"
        assert photos[0]["thumbnail_small"] == "permanent-small.jpg"
        assert photos[0]["thumbnail_medium"] == "perm-medium.jpg"
        assert photos[0]["thumbnail_large"] == "perm-large.jpg"

    def test_updates_key_even_if_file_missing(self) -> None:
        """The key is updated even when the staging file does not exist on disk."""
        photos = [{"storage_key": "staging/missing.jpg"}]

        move_staging_to_permanent(photos)

        assert photos[0]["storage_key"] == "missing.jpg"

    def test_exdev_falls_back_to_shutil_move(self, tmp_path: Path) -> None:
        """OSError(EXDEV) from os.replace triggers the shutil.move fallback."""
        staging_file = tmp_path / "staging" / "uuid.jpg"
        staging_file.write_bytes(b"test-data")

        photos = [{"storage_key": "staging/uuid.jpg"}]

        with (
            patch(
                "apps.media.services.filesystem.os.replace",
                side_effect=OSError(errno.EXDEV, "cross-device"),
            ) as mock_replace,
            patch("apps.media.services.filesystem.shutil.move") as mock_move,
        ):
            move_staging_to_permanent(photos)

        mock_replace.assert_called_once()
        mock_move.assert_called_once()
        assert photos[0]["storage_key"] == "uuid.jpg"

    def test_non_exdev_oserror_reraises(self, tmp_path: Path) -> None:
        """Non-EXDEV OSError from os.replace is re-raised to the caller."""
        staging_file = tmp_path / "staging" / "uuid.jpg"
        staging_file.write_bytes(b"test-data")

        photos = [{"storage_key": "staging/uuid.jpg"}]

        with patch(
            "apps.media.services.filesystem.os.replace",
            side_effect=OSError(errno.EACCES, "permission denied"),
        ):
            with pytest.raises(OSError, match="permission denied"):
                move_staging_to_permanent(photos)

        # Key must NOT be updated when os.replace raises
        assert photos[0]["storage_key"] == "staging/uuid.jpg"

    def test_multiple_photos_processed(self, tmp_path: Path) -> None:
        """Each photo dict in the list is processed independently."""
        staging_dir = tmp_path / "staging"
        for name in ["a.jpg", "b.jpg"]:
            (staging_dir / name).write_bytes(b"data")

        photos = [
            {"storage_key": "staging/a.jpg", "thumbnail_small": None},
            {"storage_key": "staging/b.jpg", "thumbnail_small": None},
        ]

        move_staging_to_permanent(photos)

        assert photos[0]["storage_key"] == "a.jpg"
        assert photos[1]["storage_key"] == "b.jpg"
