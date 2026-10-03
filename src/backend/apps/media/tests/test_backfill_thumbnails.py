"""
Integration tests for the backfill_thumbnails management command.

Verifies:
- Dry-run mode reports count without generating thumbnails
- Backfill generates missing thumbnails for AdImage records
- Partial backfill only fills missing variants (idempotent)
- Records with all thumbnails already present are skipped
- Missing original image files are handled gracefully
- Batch-size parameter processes records in chunks

Uses an isolated temporary MEDIA_ROOT with real image files.
"""

from __future__ import annotations

import io
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from django.core.management import call_command
from django.test import override_settings
from PIL import Image

from apps.ads.models import AdImage
from apps.media.services.filesystem import generate_storage_key
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_media_root() -> Generator[Path]:
    """Create a temporary MEDIA_ROOT isolated from the real media volume."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_test_image() -> bytes:
    """Create a simple RGB test image and return its JPEG bytes."""
    image = Image.new("RGB", (800, 600), color=(64, 128, 192))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=95)
    buffer.seek(0)
    return buffer.getvalue()


def _create_adimage_with_original(
    seller: object,
    category: object,
    city: object,
    media_root: Path,
    image_key: str | None = None,
    set_thumbnails: bool = False,
) -> AdImage:
    """Create a PUBLISHED ad with an AdImage and a physical original file.

    Args:
        seller: User for the ad.
        category: Category for the ad.
        city: City for the ad.
        media_root: Temporary MEDIA_ROOT path.
        image_key: Optional storage key (auto-generated if None).
        set_thumbnails: If True, sets thumbnail fields to dummy values.

    Returns:
        The created AdImage instance.
    """
    from apps.core.enums import AdStatus

    key = image_key or generate_storage_key()

    ad = create_test_ad(
        seller,
        category,
        city,
        status=AdStatus.PUBLISHED,
    )

    kwargs = {}
    if set_thumbnails:
        kwargs["thumbnail_small"] = f"{key}-small.jpg"
        kwargs["thumbnail_medium"] = f"{key}-medium.jpg"
        kwargs["thumbnail_large"] = f"{key}-large.jpg"

    ad_image = AdImage.objects.create(ad=ad, image=key, **kwargs)

    # Write the physical original file
    file_path = media_root / key
    file_path.write_bytes(_make_test_image())

    return ad_image


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBackfillThumbnails:
    """Integration tests for the backfill_thumbnails management command."""

    def test_dry_run_reports_count(self, seller, category, city, isolated_media_root):
        """--dry-run reports the count without generating thumbnails."""
        _create_adimage_with_original(seller, category, city, isolated_media_root)
        _create_adimage_with_original(seller, category, city, isolated_media_root)

        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            # Dry run should not raise
            call_command("backfill_thumbnails", dry_run=True)

        # Verify no thumbnails were generated
        for ad_image in AdImage.objects.all():
            assert ad_image.thumbnail_small is None
            assert ad_image.thumbnail_medium is None
            assert ad_image.thumbnail_large is None

    def test_backfill_generates_all_thumbnails(
        self, seller, category, city, isolated_media_root
    ):
        """Backfill generates all three thumbnail variants for missing records."""
        ad_image = _create_adimage_with_original(
            seller, category, city, isolated_media_root
        )

        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            call_command("backfill_thumbnails", batch_size=10)

        ad_image.refresh_from_db()
        assert ad_image.thumbnail_small is not None
        assert ad_image.thumbnail_small.endswith("-small.jpg")
        assert ad_image.thumbnail_medium is not None
        assert ad_image.thumbnail_medium.endswith("-medium.jpg")
        assert ad_image.thumbnail_large is not None
        assert ad_image.thumbnail_large.endswith("-large.jpg")

        # Verify physical files exist
        assert (isolated_media_root / ad_image.thumbnail_small).is_file()
        assert (isolated_media_root / ad_image.thumbnail_medium).is_file()
        assert (isolated_media_root / ad_image.thumbnail_large).is_file()

    def test_backfill_partial_thumbnails_only_fills_missing(
        self, seller, category, city, isolated_media_root
    ):
        """Backfill only fills missing thumbnail variants, preserving existing."""
        ad_image = _create_adimage_with_original(
            seller,
            category,
            city,
            isolated_media_root,
        )
        # Pre-set small thumbnail
        ad_image.thumbnail_small = "existing-small.jpg"
        ad_image.save()

        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            call_command("backfill_thumbnails", batch_size=10)

        ad_image.refresh_from_db()
        # Small should be preserved (not overwritten)
        assert ad_image.thumbnail_small == "existing-small.jpg"
        # Medium and large should be generated
        assert ad_image.thumbnail_medium is not None
        assert ad_image.thumbnail_medium.endswith("-medium.jpg")
        assert ad_image.thumbnail_large is not None
        assert ad_image.thumbnail_large.endswith("-large.jpg")

    def test_backfill_skips_records_with_all_thumbnails(
        self, seller, category, city, isolated_media_root
    ):
        """Records that already have all thumbnails are skipped (idempotent)."""
        ad_image = _create_adimage_with_original(
            seller, category, city, isolated_media_root, set_thumbnails=True
        )

        # Record already has all three thumbnails set
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            call_command("backfill_thumbnails", batch_size=10)

        # Verify no changes
        ad_image.refresh_from_db()
        assert ad_image.thumbnail_small is not None
        assert ad_image.thumbnail_medium is not None
        assert ad_image.thumbnail_large is not None

    def test_backfill_missing_file_skips_gracefully(
        self, seller, category, city, isolated_media_root
    ):
        """Missing original image file does not crash the command."""
        ad_image = _create_adimage_with_original(
            seller, category, city, isolated_media_root
        )
        # Delete the original file
        original_path = isolated_media_root / ad_image.image
        original_path.unlink()

        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            # Should not raise
            call_command("backfill_thumbnails", batch_size=10)

        ad_image.refresh_from_db()
        assert ad_image.thumbnail_small is None
        assert ad_image.thumbnail_medium is None
        assert ad_image.thumbnail_large is None

    def test_backfill_batch_processing(
        self, seller, category, city, isolated_media_root
    ):
        """Batch-size parameter correctly processes records in chunks."""
        # Create more records than default batch size
        num_records = 5
        for _ in range(num_records):
            _create_adimage_with_original(seller, category, city, isolated_media_root)

        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            call_command("backfill_thumbnails", batch_size=2)

        # All records should have thumbnails
        for ad_image in AdImage.objects.all():
            assert ad_image.thumbnail_small is not None
            assert ad_image.thumbnail_medium is not None
            assert ad_image.thumbnail_large is not None

    def test_backfill_generated_thumbnails_are_valid_jpeg(
        self, seller, category, city, isolated_media_root
    ):
        """Generated thumbnail files are valid progressive JPEG images."""
        ad_image = _create_adimage_with_original(
            seller, category, city, isolated_media_root
        )

        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            call_command("backfill_thumbnails", batch_size=10)

        ad_image.refresh_from_db()
        for field in ["thumbnail_small", "thumbnail_medium", "thumbnail_large"]:
            thumb_path = isolated_media_root / getattr(ad_image, field)
            with Image.open(thumb_path) as img:
                assert img.format == "JPEG"
                # Verify progressive flag
                assert img.info.get("progressive"), f"{field} is not progressive"
                img.verify()

    def test_backfill_zero_records_succeeds(self, isolated_media_root):
        """Running backfill when no records exist succeeds silently."""
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            # Should not raise
            call_command("backfill_thumbnails", batch_size=10)

    def test_backfill_repairs_stale_leftover_small_file(
        self, seller, category, city, isolated_media_root
    ):
        """A row with all-NULL columns and a leftover ``-small.jpg`` is repaired.

        This is the D2 tripwire: a dead run leaves ``-small.jpg`` on disk with
        every column ``NULL``.  The shipped guard's first ``O_EXCL`` collision
        skipped the row forever, so the columns stayed ``NULL``.  With the
        repair guard the leftover is overwritten and all three columns land.
        """
        ad_image = _create_adimage_with_original(
            seller, category, city, isolated_media_root
        )
        # Simulate the dead run: small file written, no columns persisted.
        leftover = isolated_media_root / f"{ad_image.image.rsplit('.', 1)[0]}-small.jpg"
        leftover.write_bytes(b"truncated-leftover")

        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            call_command("backfill_thumbnails", batch_size=10)

        ad_image.refresh_from_db()
        assert ad_image.thumbnail_small is not None
        assert ad_image.thumbnail_medium is not None
        assert ad_image.thumbnail_large is not None
        for field in ["thumbnail_small", "thumbnail_medium", "thumbnail_large"]:
            thumb_path = isolated_media_root / getattr(ad_image, field)
            assert thumb_path.is_file()
            with Image.open(thumb_path) as img:
                img.verify()

    def test_backfill_repair_run_is_idempotent(
        self, seller, category, city, isolated_media_root
    ):
        """A second repair run is a no-op — values unchanged, no errors.

        After the first run every column is populated, so Phase 1's queryset
        no longer selects the row; a second run must not touch it.
        """
        ad_image = _create_adimage_with_original(
            seller, category, city, isolated_media_root
        )
        leftover = isolated_media_root / f"{ad_image.image.rsplit('.', 1)[0]}-small.jpg"
        leftover.write_bytes(b"truncated-leftover")

        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            call_command("backfill_thumbnails", batch_size=10)
            ad_image.refresh_from_db()
            first = {
                "thumbnail_small": ad_image.thumbnail_small,
                "thumbnail_medium": ad_image.thumbnail_medium,
                "thumbnail_large": ad_image.thumbnail_large,
            }
            mtimes = {
                field: (isolated_media_root / value).stat().st_mtime_ns
                for field, value in first.items()
            }
            call_command("backfill_thumbnails", batch_size=10)

        ad_image.refresh_from_db()
        assert ad_image.thumbnail_small == first["thumbnail_small"]
        assert ad_image.thumbnail_medium == first["thumbnail_medium"]
        assert ad_image.thumbnail_large == first["thumbnail_large"]
        # No file was rewritten by the second run.
        for field, value in first.items():
            assert (isolated_media_root / value).stat().st_mtime_ns == mtimes[field]

    def test_decide_write_mode_three_cases(self, tmp_path):
        """The guard's decision table: skip / CREATE_ONLY / REPLACE.

        The column state is the source of truth:

        - a fully-populated row is not reached (filtered in Phase 1);
        - ``NULL`` columns with no files present -> ``CREATE_ONLY``;
        - ``NULL`` columns with a file present -> ``REPLACE`` (stale leftover).
        """
        from apps.core.enums import WriteMode
        from apps.media.management.commands.backfill_thumbnails import Command

        command = Command()
        row = AdImage.__new__(AdImage)
        row.id = 1

        # NULL columns, no files on disk -> CREATE_ONLY.
        row.image = "case.jpg"
        row.thumbnail_small = None
        row.thumbnail_medium = None
        row.thumbnail_large = None
        assert command._decide_write_mode(row, tmp_path) is WriteMode.CREATE_ONLY

        # NULL columns, leftover small file present -> REPLACE.
        (tmp_path / "case-small.jpg").write_bytes(b"x")
        assert command._decide_write_mode(row, tmp_path) is WriteMode.REPLACE

        # A fully-populated row is not consulted; every missing column absent
        # and populated columns pointing elsewhere -> CREATE_ONLY.
        row.thumbnail_small = "existing-small.jpg"
        row.thumbnail_medium = None
        row.thumbnail_large = None
        (tmp_path / "case-small.jpg").unlink()
        assert command._decide_write_mode(row, tmp_path) is WriteMode.CREATE_ONLY

