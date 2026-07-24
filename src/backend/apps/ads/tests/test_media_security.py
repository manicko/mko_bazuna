"""
Media security tests for Mko Bazuna (MED-008).

Verifies:
- Media access control: unpublished/withdrawn ad photos are not served
- EXIF stripping: metadata is removed after store
- Physical deletion: delete_photo unlinks files from MEDIA_ROOT
- Path-traversal keys are rejected by the media_gate view

Uses an isolated temporary MEDIA_ROOT to avoid side effects.
"""

from collections.abc import Generator
import io
import tempfile
from pathlib import Path

import pytest
from PIL import Image
from PIL.ExifTags import Base as ExifBase
from django.test import Client, override_settings
from django.utils import timezone

from telegram_bot.services.media import delete_photo, generate_storage_key, strip_photo_exif

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
        telegram_id=900000010,
        chat_id=900000010,
        password="x",
    )


@pytest.fixture
def staff_user() -> object:
    """Create a staff user for moderator access tests."""
    from apps.users.models import User

    return User.objects.create(
        telegram_id=900000011,
        chat_id=900000011,
        password="x",
        is_staff=True,
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


@pytest.fixture
def jpeg_with_exif() -> bytes:
    """Generate a small JPEG image with embedded EXIF metadata."""
    img = Image.new("RGB", (100, 100), color="red")
    exif_dict = {
        ExifBase.Make: "CameraMaker",
        ExifBase.Model: "CameraModel",
        ExifBase.GPSInfo: b"\x02\x03\x04\x05",  # Mock GPS data
    }
    exif_bytes = img.getexif()
    for tag, value in exif_dict.items():
        exif_bytes[tag] = value
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif_bytes.tobytes())
    return buf.getvalue()


