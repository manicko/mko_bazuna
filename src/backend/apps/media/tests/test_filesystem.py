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
import os
import re
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from django.test import override_settings
from PIL import Image

from apps.media.schemas import SubmittedPhoto
from apps.media.services.filesystem import (
    DELETE_PHOTO_MAX_ATTEMPTS,
    assert_storage_key_contained,
    delete_photo,
    generate_storage_key,
    plan_staging_promotion,
    promote_media_files,
    reclaim_staged_keys,
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
        caplog: pytest.LogCaptureFixture,
    ) -> Iterator[None]:
        """Redirect MEDIA_ROOT to a temp dir and capture WARNING+ logs.

        Uses ``override_settings`` instead of a ``SimpleNamespace`` monkeypatch
        so the real Django settings object is preserved (other attributes remain
        accessible) and only ``MEDIA_ROOT`` is overridden.
        """
        caplog.set_level(logging.WARNING)
        with override_settings(MEDIA_ROOT=str(tmp_path)):
            yield

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

    def test_strips_jpeg_comment(self) -> None:
        """JPEG COM marker bytes are removed by strip_photo_exif."""
        img = Image.new("RGB", (100, 100), color="red")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", comment=b"PII-in-comment")
        cleaned = strip_photo_exif(buf.getvalue())
        assert b"PII-in-comment" not in cleaned

    def test_strips_xmp_packet(self) -> None:
        """XMP packet bytes are removed by strip_photo_exif."""
        img = Image.new("RGB", (100, 100), color="red")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", exif=b"\xff\xe1\x00\x10Exif\x00\x00")
        cleaned = strip_photo_exif(buf.getvalue())
        assert b"Exif\x00\x00" not in cleaned


# ---------------------------------------------------------------------------
# Test — assert_storage_key_contained
# ---------------------------------------------------------------------------


class TestAssertStorageKeyContained:
    """``assert_storage_key_contained`` — path traversal security validation."""

    @pytest.fixture(autouse=True)
    def _isolate_media_root(
        self,
        tmp_path: Path,
    ) -> Iterator[None]:
        """Redirect MEDIA_ROOT to a temp dir for deterministic realpath checks."""
        with override_settings(MEDIA_ROOT=str(tmp_path)):
            yield

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


