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
from PIL import Image
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from apps.ads.models import AdImage

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_media_root() -> Generator[Path]:
    """Create a temporary MEDIA_ROOT isolated from the real media volume."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def seller() -> object:
    """Create a seller user for ad fixtures."""
    from apps.users.models import User

    return User.objects.create(
        telegram_id=900000020,
        chat_id=900000020,
        password="x",
    )


@pytest.fixture
def category() -> object:
    """Create a leaf category for ad fixtures."""
    from apps.categories.models import Category

    return Category.objects.create(
        name="Test Category",
        slug="test-category",
    )


@pytest.fixture
def city() -> object:
    """Create a city for ad fixtures."""
    from apps.locations.models import City

    return City.objects.create(
        country_code="ME",
        name="Test City",
        region="Test Region",
        slug="test-city",
    )


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
    from apps.ads.models import Ad
    from apps.core.enums import AdStatus

    from telegram_bot.services.media import generate_storage_key

    key = image_key or generate_storage_key()

    ad = Ad.objects.create(
        user=seller,
        title="Test Ad",
        description="Test description",
        category=category,
        city=city,
        category_name=category.name,
        status=AdStatus.PUBLISHED,
        published_at=timezone.now(),
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

    def test_backfill_generates_all_thumbnails(self, seller, category, city, isolated_media_root):
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
            seller, category, city, isolated_media_root,
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

    def test_backfill_batch_processing(self, seller, category, city, isolated_media_root):
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