"""
Unit tests for ThumbnailService.

Tests cover all three size variants, aspect ratio preservation for
non-square images, progressive JPEG output, invalid input handling, and the
atomic per-file publish contract (temp cleanup, permissions, mode semantics).
No database interaction required — uses pytest-style with temporary
directories.
"""

from __future__ import annotations

import io
import os
from pathlib import Path

import pytest
from PIL import Image

from apps.core.enums import ThumbnailSizeStrEnum, WriteMode
from apps.media.services.thumbnails import TEMP_SUFFIX, ThumbnailService


def _make_test_image(width: int, height: int) -> bytes:
    """Create a simple RGB test image and return its JPEG bytes.

    Args:
        width: Image width in pixels.
        height: Image height in pixels.

    Returns:
        JPEG-encoded image content as bytes.
    """
    image = Image.new("RGB", (width, height), color=(64, 128, 192))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=95)
    buffer.seek(0)
    return buffer.getvalue()


def _thumbnail_names(tmp_path: Path, original_key: str) -> set[str]:
    """Return the expected final filenames for ``original_key``."""
    stem = os.path.splitext(original_key)[0]
    return {f"{stem}-{size.value}.jpg" for size in ThumbnailSizeStrEnum}


def _temp_files(directory: Path) -> list[Path]:
    """Return every temp file left in ``directory``."""
    return [p for p in directory.iterdir() if p.name.endswith(TEMP_SUFFIX)]