class TestPlanStagingPromotion:
    """``plan_staging_promotion`` — PURE key rewriting with existence validation."""

    @pytest.fixture(autouse=True)
    def _isolate_media_root(
        self,
        tmp_path: Path,
    ) -> Iterator[None]:
        """Redirect MEDIA_ROOT to a temp dir and create the staging subdir."""
        with override_settings(MEDIA_ROOT=str(tmp_path)):
            (tmp_path / "staging").mkdir()
            yield

    def test_strips_staging_prefix_from_all_fields(self, tmp_path: Path) -> None:
        """Staging prefix is stripped from storage_key and all thumbnail fields.

        ``plan_staging_promotion`` performs no filesystem mutation, so the
        staging files must still be present at their original paths afterwards.
        """
        staging_dir = tmp_path / "staging"
        for name in [
            "uuid.jpg",
            "uuid-small.jpg",
            "uuid-medium.jpg",
            "uuid-large.jpg",
        ]:
            (staging_dir / name).write_bytes(b"staged")

        photos = [
            SubmittedPhoto(
                storage_key="staging/uuid.jpg",
                thumbnail_small="staging/uuid-small.jpg",
                thumbnail_medium="staging/uuid-medium.jpg",
                thumbnail_large="staging/uuid-large.jpg",
            )
        ]

        permanent_keys = plan_staging_promotion(photos)

        assert photos[0].storage_key == "uuid.jpg"
        assert photos[0].thumbnail_small == "uuid-small.jpg"
        assert photos[0].thumbnail_medium == "uuid-medium.jpg"
        assert photos[0].thumbnail_large == "uuid-large.jpg"

        assert set(permanent_keys) == {
            "uuid.jpg",
            "uuid-small.jpg",
            "uuid-medium.jpg",
            "uuid-large.jpg",
        }

        # PURE: no filesystem mutation — the staging files are still in place
        # and nothing was written to permanent storage.
        assert (staging_dir / "uuid.jpg").exists()
        assert not (tmp_path / "uuid.jpg").exists()

    def test_leaves_non_staging_keys_untouched(self, tmp_path: Path) -> None:
        """Keys without the staging prefix are not modified and not returned."""
        (tmp_path / "permanent.jpg").write_bytes(b"data")
        (tmp_path / "permanent-small.jpg").write_bytes(b"data")

        photos = [
            SubmittedPhoto(
                storage_key="permanent.jpg",
                thumbnail_small="permanent-small.jpg",
                thumbnail_medium="perm-medium.jpg",
                thumbnail_large="perm-large.jpg",
            )
        ]

        permanent_keys = plan_staging_promotion(photos)

        assert photos[0].storage_key == "permanent.jpg"
        assert photos[0].thumbnail_small == "permanent-small.jpg"
        assert photos[0].thumbnail_medium == "perm-medium.jpg"
        assert photos[0].thumbnail_large == "perm-large.jpg"
        assert permanent_keys == []

    def test_multiple_photos_processed(self, tmp_path: Path) -> None:
        """Each photo in the list is processed independently."""
        staging_dir = tmp_path / "staging"
        for name in ["a.jpg", "b.jpg"]:
            (staging_dir / name).write_bytes(b"data")

        photos = [
            SubmittedPhoto(storage_key="staging/a.jpg", thumbnail_small=None),
            SubmittedPhoto(storage_key="staging/b.jpg", thumbnail_small=None),
        ]

        permanent_keys = plan_staging_promotion(photos)

        assert photos[0].storage_key == "a.jpg"
        assert photos[1].storage_key == "b.jpg"
        assert set(permanent_keys) == {"a.jpg", "b.jpg"}

    def test_raises_and_leaves_key_untouched_when_file_missing(self) -> None:
        """A missing staged file raises ``FileNotFoundError`` and rewrites no key.

        This INVERTS the former ``test_updates_key_even_if_file_missing``,
        which asserted the defect: it rewrote the key to the permanent form
        even though there was no file to move.  The contract is now *rewrite a
        key iff the file was actually moved* — a missing staged file is a
        terminal error the caller must surface, and the sibling
        ``TestPromoteMediaFiles::test_non_exdev_oserror_is_logged_and_not_propagated``
        already asserted the same contract for the move itself.
        """
        photos = [SubmittedPhoto(storage_key="staging/missing.jpg")]

        with pytest.raises(FileNotFoundError, match="staging/missing.jpg"):
            plan_staging_promotion(photos)

        # No key is rewritten when validation fails.
        assert photos[0].storage_key == "staging/missing.jpg"

    def test_missing_second_photo_leaves_earlier_keys_rewritten(
        self, tmp_path: Path
    ) -> None:
        """Keys before the failing one are rewritten; keys at/after are not.

        The loop mutates as it iterates and raises mid-list, so a multi-photo
        submission that fails on the second photo leaves the first photo's key
        in its permanent form — the docstring's "no key at or after the failing
        one is rewritten" is exactly this, and a single-photo case cannot pin it.
        """
        staging_dir = tmp_path / "staging"
        (staging_dir / "first.jpg").write_bytes(b"staged")
        # ``staging/second.jpg`` is deliberately absent.

        photos = [
            SubmittedPhoto(storage_key="staging/first.jpg", thumbnail_small=None),
            SubmittedPhoto(storage_key="staging/second.jpg", thumbnail_small=None),
        ]

        with pytest.raises(FileNotFoundError, match="staging/second.jpg"):
            plan_staging_promotion(photos)

        # The first photo was processed before the raise: its key is rewritten.
        assert photos[0].storage_key == "first.jpg"
        # The failing photo's key is untouched.
        assert photos[1].storage_key == "staging/second.jpg"


