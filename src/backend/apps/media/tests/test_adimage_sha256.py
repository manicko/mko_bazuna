"""
Integration tests for ``AdImage.save()`` SHA-256 auto-computation (07-MEDIA-011).

Verifies:
- ``AdImage.save()`` populates ``sha256`` on **insert** when the referenced file
  exists on disk, using :class:`FileHashService`.
- A subsequent ``save(update_fields=[...])`` does **not** recompute ``sha256``
  when the field is already populated (the guard at line 732 of models.py).
- A missing file leaves ``sha256`` empty rather than raising.
- On insert, a pre-computed ``sha256`` passed to ``AdImage.objects.create()`` is
  preserved and NOT recomputed from the on-disk file.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from django.test import override_settings

from apps.ads.models import AdImage
from apps.core.enums import AdStatus
from apps.media.services.filesystem import generate_storage_key
from apps.media.services.hash_service import FileHashService
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestAdImageSaveSha256:
    """``AdImage.save`` — SHA-256 auto-computation on insert/update."""

    def test_sha256_populated_on_insert_when_file_exists(
        self, seller, category, city, tmp_path: Path
    ) -> None:
        """On insert, ``sha256`` is filled from the on-disk file via FileHashService."""
        media_root = tmp_path / "media"
        media_root.mkdir()
        with override_settings(MEDIA_ROOT=str(media_root)):
            ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)

            image_key = generate_storage_key()
            photo_bytes = b"fake-jpeg-bytes-for-hashing"
            (media_root / image_key).write_bytes(photo_bytes)

            ad_image = AdImage.objects.create(
                ad=ad, image=image_key, position=0
            )

            ad_image.refresh_from_db()
            expected = hashlib.sha256(photo_bytes).hexdigest()
            assert ad_image.sha256 == expected

    def test_sha256_not_recomputed_on_update_when_already_set(
        self, seller, category, city, tmp_path: Path
    ) -> None:
        """``save()`` does not recompute ``sha256`` on update when already populated.

        The guard at ``AdImage.save`` line 732 is ``if not self.sha256:`` — so an
        **update** (not adding) with a non-empty ``sha256`` skips the file-based
        recomputation. This test creates the row (which populates ``sha256``),
        then changes the on-disk file bytes and saves again; the digest must
        remain the original value, not reflect the changed bytes.
        """
        media_root = tmp_path / "media"
        media_root.mkdir()
        with override_settings(MEDIA_ROOT=str(media_root)):
            ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)

            image_key = generate_storage_key()
            photo_bytes = b"original-bytes"
            (media_root / image_key).write_bytes(photo_bytes)

            ad_image = AdImage.objects.create(
                ad=ad, image=image_key, position=0
            )
            original_hash = ad_image.sha256
            assert original_hash, "sha256 should be populated on insert"

            # Overwrite the file with different bytes and save again.
            (media_root / image_key).write_bytes(b"changed-bytes")
            ad_image.save(update_fields=["image"])

            ad_image.refresh_from_db()
            assert ad_image.sha256 == original_hash, (
                "sha256 was recomputed during update despite the guard"
            )

    def test_sha256_empty_when_file_missing(self, seller, category, city) -> None:
        """A non-existent file leaves ``sha256`` blank instead of raising."""
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        ad_image = AdImage.objects.create(
            ad=ad, image="nonexistent.jpg", position=0
        )

        ad_image.refresh_from_db()
        assert ad_image.sha256 == ""

    def test_sha256_matches_file_hash_service(
        self, seller, category, city, tmp_path: Path
    ) -> None:
        """The value on the row equals ``FileHashService.calculate_sha256``."""
        media_root = tmp_path / "media"
        media_root.mkdir()
        with override_settings(MEDIA_ROOT=str(media_root)):
            ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)

            image_key = generate_storage_key()
            photo_bytes = b"integration-test-photo-bytes"
            (media_root / image_key).write_bytes(photo_bytes)

            ad_image = AdImage.objects.create(
                ad=ad, image=image_key, position=0
            )
            ad_image.refresh_from_db()

            file_hash = FileHashService.calculate_sha256(str(media_root / image_key))
            assert ad_image.sha256 == file_hash

    def test_sha256_not_recomputed_on_insert_when_explicitly_passed(
        self, seller, category, city, tmp_path: Path
    ) -> None:
        """On insert, a pre-computed ``sha256`` is preserved, not recomputed.

        The guard at ``AdImage.save`` line 732 is ``if not self.sha256:`` — so
        when ``sha256`` is already populated (passed explicitly to
        ``AdImage.objects.create()``), the on-disk file is never read and the
        pre-computed value is kept even if the file bytes differ.
        """
        media_root = tmp_path / "media"
        media_root.mkdir()
        with override_settings(MEDIA_ROOT=str(media_root)):
            ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)

            image_key = generate_storage_key()
            photo_bytes = b"on-disk-bytes"
            (media_root / image_key).write_bytes(photo_bytes)

            pre_computed = "precomputed-sha256-value"
            ad_image = AdImage.objects.create(
                ad=ad, image=image_key, position=0, sha256=pre_computed
            )

            ad_image.refresh_from_db()
            assert ad_image.sha256 == pre_computed, (
                "sha256 was recomputed from the file despite being passed explicitly"
            )
            # The on-disk bytes hash to something different; confirm they differ.
            assert pre_computed != hashlib.sha256(photo_bytes).hexdigest()
