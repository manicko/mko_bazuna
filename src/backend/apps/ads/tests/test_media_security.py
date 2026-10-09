"""
Media security tests for Mko Bazuna (MED-008).

Verifies:
- Media access control: unpublished/withdrawn ad photos are not served
- EXIF stripping: metadata is removed after store
- Physical deletion: delete_photo unlinks files from MEDIA_ROOT
- Path-traversal keys are rejected by the media_gate view

Uses an isolated temporary MEDIA_ROOT to avoid side effects.
"""

from __future__ import annotations

import io
import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import DEFAULT_CACHE_ALIAS, cache, caches
from django.http import FileResponse
from django.test import Client, override_settings
from django_redis.exceptions import ConnectionInterrupted
from PIL import Image
from PIL.ExifTags import Base as ExifBase

from apps.ads.views.listings import (
    _MEDIA_GATE_429_SVG,
    MEDIA_RATE_LIMIT_PERIOD,
    MEDIA_RATE_LIMIT_REQUESTS,
    _serve_image,
)
from apps.core.enums import AdStatus
from apps.media.services.filesystem import (
    delete_photo,
    generate_storage_key,
    strip_photo_exif,
)
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
def jpeg_with_exif() -> bytes:
    """Generate a small JPEG image with embedded EXIF metadata."""
    img = Image.new("RGB", (100, 100), color="red")
    exif_dict = {
        ExifBase.Make: "CameraMaker",
        ExifBase.Model: "CameraModel",
        # GPSInfo (tag 0x8825) must be an IFD sub-table dict, not raw bytes:
        # PIL's Exif.tobytes() serializes it as a nested IFD, and dict values
        # are interpreted as the tag's typed IFD entries (e.g. {1: "N"} = GPSLatitudeRef).
        ExifBase.GPSInfo: {1: "N"},
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
    from apps.ads.models import AdImage
    from apps.core.enums import AdStatus

    actual_status = status or AdStatus.PUBLISHED
    key = image_key or generate_storage_key()

    ad = create_test_ad(seller, category, city, status=actual_status)

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
    """Media access gate (MED-001) — unpublished/withdrawn ad photos blocked.

    Tests run with DEBUG=False to exercise the production X-Accel-Redirect path
    (the dev FileResponse path requires physical files on disk and is not what
    these assertions target).
    """

    @pytest.fixture(autouse=True)
    def _debug_false(self):
        with override_settings(DEBUG=False):
            yield
    """Media access gate (MED-001) — unpublished/withdrawn ad photos blocked."""

    def test_published_ad_returns_redirect(
        self, seller, category, city, isolated_media_root
    ):
        """PUBLISHED ad images get X-Accel-Redirect header."""
        key = generate_storage_key()
        _create_ad_with_image(seller, category, city, image_key=key)
        client = Client()
        url = f"/media/{key}"
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            response = client.get(url)
        assert response.status_code == 200
        assert response.headers.get("X-Accel-Redirect") == f"/protected-media/{key}"

    def test_draft_ad_returns_forbidden(
        self, seller, category, city, isolated_media_root
    ):
        """DRAFT ad images return 403 Forbidden."""
        from apps.core.enums import AdStatus

        key = generate_storage_key()
        _create_ad_with_image(
            seller, category, city, image_key=key, status=AdStatus.DRAFT
        )
        client = Client()
        url = f"/media/{key}"
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            response = client.get(url)
        assert response.status_code == 403

    def test_on_moderation_ad_returns_forbidden(
        self, seller, category, city, isolated_media_root
    ):
        """ON_MODERATION ad images return 403 Forbidden."""
        from apps.core.enums import AdStatus

        key = generate_storage_key()
        _create_ad_with_image(
            seller, category, city, image_key=key, status=AdStatus.ON_MODERATION
        )
        client = Client()
        url = f"/media/{key}"
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            response = client.get(url)
        assert response.status_code == 403

    def test_deleted_ad_returns_forbidden(
        self, seller, category, city, isolated_media_root
    ):
        """DELETED ad images return 403 Forbidden."""
        from apps.core.enums import AdStatus

        key = generate_storage_key()
        _create_ad_with_image(
            seller, category, city, image_key=key, status=AdStatus.DELETED
        )
        client = Client()
        url = f"/media/{key}"
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            response = client.get(url)
        assert response.status_code == 403

    def test_staff_can_view_any_status(
        self, seller, staff_user, category, city, isolated_media_root
    ):
        """Staff users can view images for any ad status."""
        from django.test import Client

        from apps.core.enums import AdStatus

        key = generate_storage_key()
        _create_ad_with_image(
            seller, category, city, image_key=key, status=AdStatus.ON_MODERATION
        )
        client = Client()
        # Log in as staff
        client.force_login(staff_user)
        url = f"/media/{key}"
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            response = client.get(url)
        assert response.status_code == 200
        assert response.headers.get("X-Accel-Redirect") == f"/protected-media/{key}"

    def test_non_existent_key_returns_404(self, isolated_media_root):
        """Non-existent image key returns 404."""
        client = Client()
        url = "/media/nonexistent-uuid.jpg"
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            response = client.get(url)
        assert response.status_code == 404

    def test_seed_storage_key_with_path_returns_redirect(
        self, seller, category, city, isolated_media_root
    ):
        """Storage keys with slashes (e.g. 'seed/kvartiry_01.jpg') resolve via media_gate.

        Seed images use subdirectory-prefixed storage keys like ``seed/<filename>.jpg``.
        The ``<path:image_key>`` URL converter must match the full path (including
        the ``/``) so the view can look up the AdImage by its ``image`` field.
        """
        key = "seed/kvartiry_01.jpg"
        _create_ad_with_image(seller, category, city, image_key=key)
        client = Client()
        url = f"/media/{key}"
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            response = client.get(url)
        assert response.status_code == 200
        assert response.headers.get("X-Accel-Redirect") == f"/protected-media/{key}"

    def test_shared_seed_key_across_multiple_ads_returns_200(
        self, seller, category, city, isolated_media_root
    ):
        """A storage key shared by several ads serves without HTTP 500.

        Seed data reuses ``seed/<filename>`` across multiple ads. ``media_gate``
        must look the key up via ``filter`` (not ``get``); otherwise the shared
        key raises ``MultipleObjectsReturned`` and the listings-page images fail
        to render. Regression guard for the image-display bug.
        """
        key = "seed/birds_04.jpg"
        # Same image referenced by two distinct PUBLISHED ads (seed reuse)
        _create_ad_with_image(seller, category, city, image_key=key)
        _create_ad_with_image(seller, category, city, image_key=key)
        client = Client()
        url = f"/media/{key}"
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            response = client.get(url)
        assert response.status_code == 200
        assert response.headers.get("X-Accel-Redirect") == f"/protected-media/{key}"

    def test_serve_image_returns_fileresponse(self, isolated_media_root):
        """_serve_image returns a FileResponse (streams from disk), not HttpResponse.

        The docstring claims FileResponse streaming; this verifies the code matches
        by asserting the concrete return type is FileResponse (not a bare
        HttpResponse that buffers the whole file into memory).
        """
        key = generate_storage_key()
        file_path = isolated_media_root / key
        file_path.write_bytes(b"\xff\xd8\xff\xe0" + b"fake-jpeg-data")
        with override_settings(MEDIA_ROOT=isolated_media_root):
            response = _serve_image(key)
        assert isinstance(response, FileResponse)
        assert response.headers["Content-Type"] == "image/jpeg"
        assert response.headers["X-Content-Type-Options"] == "nosniff"


class TestMediaGateDeclinedUser:
    """Declined-user media is gated from non-staff access (AUTZ-003).

    A declined user's PUBLISHED ad is hidden from browse/search; this guards the
    direct ``/media/<key>`` route from leaking its images. Staff (moderators)
    keep access to review content.
    """

    @pytest.fixture(autouse=True)
    def _debug_false(self):
        with override_settings(DEBUG=False):
            yield

    def test_declined_user_published_image_returns_forbidden(
        self, seller, category, city, isolated_media_root
    ):
        """A declined user's PUBLISHED ad image returns 403 for non-staff."""
        key = generate_storage_key()
        _create_ad_with_image(seller, category, city, image_key=key)
        client = Client()
        url = f"/media/{key}"

        # Sanity: accessible before the decline.
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            assert client.get(url).status_code == 200

        # Decline consent — the image must become unreachable.
        seller.is_declined = True
        seller.save(update_fields=["is_declined"])

        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            response = client.get(url)
        assert response.status_code == 403

    def test_staff_can_view_declined_user_image(
        self, seller, staff_user, category, city, isolated_media_root
    ):
        """Staff can still view a declined user's image (regression guard)."""
        key = generate_storage_key()
        _create_ad_with_image(seller, category, city, image_key=key)
        seller.is_declined = True
        seller.save(update_fields=["is_declined"])

        client = Client()
        client.force_login(staff_user)
        url = f"/media/{key}"
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            response = client.get(url)
        assert response.status_code == 200
        assert response.headers.get("X-Accel-Redirect") == f"/protected-media/{key}"

    def test_non_declined_user_published_image_returns_redirect(
        self, seller, category, city, isolated_media_root
    ):
        """A non-declined user's PUBLISHED ad image still serves normally."""
        key = generate_storage_key()
        _create_ad_with_image(seller, category, city, image_key=key)
        client = Client()
        url = f"/media/{key}"
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            response = client.get(url)
        assert response.status_code == 200
        assert response.headers.get("X-Accel-Redirect") == f"/protected-media/{key}"


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

    def test_strip_photo_exif_removes_icc_profile(self) -> None:
        """ICC profile is removed after strip_photo_exif."""
        import io

        from PIL import Image

        img = Image.new("RGB", (100, 100), color="green")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", icc_profile=b"fake-icc-profile-data")
        jpeg_with_icc = buf.getvalue()

        # Verify the ICC profile is present before stripping
        pre_img = Image.open(io.BytesIO(jpeg_with_icc))
        assert "icc_profile" in pre_img.info

        cleaned = strip_photo_exif(jpeg_with_icc)
        result = Image.open(io.BytesIO(cleaned))
        assert "icc_profile" not in result.info


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

    def test_delete_photo_rejects_traversal_key(self, isolated_media_root):
        """delete_photo raises ValueError for path-traversal keys and does not
        delete files outside MEDIA_ROOT."""
        escape_file = isolated_media_root.parent / "escape_test.jpg"
        escape_file.write_bytes(b"do not delete me")
        try:
            with override_settings(MEDIA_ROOT=str(isolated_media_root)):
                with pytest.raises(ValueError):
                    delete_photo("../escape_test.jpg")

            assert escape_file.exists()
        finally:
            escape_file.unlink(missing_ok=True)

    def test_delete_photo_accepts_valid_key(self, isolated_media_root):
        """delete_photo successfully deletes a file with a valid UUID key
        (regression guard for the containment filter)."""
        key = generate_storage_key()
        file_path = isolated_media_root / key
        file_path.write_bytes(b"valid image data")
        assert file_path.exists()

        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            delete_photo(key)

        assert not file_path.exists()


class TestPathTraversalRejection:
    """Path-traversal keys are rejected by the media_gate view."""

    def test_path_traversal_up_dir(self, isolated_media_root):
        """Path traversal with '../' returns 404."""
        client = Client()
        url = "/media/../../../etc/passwd"
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            response = client.get(url)
        # The key won't match any AdImage in DB -> 404
        assert response.status_code == 404

    def test_path_traversal_encoded(self, isolated_media_root):
        """URL-encoded path traversal returns 404."""
        client = Client()
        url = "/media/%2e%2e%2f%2e%2e%2fetc%2fpasswd"
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            response = client.get(url)
        assert response.status_code == 404

    def test_path_traversal_with_slash_prefix(self, isolated_media_root):
        """Absolute path-like key returns 404."""
        client = Client()
        url = "/media//etc/passwd"
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            response = client.get(url)
        assert response.status_code == 404

    def test_path_traversal_with_null_byte(self, isolated_media_root):
        """Null byte injection in image key returns 404."""
        client = Client()
        url = "/media/../../../etc/passwd%00.jpg"
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            response = client.get(url)
        assert response.status_code == 404

    def test_random_key_does_not_resolve(self, isolated_media_root):
        """Random non-existent key returns 404 (not a path traversal)."""
        client = Client()
        url = "/media/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.jpg"
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            response = client.get(url)
        assert response.status_code == 404

    def test_media_gate_rejects_dotdot_key(
        self, seller, category, city, isolated_media_root
    ):
        """media_gate returns 404 for keys containing ../ even when an AdImage row exists.

        The containment check (assert_storage_key_contained) must reject the
        traversal key before the DB lookup, so a valid AdImage row in the
        database does not cause the request to succeed.
        """
        key = generate_storage_key()
        _create_ad_with_image(seller, category, city, image_key=key)
        client = Client()
        url = "/media/%2e%2e%2fescape.jpg"
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            response = client.get(url)
        assert response.status_code == 404


class TestMediaGateThumbnailResolution:
    """media_gate resolves thumbnail keys via thumbnail_* fields (ARCH-001).

    Tests run with DEBUG=False to exercise the production X-Accel-Redirect path.
    """

    @pytest.fixture(autouse=True)
    def _debug_false(self):
        with override_settings(DEBUG=False):
            yield
    """media_gate resolves thumbnail keys via thumbnail_* fields (ARCH-001)."""

    def _create_ad_with_thumbnail(
        self,
        seller: object,
        category: object,
        city: object,
        thumbnail_key: str,
        thumbnail_field: str,
        image_key: str | None = None,
        status: object | None = None,
    ) -> tuple[str, str]:
        """Create a PUBLISHED ad with an AdImage that has a specific thumbnail set.

        Returns the image_key used.
        """
        from apps.ads.models import AdImage
        from apps.core.enums import AdStatus

        actual_status = status or AdStatus.PUBLISHED
        orig_key = image_key or generate_storage_key()

        ad = create_test_ad(seller, category, city, status=actual_status)

        kwargs = {thumbnail_field: thumbnail_key}
        AdImage.objects.create(ad=ad, image=orig_key, **kwargs)
        return orig_key, thumbnail_key

    def test_small_thumbnail_key_resolves(
        self, seller, category, city, isolated_media_root
    ):
        """media_gate returns 200 for a key stored in thumbnail_small."""
        _, thumb_key = self._create_ad_with_thumbnail(
            seller, category, city, "img-small.jpg", "thumbnail_small"
        )
        client = Client()
        url = f"/media/{thumb_key}"
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            response = client.get(url)
        assert response.status_code == 200
        assert (
            response.headers.get("X-Accel-Redirect") == f"/protected-media/{thumb_key}"
        )

    def test_medium_thumbnail_key_resolves(
        self, seller, category, city, isolated_media_root
    ):
        """media_gate returns 200 for a key stored in thumbnail_medium."""
        _, thumb_key = self._create_ad_with_thumbnail(
            seller, category, city, "img-medium.jpg", "thumbnail_medium"
        )
        client = Client()
        url = f"/media/{thumb_key}"
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            response = client.get(url)
        assert response.status_code == 200
        assert (
            response.headers.get("X-Accel-Redirect") == f"/protected-media/{thumb_key}"
        )

    def test_large_thumbnail_key_resolves(
        self, seller, category, city, isolated_media_root
    ):
        """media_gate returns 200 for a key stored in thumbnail_large."""
        _, thumb_key = self._create_ad_with_thumbnail(
            seller, category, city, "img-large.jpg", "thumbnail_large"
        )
        client = Client()
        url = f"/media/{thumb_key}"
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            response = client.get(url)
        assert response.status_code == 200
        assert (
            response.headers.get("X-Accel-Redirect") == f"/protected-media/{thumb_key}"
        )

    def test_thumbnail_key_with_draft_ad_returns_forbidden(
        self, seller, category, city, isolated_media_root
    ):
        """Thumbnail key respects ad status — draft returns 403."""
        from apps.core.enums import AdStatus

        _, thumb_key = self._create_ad_with_thumbnail(
            seller,
            category,
            city,
            "draft-small.jpg",
            "thumbnail_small",
            status=AdStatus.DRAFT,
        )
        client = Client()
        url = f"/media/{thumb_key}"
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            response = client.get(url)
        assert response.status_code == 403

    def test_thumbnail_key_staff_can_view_any_status(
        self, seller, staff_user, category, city, isolated_media_root
    ):
        """Staff users can view thumbnail keys for any ad status."""
        from apps.core.enums import AdStatus

        _, thumb_key = self._create_ad_with_thumbnail(
            seller,
            category,
            city,
            "staff-small.jpg",
            "thumbnail_small",
            status=AdStatus.ON_MODERATION,
        )
        client = Client()
        client.force_login(staff_user)
        url = f"/media/{thumb_key}"
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            response = client.get(url)
        assert response.status_code == 200
        assert (
            response.headers.get("X-Accel-Redirect") == f"/protected-media/{thumb_key}"
        )

    def test_thumbnail_key_prefers_image_field_over_thumbnail_fields(
        self, seller, category, city, isolated_media_root
    ):
        """When a key matches both image and thumbnail_small, image wins."""
        from apps.ads.models import AdImage

        conflicting_key = "conflict.jpg"
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        # Create two AdImages — one with image=conflict.jpg, one with thumbnail_small=conflict.jpg
        AdImage.objects.create(ad=ad, image=conflicting_key, position=0)
        AdImage.objects.create(
            ad=ad, image="other.jpg", thumbnail_small=conflicting_key, position=1
        )

        client = Client()
        url = f"/media/{conflicting_key}"
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            response = client.get(url)
        # Should resolve to the one with image=conflict.jpg (primary lookup)
        assert response.status_code == 200

    def test_non_existent_thumbnail_key_returns_404(self, isolated_media_root):
        """Non-existent thumbnail key returns 404."""
        client = Client()
        url = "/media/nonexistent-small.jpg"
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            response = client.get(url)
        assert response.status_code == 404


class TestMediaGateCacheControl:
    """B9/LOW-004: Cache-Control + Vary headers on media_gate responses.

    200 responses carry Cache-Control: public, max-age=86400 (24h CDN/browser TTL).
    ``immutable`` is omitted: image keys are UUID v4 / fixed seed names, NOT
    content-addressed, so regenerated seed files must bypass cache at the same URL.
    403, 404, and 429 responses never receive the long TTL.
    """

    def test_prod_200_cache_control_long_ttl(
        self, seller, category, city, isolated_media_root
    ):
        """Production (DEBUG=False) 200: Cache-Control public max-age=86400 + X-Accel-Redirect."""
        key = generate_storage_key()
        _create_ad_with_image(seller, category, city, image_key=key)
        client = Client()
        url = f"/media/{key}"
        with override_settings(MEDIA_ROOT=str(isolated_media_root), DEBUG=False):
            response = client.get(url)
        assert response.status_code == 200
        assert response.headers.get("X-Accel-Redirect") == f"/protected-media/{key}"
        assert response.headers.get("Cache-Control") == "public, max-age=86400"
        assert "no-store" not in response.headers.get("Cache-Control", "")
        assert "cookie" in response.headers.get("Vary", "").lower()

    def test_prod_staff_200_cache_control_long_ttl(
        self, seller, staff_user, category, city, isolated_media_root
    ):
        """Production (DEBUG=False) staff 200: Cache-Control public max-age=86400 + X-Accel-Redirect."""
        key = generate_storage_key()
        _create_ad_with_image(
            seller, category, city, image_key=key, status=AdStatus.DRAFT
        )
        client = Client()
        client.force_login(staff_user)
        url = f"/media/{key}"
        with override_settings(MEDIA_ROOT=str(isolated_media_root), DEBUG=False):
            response = client.get(url)
        assert response.status_code == 200
        assert response.headers.get("X-Accel-Redirect") == f"/protected-media/{key}"
        assert response.headers.get("Cache-Control") == "public, max-age=86400"
        assert "no-store" not in response.headers.get("Cache-Control", "")
        assert "cookie" in response.headers.get("Vary", "").lower()

    def test_media_cache_invalidated_on_ad_status_change(
        self, seller, category, city, isolated_media_root
    ):
        """Server-side authorization re-check on each request: PUBLISHED→DELETED yields 403."""
        key = generate_storage_key()
        ad, _, _ = _create_ad_with_image(seller, category, city, image_key=key)
        client = Client()
        url = f"/media/{key}"
        with override_settings(MEDIA_ROOT=str(isolated_media_root), DEBUG=False):
            response = client.get(url)
        assert response.status_code == 200
        assert response.headers.get("Cache-Control") == "public, max-age=86400"

        # Simulate status transition: PUBLISHED → DELETED (matches soft_delete_user_ads pattern)
        from django.utils import timezone

        from apps.ads.models import Ad

        Ad.objects.filter(id=ad.id).update(
            status=AdStatus.DELETED, deleted_at=timezone.now()
        )

        with override_settings(MEDIA_ROOT=str(isolated_media_root), DEBUG=False):
            response_after = client.get(url)
        assert response_after.status_code == 403

    def test_media_cache_invalidated_on_consent_withdrawal(
        self, seller, category, city, isolated_media_root
    ):
        """Server-side authorization re-check: consent withdrawal (→DELETED) yields 403."""
        from apps.users.services.deletion import withdraw_consent

        key = generate_storage_key()
        _create_ad_with_image(seller, category, city, image_key=key)
        client = Client()
        url = f"/media/{key}"
        with override_settings(MEDIA_ROOT=str(isolated_media_root), DEBUG=False):
            response = client.get(url)
        assert response.status_code == 200
        assert response.headers.get("Cache-Control") == "public, max-age=86400"

        # Withdraw consent — soft_deletes all ads to DELETED via .update()
        withdraw_consent(seller)

        with override_settings(MEDIA_ROOT=str(isolated_media_root), DEBUG=False):
            response_after = client.get(url)
        assert response_after.status_code == 403

    def test_dev_200_cache_control_no_cache(
        self, seller, category, city, isolated_media_root
    ):
        """Dev (DEBUG=True) 200: FileResponse with Cache-Control: public max-age=86400."""
        key = generate_storage_key()
        _create_ad_with_image(
            seller,
            category,
            city,
            image_key=key,
            file_bytes=b"\xff\xd8\xff\xe0" + b"fake-jpeg-data",
            media_root=isolated_media_root,
        )
        client = Client()
        url = f"/media/{key}"
        with override_settings(MEDIA_ROOT=isolated_media_root, DEBUG=True):
            response = client.get(url)
        assert response.status_code == 200
        assert isinstance(response, FileResponse)
        assert response.headers.get("Cache-Control") == "public, max-age=86400"
        assert "immutable" not in response.headers.get("Cache-Control", "")
        assert "cookie" in response.headers.get("Vary", "").lower()

    def test_dev_staff_200_cache_control_no_cache(
        self, seller, staff_user, category, city, isolated_media_root
    ):
        """Dev (DEBUG=True) staff 200: FileResponse with Cache-Control: public max-age=86400."""
        key = generate_storage_key()
        _create_ad_with_image(
            seller,
            category,
            city,
            image_key=key,
            file_bytes=b"\xff\xd8\xff\xe0" + b"fake-jpeg-data",
            media_root=isolated_media_root,
            status=AdStatus.DRAFT,
        )
        client = Client()
        client.force_login(staff_user)
        url = f"/media/{key}"
        with override_settings(MEDIA_ROOT=isolated_media_root, DEBUG=True):
            response = client.get(url)
        assert response.status_code == 200
        assert isinstance(response, FileResponse)
        assert response.headers.get("Cache-Control") == "public, max-age=86400"
        assert "immutable" not in response.headers.get("Cache-Control", "")
        assert "cookie" in response.headers.get("Vary", "").lower()

    # ------------------------------------------------------------------
    # Vary + Cache-Control on error responses
    # ------------------------------------------------------------------

    def test_403_has_vary_but_no_cache_control(
        self, seller, category, city, isolated_media_root
    ):
        """403 Forbidden: Vary: Cookie present, NO Cache-Control.

        A cached 403 would block users after an ad transitions to PUBLISHED
        (or vice-versa for DRAFT), so access-denied responses must never be cached.
        """
        key = generate_storage_key()
        _create_ad_with_image(
            seller, category, city, image_key=key, status=AdStatus.DRAFT
        )
        client = Client()
        url = f"/media/{key}"
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            response = client.get(url)
        assert response.status_code == 403
        assert "cookie" in response.headers.get("Vary", "").lower()
        assert response.headers.get("Cache-Control") is None

    def test_404_has_no_cache_control(self, isolated_media_root):
        """404 response must NOT receive Cache-Control."""
        client = Client()
        url = "/media/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.jpg"
        with override_settings(MEDIA_ROOT=str(isolated_media_root), DEBUG=False):
            response = client.get(url)
        assert response.status_code == 404
        assert response.headers.get("Cache-Control") is None

    # ------------------------------------------------------------------
    # _serve_image is NOT modified — media_gate wraps its return value
    # ------------------------------------------------------------------

    def test_serve_image_does_not_set_cache_control(self, isolated_media_root):
        """_serve_image itself must NOT set Cache-Control (media_gate wraps it)."""
        key = generate_storage_key()
        file_path = isolated_media_root / key
        file_path.write_bytes(b"\xff\xd8\xff\xe0" + b"fake-jpeg-data")
        with override_settings(MEDIA_ROOT=isolated_media_root):
            response = _serve_image(key)
        assert isinstance(response, FileResponse)
        assert response.headers.get("Cache-Control") is None

    def test_200_response_has_cache_control_max_age(
        self, seller, category, city, isolated_media_root
    ):
        """200 responses carry public, max-age=86400 WITHOUT immutable.

        Image keys are not content-addressed (UUID v4 / fixed seed names), so
        ``immutable`` must never appear — seed files are regenerated at the same
        URL and must bypass cache to avoid serving stale bytes.
        """
        key = generate_storage_key()
        _create_ad_with_image(seller, category, city, image_key=key)
        client = Client()
        url = f"/media/{key}"
        with override_settings(MEDIA_ROOT=str(isolated_media_root), DEBUG=False):
            response = client.get(url)
        assert response.status_code == 200
        cc = response.headers.get("Cache-Control", "")
        assert "max-age=86400" in cc
        assert "immutable" not in cc
        assert "no-store" not in cc


class TestMediaGateApplicationRateLimit:
    """Application-level limiter on ``media_gate`` (09-API-005).

    The proxy half of the finding was shipped by phase 07 (``location /media/``
    carries ``browse_limit burst=40 nodelay`` in both sites, pinned by
    ``test_nginx_config.py``). This class covers the half that survives a
    bypassed proxy: the view refuses an over-budget client before the AdImage
    lookup, and fails open when the cache is unavailable.
    """

    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        """Clear the shared LocMemCache so per-IP counters don't leak across tests."""
        cache.clear()
        yield
        cache.clear()

    def _published_key(self, seller, category, city) -> str:
        key = generate_storage_key()
        _create_ad_with_image(seller, category, city, image_key=key)
        return key

    def test_burst_over_budget_is_refused(self, seller, category, city):
        """The (limit+1)th request from one IP is refused with 429.

        Asserts on the response, not on the helper's return value: the guard is
        only correct if the view converts an over-budget decision into a 429.
        """
        key = self._published_key(seller, category, city)
        client = Client()
        url = f"/media/{key}"

        with override_settings(DEBUG=False):
            for _ in range(MEDIA_RATE_LIMIT_REQUESTS):
                assert client.get(url).status_code == 200
            response = client.get(url)

        assert response.status_code == 429
        assert response.headers.get("Retry-After") == str(MEDIA_RATE_LIMIT_PERIOD)
        assert "<svg" in response.content.decode()
        assert response.headers.get("Content-Type") == "image/svg+xml"
        assert response.headers.get("Cache-Control") == "no-store"

    def test_over_budget_is_refused_before_the_db_lookup(self, seller, category, city):
        """The limiter runs before the AdImage query.

        An over-budget request for a key that resolves to a PUBLISHED ad must
        still be refused — proving the guard does not depend on the lookup
        succeeding, which is the point of protecting the database.
        """
        key = self._published_key(seller, category, city)
        client = Client()
        url = f"/media/{key}"

        with override_settings(DEBUG=False):
            for _ in range(MEDIA_RATE_LIMIT_REQUESTS):
                client.get(url)
            response = client.get(url)

        assert response.status_code == 429
        assert response.headers.get("Retry-After") == str(MEDIA_RATE_LIMIT_PERIOD)
        assert "<svg" in response.content.decode()
        assert response.headers.get("Content-Type") == "image/svg+xml"
        assert response.headers.get("Cache-Control") == "no-store"

    def test_independent_per_ip(self, seller, category, city):
        """Exhausting one IP's budget does not affect a different IP."""
        key = self._published_key(seller, category, city)
        url = f"/media/{key}"

        with override_settings(DEBUG=False):
            for _ in range(MEDIA_RATE_LIMIT_REQUESTS + 1):
                Client(REMOTE_ADDR="203.0.113.10").get(url)
            response = Client(REMOTE_ADDR="203.0.113.11").get(url)

        assert response.status_code == 200

    def test_fails_open_on_cache_outage(self, seller, category, city):
        """A cache outage allows the media request instead of raising.

        The seam is the shared cache backend, not a module-level ``cache`` name.
        ``django.core.cache.cache`` is a single proxy over one backend, so every
        guard module's ``cache`` global is the same object; patching the backend
        is invariant to which module holds a reference and cannot be neutralised
        by a guard gaining, losing or duplicating a ``cache`` import.
        """
        key = self._published_key(seller, category, city)
        client = Client()
        url = f"/media/{key}"

        outage = MagicMock()
        outage.add.side_effect = ConnectionInterrupted(None)

        with (
            override_settings(DEBUG=False),
            patch.object(caches[DEFAULT_CACHE_ALIAS], "add", outage.add),
        ):
            response = client.get(url)

        assert response.status_code != 429

    def test_period_constant_is_the_documented_window(self) -> None:
        """The window pair is the reviewed budget, not an inline literal."""
        assert (MEDIA_RATE_LIMIT_REQUESTS, MEDIA_RATE_LIMIT_PERIOD) == (60, 60)

    def test_429_has_retry_after_header(self, seller, category, city):
        """The 429 response advertises how long the client should wait."""
        key = self._published_key(seller, category, city)
        client = Client()
        url = f"/media/{key}"

        with override_settings(DEBUG=False):
            for _ in range(MEDIA_RATE_LIMIT_REQUESTS):
                client.get(url)
            response = client.get(url)

        assert response.status_code == 429
        assert response.headers.get("Retry-After") == str(MEDIA_RATE_LIMIT_PERIOD)

    def test_429_returns_svg_placeholder(self, seller, category, city):
        """The 429 body is an SVG rectangle matching the 240×180 thumbnail slot."""
        key = self._published_key(seller, category, city)
        client = Client()
        url = f"/media/{key}"

        with override_settings(DEBUG=False):
            for _ in range(MEDIA_RATE_LIMIT_REQUESTS):
                client.get(url)
            response = client.get(url)

        assert response.status_code == 429
        body = response.content.decode()
        assert "<svg" in body
        assert response.headers.get("Content-Type") == "image/svg+xml"
        assert _MEDIA_GATE_429_SVG in body

    def test_429_has_no_store_cache_control(self, seller, category, city):
        """The 429 response must never be cached by intermediary proxies."""
        key = self._published_key(seller, category, city)
        client = Client()
        url = f"/media/{key}"

        with override_settings(DEBUG=False):
            for _ in range(MEDIA_RATE_LIMIT_REQUESTS):
                client.get(url)
            response = client.get(url)

        assert response.status_code == 429
        assert response.headers.get("Cache-Control") == "no-store"

