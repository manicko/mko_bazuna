"""
Ad image service — creation with SHA-256 hashing and user-scope deduplication.

Extracted from ``AdImage.save()`` (QLT-012) so the model no longer performs
file I/O or silently skips saves for duplicate uploads.
"""

import logging
from pathlib import Path

from django.conf import settings

from apps.ads.models import Ad, AdImage
from apps.media.services.hash_service import FileHashService

logger = logging.getLogger(__name__)


class AdImageService:
    """Create ``AdImage`` rows with content-aware deduplication.

    When a seller uploads a photo that is byte-identical to one they have
    already attached to another ad, the existing row is returned instead of
    creating a duplicate.  This keeps storage and the ``sha256`` index lean
    without silently swallowing writes in the model layer.
    """

    @staticmethod
    def _compute_sha256(image_key: str) -> str:
        """Return the SHA-256 hex digest of *image_key* on disk, or ``""``.

        Falls back to an empty string when ``MEDIA_ROOT`` is unset or the
        file does not exist (e.g. in unit tests that never touch the disk).
        """
        media_root = settings.MEDIA_ROOT
        if media_root is None:
            return ""
        file_path = Path(str(media_root)) / image_key
        if not file_path.exists():
            return ""
        return FileHashService.calculate_sha256(str(file_path))

    @classmethod
    def create_or_skip(cls, ad: Ad, image: str, **extra) -> AdImage:
        """Create an ``AdImage``, returning an existing duplicate if one is found.

        Deduplication is scoped per seller: if the ad's owner already has an
        ``AdImage`` whose ``sha256`` matches the newly uploaded file, that
        existing row is returned (no new row is created) and the skip is
        logged.

        Args:
            ad: Parent ad.  Must already be persisted so that ``user_id``
                is available for the dedup query.
            image: Storage key of the image file.
            **extra: Additional ``AdImage`` field values
                (``telegram_file_id``, ``position``, thumbnail keys, …).

        Returns:
            The newly created ``AdImage``, or the existing duplicate row.
        """
        sha256 = cls._compute_sha256(image)

        if sha256:
            duplicate = AdImage.objects.filter(
                sha256=sha256,
                ad__user_id=ad.user_id,
            ).first()
            if duplicate is not None:
                logger.info(
                    "AdImage dedup: sha256=%s ad_id=%s user_id=%s "
                    "skipped (existing pk=%s)",
                    sha256[:12],
                    ad.pk,
                    ad.user_id,
                    duplicate.pk,
                )
                return duplicate

        return AdImage.objects.create(
            ad=ad,
            image=image,
            sha256=sha256,
            **extra,
        )