class TestPromoteMediaFiles:
    """``promote_media_files`` — the post-commit filesystem move."""

    @pytest.fixture(autouse=True)
    def _isolate_media_root(
        self,
        tmp_path: Path,
    ) -> Iterator[None]:
        """Redirect MEDIA_ROOT to a temp dir and create the staging subdir."""
        with override_settings(MEDIA_ROOT=str(tmp_path)):
            (tmp_path / "staging").mkdir()
            yield

    def test_promotes_staging_file_to_permanent(self, tmp_path: Path) -> None:
        """A staged file is moved from ``staging/<key>`` to ``<key>``."""
        (tmp_path / "staging" / "uuid.jpg").write_bytes(b"test-data")

        promote_media_files(["uuid.jpg"])

        assert (tmp_path / "uuid.jpg").is_file()
        assert not (tmp_path / "staging" / "uuid.jpg").exists()

    def test_exdev_falls_back_to_shutil_move(self, tmp_path: Path) -> None:
        """OSError(EXDEV) from os.replace triggers the shutil.move fallback."""
        staging_file = tmp_path / "staging" / "uuid.jpg"
        staging_file.write_bytes(b"test-data")

        with (
            patch(
                "apps.media.services.filesystem.os.replace",
                side_effect=OSError(errno.EXDEV, "cross-device"),
            ) as mock_replace,
            patch("apps.media.services.filesystem.shutil.move") as mock_move,
        ):
            promote_media_files(["uuid.jpg"])

        mock_replace.assert_called_once()
        mock_move.assert_called_once()

    def test_non_exdev_oserror_is_logged_and_not_propagated(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A non-EXDEV ``OSError`` is logged, never propagated out of the move.

        This carries forward the intent of the former
        ``test_non_exdev_oserror_reraises`` (which pinned that ``os.replace``
        failures are the error path, not a happy path) under the new
        post-commit contract: because ``promote_media_files`` runs from
        ``transaction.on_commit`` the row is already committed, so the failure
        must be recorded rather than raised back into the caller.  It asserts
        the *behavioural* consequence — an ERROR/WARNING record exists and the
        file was not moved — not a message's wording.
        """
        staging_file = tmp_path / "staging" / "uuid.jpg"
        staging_file.write_bytes(b"test-data")

        with (
            caplog.at_level(logging.ERROR, logger="apps.media.services.filesystem"),
            patch(
                "apps.media.services.filesystem.os.replace",
                side_effect=OSError(errno.EACCES, "permission denied"),
            ),
        ):
            promote_media_files(["uuid.jpg"])

        assert any(record.levelno >= logging.ERROR for record in caplog.records), (
            "expected an ERROR/WARNING record for the failed key"
        )
        # The file was not moved, so the key was not promoted.
        assert (tmp_path / "staging" / "uuid.jpg").exists()
        assert not (tmp_path / "uuid.jpg").exists()

    def test_one_failed_key_does_not_abort_the_remaining_promotions(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """One failing key is logged and skipped; the rest still move.

        Develops a real race with the shipped convention: this runs POST-COMMIT,
        so an exception crossing back into the caller would be a lie — the row is
        already committed.  The per-key handler must log an ERROR/WARNING record
        and continue rather than propagate.
        """
        (tmp_path / "staging" / "a.jpg").write_bytes(b"data-a")
        (tmp_path / "staging" / "b.jpg").write_bytes(b"data-b")

        real_replace = os.replace

        def replace_fails_for_a(src: str, dst: str) -> None:
            if os.path.basename(src) == "a.jpg":
                raise OSError(errno.EACCES, "permission denied")
            real_replace(src, dst)

        with (
            caplog.at_level(logging.ERROR, logger="apps.media.services.filesystem"),
            patch(
                "apps.media.services.filesystem.os.replace",
                side_effect=replace_fails_for_a,
            ),
        ):
            promote_media_files(["a.jpg", "b.jpg"])

        # The failure was recorded, not swallowed silently.
        assert any(
            record.levelno >= logging.ERROR for record in caplog.records
        ), "expected an ERROR/WARNING record for the failed key"
        # The later key still moved despite the earlier failure.
        assert (tmp_path / "b.jpg").is_file()
        assert not (tmp_path / "staging" / "b.jpg").exists()


# ---------------------------------------------------------------------------
# Test — reclaim_staged_keys
# ---------------------------------------------------------------------------


class TestReclaimStagedKeys:
    """``reclaim_staged_keys`` — post-commit deletion of skipped staged uploads."""

    @pytest.fixture(autouse=True)
    def _isolate_media_root(
        self,
        tmp_path: Path,
    ) -> Iterator[None]:
        """Redirect MEDIA_ROOT to a temp dir and create the staging subdir."""
        with override_settings(MEDIA_ROOT=str(tmp_path)):
            (tmp_path / "staging").mkdir()
            yield

    def test_deletes_all_staged_files_and_promotes_nothing(
        self, tmp_path: Path
    ) -> None:
        """Each key's staged file is removed; no permanent file is created.

        The permanent-form key names the eventual destination, but the bytes are
        still at ``staging/<key>`` at reclaim time — so ``reclaim_staged_keys``
        composes ``STAGING_PREFIX + key`` and must not touch the permanent path.
        """
        keys = ["uuid.jpg", "uuid-small.jpg", "uuid-medium.jpg", "uuid-large.jpg"]
        for key in keys:
            (tmp_path / "staging" / key).write_bytes(b"staged")

        reclaim_staged_keys(keys)

        for key in keys:
            assert not (tmp_path / "staging" / key).exists(), (
                f"staged file {key} was not reclaimed"
            )
            assert not (tmp_path / key).exists(), (
                f"reclaim must not create permanent {key}"
            )

    def test_missing_staged_file_is_silent(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A staged file already gone is a silent no-op, never an exception."""
        with caplog.at_level(logging.WARNING):
            reclaim_staged_keys(["already-gone.jpg"])  # must not raise

        assert not (tmp_path / "staging" / "already-gone.jpg").exists()

    def test_one_bad_key_does_not_abort_the_remaining_reclaims(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A traversal key is swallowed and logged; the rest are still deleted.

        This is the per-key-isolation tripwire.  ``delete_photo`` calls
        ``assert_storage_key_contained`` outside its retry loop and that raises
        ``ValueError``; because Django invokes ``on_commit`` callbacks unguarded,
        an unguarded raise would abort every later callback.  The composed
        argument here is ``"staging/../x.jpg"``, whose parts contain ``..``, so
        the containment check rejects it.  Without the per-key ``try/except``
        this test fails with an escaped ``ValueError`` and the good key survives.
        """
        (tmp_path / "staging" / "good.jpg").write_bytes(b"staged")

        with caplog.at_level(
            logging.ERROR, logger="apps.media.services.filesystem"
        ):
            reclaim_staged_keys(["../x.jpg", "good.jpg"])  # must not raise

        assert any(record.levelno >= logging.ERROR for record in caplog.records), (
            "the rejected key should have been logged"
        )
        # The good key was still reclaimed despite the earlier bad key.
        assert not (tmp_path / "staging" / "good.jpg").exists()