class TestThumbnailService:
    """Tests for ThumbnailService thumbnail generation."""

    def test_all_three_variants_returned(self, tmp_path: Path) -> None:
        """generate_thumbnails returns all three supported size variants."""
        photo_bytes = _make_test_image(800, 600)
        service = ThumbnailService(storage_dir=str(tmp_path))
        result = service.generate_thumbnails(photo_bytes, "test.jpg")

        assert ThumbnailSizeStrEnum.SMALL in result
        assert ThumbnailSizeStrEnum.MEDIUM in result
        assert ThumbnailSizeStrEnum.LARGE in result

    def test_storage_key_format_follows_uuid_size_pattern(self, tmp_path: Path) -> None:
        """Storage keys follow the '<uuid>-<size>.jpg' pattern."""
        photo_bytes = _make_test_image(800, 600)
        service = ThumbnailService(storage_dir=str(tmp_path))
        result = service.generate_thumbnails(photo_bytes, "abc123.jpg")

        stem = "abc123"
        assert (
            result[ThumbnailSizeStrEnum.SMALL]
            == f"{stem}-{ThumbnailSizeStrEnum.SMALL.value}.jpg"
        )
        assert (
            result[ThumbnailSizeStrEnum.MEDIUM]
            == f"{stem}-{ThumbnailSizeStrEnum.MEDIUM.value}.jpg"
        )
        assert (
            result[ThumbnailSizeStrEnum.LARGE]
            == f"{stem}-{ThumbnailSizeStrEnum.LARGE.value}.jpg"
        )

    def test_storage_key_with_multi_part_extension(self, tmp_path: Path) -> None:
        """Storage key handles multi-part extensions like .tar.gz correctly."""
        photo_bytes = _make_test_image(800, 600)
        service = ThumbnailService(storage_dir=str(tmp_path))
        result = service.generate_thumbnails(photo_bytes, "photo.tar.gz")

        # os.path.splitext('photo.tar.gz') -> ('photo.tar', '.gz')
        # The stem should be 'photo.tar'
        assert result[ThumbnailSizeStrEnum.SMALL] == "photo.tar-small.jpg"

    def test_atomic_write_creates_file(self, tmp_path: Path) -> None:
        """Generated thumbnail file exists on disk and is valid JPEG."""
        photo_bytes = _make_test_image(800, 600)
        service = ThumbnailService(storage_dir=str(tmp_path))
        result = service.generate_thumbnails(photo_bytes, "atomic.jpg")

        thumb_path = tmp_path / result[ThumbnailSizeStrEnum.SMALL]
        assert thumb_path.is_file()
        with Image.open(thumb_path) as img:
            assert img.format == "JPEG"
            img.verify()  # Raises on corrupt data

    def test_atomic_write_collision_raises_file_exists(self, tmp_path: Path) -> None:
        """Writing to an existing thumbnail path raises FileExistsError.

        The failed second call must not silently clobber the first call's
        bytes: the published files stay byte-identical.  This is the half of
        the test's original purpose a bare ``pytest.raises`` never verified.
        """
        photo_bytes = _make_test_image(800, 600)
        service = ThumbnailService(storage_dir=str(tmp_path))
        # First call succeeds
        service.generate_thumbnails(photo_bytes, "collision.jpg")
        published = sorted(p.name for p in tmp_path.iterdir())
        before = {name: (tmp_path / name).read_bytes() for name in published}
        # Second call with same key raises FileExistsError (os.link -> EEXIST)
        with pytest.raises(FileExistsError):
            service.generate_thumbnails(photo_bytes, "collision.jpg")

        # The existing files are untouched — no silent overwrite, no temp left.
        assert sorted(p.name for p in tmp_path.iterdir()) == published
        for name, content in before.items():
            assert (tmp_path / name).read_bytes() == content

    def test_small_thumbnail_generation(self, tmp_path: Path) -> None:
        """SMALL variant produces a 240x180 thumbnail."""
        photo_bytes = _make_test_image(1920, 1080)
        service = ThumbnailService(storage_dir=str(tmp_path))
        result = service.generate_thumbnails(photo_bytes, "photo.jpg")

        thumb_path = tmp_path / result[ThumbnailSizeStrEnum.SMALL]
        assert thumb_path.exists()

        with Image.open(thumb_path) as img:
            assert img.width <= 240
            assert img.height <= 180
            assert img.format == "JPEG"

    def test_medium_thumbnail_generation(self, tmp_path: Path) -> None:
        """MEDIUM variant produces a 640x480 thumbnail."""
        photo_bytes = _make_test_image(1920, 1080)
        service = ThumbnailService(storage_dir=str(tmp_path))
        result = service.generate_thumbnails(photo_bytes, "photo.jpg")

        thumb_path = tmp_path / result[ThumbnailSizeStrEnum.MEDIUM]
        assert thumb_path.exists()

        with Image.open(thumb_path) as img:
            assert img.width <= 640
            assert img.height <= 480
            assert img.format == "JPEG"

    def test_large_thumbnail_generation(self, tmp_path: Path) -> None:
        """LARGE variant produces a 1280x960 thumbnail."""
        photo_bytes = _make_test_image(1920, 1080)
        service = ThumbnailService(storage_dir=str(tmp_path))
        result = service.generate_thumbnails(photo_bytes, "photo.jpg")

        thumb_path = tmp_path / result[ThumbnailSizeStrEnum.LARGE]
        assert thumb_path.exists()

        with Image.open(thumb_path) as img:
            assert img.width <= 1280
            assert img.height <= 960
            assert img.format == "JPEG"

    def test_aspect_ratio_preservation(self, tmp_path: Path) -> None:
        """Non-square (wide) image preserves aspect ratio inside box."""
        photo_bytes = _make_test_image(2000, 1000)
        service = ThumbnailService(storage_dir=str(tmp_path))
        result = service.generate_thumbnails(photo_bytes, "wide.jpg")

        thumb_path = tmp_path / result[ThumbnailSizeStrEnum.SMALL]
        with Image.open(thumb_path) as img:
            w, h = img.size
            # Must fit within 240x180 box
            assert w <= 240
            assert h <= 180
            # Must preserve 2:1 aspect ratio (2000:1000)
            # Allow off-by-one from thumbnail() rounding
            assert abs(w / h - 2.0) < 0.1, (
                f"Aspect ratio {w}/{h} = {w / h:.3f} differs from 2.0"
            )

    def test_progressive_jpeg_output(self, tmp_path: Path) -> None:
        """Generated JPEG thumbnails are progressive."""
        photo_bytes = _make_test_image(800, 600)
        service = ThumbnailService(storage_dir=str(tmp_path))
        result = service.generate_thumbnails(photo_bytes, "prog.jpg")

        thumb_path = tmp_path / result[ThumbnailSizeStrEnum.MEDIUM]
        with Image.open(thumb_path) as img:
            # Pillow stores progressive flag as int 1, not True
            assert img.info.get("progressive"), "Expected progressive JPEG output"

    def test_invalid_image_handling(self, tmp_path: Path) -> None:
        """Invalid image bytes raises ValueError."""
        service = ThumbnailService(storage_dir=str(tmp_path))
        try:
            service.generate_thumbnails(b"not-an-image-data", "bad.jpg")
        except ValueError:
            pass
        except Exception as exc:
            msg = f"Expected ValueError, got {type(exc).__name__}: {exc}"
            raise AssertionError(msg) from exc
        else:
            msg = "Expected ValueError was not raised"
            raise AssertionError(msg)

    def test_no_temp_file_survives_a_successful_call(self, tmp_path: Path) -> None:
        """A successful call leaves exactly the three final files, no temp."""
        photo_bytes = _make_test_image(800, 600)
        service = ThumbnailService(storage_dir=str(tmp_path))
        service.generate_thumbnails(photo_bytes, "clean.jpg")

        assert {p.name for p in tmp_path.iterdir()} == _thumbnail_names(
            tmp_path, "clean.jpg"
        )
        assert _temp_files(tmp_path) == []

    def test_no_temp_file_survives_a_failure(self, tmp_path: Path) -> None:
        """A failure inside the write step leaves no partial and no temp.

        The destination must be **absent** — not zero-length, not truncated —
        and no temp file may remain in the directory.
        """
        photo_bytes = _make_test_image(800, 600)
        service = ThumbnailService(storage_dir=str(tmp_path))

        def _failing_publish(content: bytes, target_path: str, mode: WriteMode) -> None:
            # Simulate a failure *after* the temp file exists but before any
            # final path is published (e.g. ENOSPC / EIO).
            raise OSError("simulated write failure")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(ThumbnailService, "_publish", staticmethod(_failing_publish))
            with pytest.raises(OSError, match="simulated write failure"):
                service.generate_thumbnails(photo_bytes, "boom.jpg")

        assert sorted(p.name for p in tmp_path.iterdir()) == []
        assert _temp_files(tmp_path) == []

    def test_failure_on_second_size_leaves_first_complete_and_no_temp(
        self, tmp_path: Path
    ) -> None:
        """Per-file isolation: the 1st size survives a 2nd-size failure.

        Every file present at a final path is complete; later sizes are
        absent; no temp file remains.  A per-call rollback is explicitly out
        of scope, so the assertion is "what is present is complete", not
        "nothing is present".
        """
        photo_bytes = _make_test_image(800, 600)
        service = ThumbnailService(storage_dir=str(tmp_path))
        real_publish = ThumbnailService._publish
        calls: list[str] = []

        def _publish_until_medium(
            content: bytes, target_path: str, mode: WriteMode
        ) -> None:
            calls.append(os.path.basename(target_path))
            if len(calls) == 2:
                raise OSError("simulated failure on the second size")
            real_publish(content, target_path, mode)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                ThumbnailService, "_publish", staticmethod(_publish_until_medium)
            )
            with pytest.raises(OSError, match="simulated failure on the second size"):
                service.generate_thumbnails(photo_bytes, "partial.jpg")

        names = {p.name for p in tmp_path.iterdir()}
        assert names == {"partial-small.jpg"}
        assert _temp_files(tmp_path) == []

        # The surviving first size is a complete, decodable JPEG.
        with Image.open(tmp_path / "partial-small.jpg") as img:
            img.verify()

    def test_published_file_is_group_and_world_readable(self, tmp_path: Path) -> None:
        """A published thumbnail is not ``0600``.

        nginx serves ``/media/`` as a different uid from the app, so a file
        created with ``tempfile.mkstemp`` defaults (``0600``) would 403 every
        image.  The mode must match an ordinary ``os.open`` write.
        """
        photo_bytes = _make_test_image(800, 600)
        service = ThumbnailService(storage_dir=str(tmp_path))
        result = service.generate_thumbnails(photo_bytes, "mode.jpg")

        mode = os.stat(tmp_path / result[ThumbnailSizeStrEnum.SMALL]).st_mode
        assert mode & 0o044, "published thumbnail is not group/world readable"
        assert mode & 0o400, "published thumbnail is not owner readable"

    def test_replace_mode_overwrites_existing_complete_file(
        self, tmp_path: Path
    ) -> None:
        """``REPLACE`` overwrites an existing complete file with valid JPEG."""
        first = _make_test_image(200, 150)
        second = _make_test_image(1600, 1200)
        service = ThumbnailService(storage_dir=str(tmp_path))
        service.generate_thumbnails(first, "rep.jpg")
        small_path = tmp_path / "rep-small.jpg"
        original_size = small_path.stat().st_size

        service.generate_thumbnails(second, "rep.jpg", mode=WriteMode.REPLACE)

        assert small_path.stat().st_size != original_size
        with Image.open(small_path) as img:
            assert img.format == "JPEG"
            img.verify()
        assert _temp_files(tmp_path) == []

    def test_replace_mode_overwrites_truncated_leftover(self, tmp_path: Path) -> None:
        """``REPLACE`` fixes the corrupt-byte class left by a dead run."""
        photo_bytes = _make_test_image(800, 600)
        service = ThumbnailService(storage_dir=str(tmp_path))
        # A truncated (zero-length) file at a final path — the state a dead
        # non-atomic run left behind.
        (tmp_path / "trunc-small.jpg").write_bytes(b"")
        (tmp_path / "trunc-medium.jpg").write_bytes(b"\xff\xd8partial")
        (tmp_path / "trunc-large.jpg").write_bytes(b"")

        service.generate_thumbnails(photo_bytes, "trunc.jpg", mode=WriteMode.REPLACE)

        for name in _thumbnail_names(tmp_path, "trunc.jpg"):
            with Image.open(tmp_path / name) as img:
                assert img.format == "JPEG"
                img.verify()
        assert _temp_files(tmp_path) == []

    def test_replace_mode_creates_when_absent(self, tmp_path: Path) -> None:
        """``REPLACE`` creates the file when nothing exists at the path."""
        photo_bytes = _make_test_image(800, 600)
        service = ThumbnailService(storage_dir=str(tmp_path))
        service.generate_thumbnails(photo_bytes, "fresh.jpg", mode=WriteMode.REPLACE)

        assert {p.name for p in tmp_path.iterdir()} == _thumbnail_names(
            tmp_path, "fresh.jpg"
        )

    def test_temp_file_lands_in_destination_directory_including_staging(
        self, tmp_path: Path
    ) -> None:
        """Temp files are created next to the target, not in a system dir.

        A ``staging/``-prefixed key publishes into ``MEDIA_ROOT/staging/``; the
        temp must be created there too, because a cross-device rename would
        degrade to a non-atomic copy.
        """
        photo_bytes = _make_test_image(800, 600)
        staging_dir = tmp_path / "staging"
        staging_dir.mkdir()
        service = ThumbnailService(storage_dir=str(tmp_path))
        observed: list[Path] = []
        real_link = os.link

        def _recording_link(src: str, dst: str, **kwargs: object) -> None:
            observed.append(Path(src))
            real_link(src, dst, **kwargs)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(os, "link", _recording_link)
            service.generate_thumbnails(photo_bytes, "staging/photo.jpg")

        assert observed, "no temp file was observed in the destination directory"
        assert all(p.parent == staging_dir for p in observed)
        assert all(p.name.endswith(TEMP_SUFFIX) for p in observed)
        assert {p.name for p in staging_dir.iterdir()} == {
            "photo-small.jpg",
            "photo-medium.jpg",
            "photo-large.jpg",
        }

    def test_create_only_mode_never_overwrites(self, tmp_path: Path) -> None:
        """An explicit ``CREATE_ONLY`` call refuses an existing file."""
        photo_bytes = _make_test_image(800, 600)
        service = ThumbnailService(storage_dir=str(tmp_path))
        service.generate_thumbnails(photo_bytes, "once.jpg")

        with pytest.raises(FileExistsError):
            service.generate_thumbnails(
                photo_bytes, "once.jpg", mode=WriteMode.CREATE_ONLY
            )
        assert _temp_files(tmp_path) == []