@pytest.fixture
def clean_jpeg() -> bytes:
    """Generate a small clean JPEG image with no EXIF metadata."""
    img = Image.new("RGB", (100, 100), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Helper — create a published ad with one image
# ---------------------------------------------------------------------------


def _create_ad_with_image(
    seller: object,
    category: object,
    city: object,
    image_key: str | None = None,
    status: object | None = None,
    file_bytes: bytes | None = None,
    media_root: Path | None = None,
) -> tuple[object, object, str]:
    """Create an Ad + AdImage, optionally writing a physical file to MEDIA_ROOT.

    Returns:
        Tuple of (ad, ad_image, image_key).
    """
    from apps.ads.models import Ad, AdImage
    from apps.core.enums import AdStatus

    actual_status = status or AdStatus.PUBLISHED
    key = image_key or generate_storage_key()

    ad = Ad.objects.create(
        user=seller,
        title="Test Ad",
        description="Test description",
        category=category,
        city=city,
        category_name=category.name,
        status=actual_status,
        published_at=timezone.now() if actual_status == AdStatus.PUBLISHED else None,
    )

    ad_image = AdImage.objects.create(
        ad=ad,
        image=key,
    )

    # Write physical file if media_root is given
    if media_root is not None and file_bytes is not None:
        file_path = media_root / key
        file_path.write_bytes(file_bytes)

    return ad, ad_image, key


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------


class TestMediaAccessControl:
    """Media access gate (MED-001) — unpublished/withdrawn ad photos blocked."""

    def test_published_ad_returns_redirect(self, seller, category, city, isolated_media_root):
        """PUBLISHED ad images get X-Accel-Redirect header."""
        key = generate_storage_key()
        _create_ad_with_image(seller, category, city, image_key=key)
        client = Client()
        url = f"/ads/media/{key}"
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            response = client.get(url)
        assert response.status_code == 200
        assert response.headers.get("X-Accel-Redirect") == f"/protected-media/{key}"

    def test_draft_ad_returns_forbidden(self, seller, category, city, isolated_media_root):
        """DRAFT ad images return 403 Forbidden."""
        from apps.core.enums import AdStatus

        key = generate_storage_key()
        _create_ad_with_image(seller, category, city, image_key=key, status=AdStatus.DRAFT)
        client = Client()
        url = f"/ads/media/{key}"
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            response = client.get(url)
        assert response.status_code == 403

    def test_on_moderation_ad_returns_forbidden(self, seller, category, city, isolated_media_root):
        """ON_MODERATION ad images return 403 Forbidden."""
        from apps.core.enums import AdStatus

        key = generate_storage_key()
        _create_ad_with_image(
            seller, category, city, image_key=key, status=AdStatus.ON_MODERATION
        )
        client = Client()
        url = f"/ads/media/{key}"
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            response = client.get(url)
        assert response.status_code == 403

    def test_deleted_ad_returns_forbidden(self, seller, category, city, isolated_media_root):
        """DELETED ad images return 403 Forbidden."""
        from apps.core.enums import AdStatus

        key = generate_storage_key()
        _create_ad_with_image(seller, category, city, image_key=key, status=AdStatus.DELETED)
        client = Client()
        url = f"/ads/media/{key}"
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            response = client.get(url)
        assert response.status_code == 403

    def test_staff_can_view_any_status(self, seller, staff_user, category, city, isolated_media_root):
        """Staff users can view images for any ad status."""
        from apps.core.enums import AdStatus

        from django.test import Client

        key = generate_storage_key()
        _create_ad_with_image(
            seller, category, city, image_key=key, status=AdStatus.ON_MODERATION
        )
        client = Client()
        # Log in as staff
        client.force_login(staff_user)
        url = f"/ads/media/{key}"
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            response = client.get(url)
        assert response.status_code == 200
        assert response.headers.get("X-Accel-Redirect") == f"/protected-media/{key}"

    def test_non_existent_key_returns_404(self, isolated_media_root):
        """Non-existent image key returns 404."""
        client = Client()
        url = "/ads/media/nonexistent-uuid.jpg"
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            response = client.get(url)
        assert response.status_code == 404


class TestExifStripping:
    """EXIF stripping (MED-002) — metadata is removed on store."""

    def test_strip_photo_exif_removes_make(self, jpeg_with_exif):
        """EXIF Make tag is removed after strip_photo_exif."""
        cleaned = strip_photo_exif(jpeg_with_exif)
        img = Image.open(io.BytesIO(cleaned))
        exif_data = img.getexif()
        assert ExifBase.Make not in exif_data

    def test_strip_photo_exif_removes_model(self, jpeg_with_exif):
        """EXIF Model tag is removed after strip_photo_exif."""
        cleaned = strip_photo_exif(jpeg_with_exif)
        img = Image.open(io.BytesIO(cleaned))
        exif_data = img.getexif()
        assert ExifBase.Model not in exif_data

    def test_strip_photo_exif_removes_gps(self, jpeg_with_exif):
        """EXIF GPSInfo tag is removed after strip_photo_exif."""
        cleaned = strip_photo_exif(jpeg_with_exif)
        img = Image.open(io.BytesIO(cleaned))
        exif_data = img.getexif()
        assert ExifBase.GPSInfo not in exif_data

    def test_strip_photo_exif_preserves_image(self, clean_jpeg):
        """Clean JPEG without EXIF is preserved unchanged."""
        import io

        from PIL import Image

        cleaned = strip_photo_exif(clean_jpeg)
        # Re-open and verify it's still a valid image
        img = Image.open(io.BytesIO(cleaned))
        assert img.size == (100, 100)
        assert img.mode == "RGB"

    def test_strip_photo_exif_valid_jpeg(self, jpeg_with_exif):
        """Output of strip_photo_exif is a valid JPEG."""
        cleaned = strip_photo_exif(jpeg_with_exif)
        assert cleaned.startswith(b"\xff\xd8\xff")
        img = Image.open(io.BytesIO(cleaned))
        img.verify()  # This raises on corrupt data


class TestPhysicalDeletion:
    """Physical file deletion (MED-003) — delete_photo removes files from disk."""

    def test_delete_photo_removes_file(self, isolated_media_root):
        """delete_photo removes the file from MEDIA_ROOT."""
        key = generate_storage_key()
        file_path = isolated_media_root / key
        file_path.write_bytes(b"test data")
        assert file_path.exists()

        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            delete_photo(key)

        assert not file_path.exists()

    def test_delete_photo_missing_file_succeeds(self, isolated_media_root):
        """delete_photo succeeds silently when file does not exist."""
        key = generate_storage_key()
        # File does not exist — should not raise
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            delete_photo(key)  # Should not raise

    def test_delete_photo_multiple_files(self, isolated_media_root):
        """delete_photo can remove multiple files independently."""
        key1 = generate_storage_key()
        key2 = generate_storage_key()
        (isolated_media_root / key1).write_bytes(b"data1")
        (isolated_media_root / key2).write_bytes(b"data2")

        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            delete_photo(key1)
            delete_photo(key2)

        assert not (isolated_media_root / key1).exists()
        assert not (isolated_media_root / key2).exists()


class TestPathTraversalRejection:
    """Path-traversal keys are rejected by the media_gate view."""

    def test_path_traversal_up_dir(self, isolated_media_root):
        """Path traversal with '../' returns 404."""
        client = Client()
        url = "/ads/media/../../../etc/passwd"
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            response = client.get(url)
        # The key won't match any AdImage in DB -> 404
        assert response.status_code == 404

    def test_path_traversal_encoded(self, isolated_media_root):
        """URL-encoded path traversal returns 404."""
        client = Client()
        url = "/ads/media/%2e%2e%2f%2e%2e%2fetc%2fpasswd"
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            response = client.get(url)
        assert response.status_code == 404

    def test_path_traversal_with_slash_prefix(self, isolated_media_root):
        """Absolute path-like key returns 404."""
        client = Client()
        url = "/ads/media//etc/passwd"
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            response = client.get(url)
        assert response.status_code == 404

    def test_path_traversal_with_null_byte(self, isolated_media_root):
        """Null byte injection in image key returns 404."""
        client = Client()
        url = "/ads/media/../../../etc/passwd%00.jpg"
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            response = client.get(url)
        assert response.status_code == 404

    def test_random_key_does_not_resolve(self, isolated_media_root):
        """Random non-existent key returns 404 (not a path traversal)."""
        client = Client()
        url = "/ads/media/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.jpg"
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            response = client.get(url)
        assert response.status_code == 404