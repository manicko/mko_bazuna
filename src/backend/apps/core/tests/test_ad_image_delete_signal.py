"""
Split from test_sweep_commands.py: Tests for the AdImage pre_delete signal (HIGH-001).

Verifies that physical files (original + thumbnails) are deleted via
``transaction.on_commit()`` after the DB cascade commits, and that filesystem
failures do not roll back the DB transaction.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.conf import settings
from django.db import transaction

from apps.ads.models import Ad, AdImage
from apps.core.enums import AdStatus
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


@pytest.mark.django_db(transaction=True)
class TestAdImageDeleteSignal:
    """Tests for the AdImage pre_delete signal (HIGH-001).

    Verifies that physical files (original + thumbnails) are deleted
    via ``transaction.on_commit()`` after the DB cascade commits,
    and that filesystem failures do not roll back the DB transaction.
    """

    @pytest.fixture
    def isolated_media_root(self, tmp_path) -> Path:
        """Isolated MEDIA_ROOT for physical-file assertions."""
        return tmp_path

    def test_cascade_delete_removes_physical_files(
        self, seller, category, city, isolated_media_root, monkeypatch
    ):
        """Hard-deleting an Ad via ORM cascade removes physical files after commit.

        Creates an Ad with an AdImage (image + 3 thumbnails) and physical
        files on disk, then calls ``ad.delete()`` inside an ``atomic()``
        block.  The pre_delete signal collects ``storage_keys()`` and
        schedules ``delete_photo`` via ``on_commit``.  After the block
        exits (commit), all physical files must be gone.
        """
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        img = AdImage.objects.create(
            ad=ad,
            image="b2-cascade-original.jpg",
            thumbnail_small="b2-cascade-small.jpg",
            thumbnail_medium="b2-cascade-medium.jpg",
            thumbnail_large="b2-cascade-large.jpg",
        )
        keys = list(img.storage_keys())
        for key in keys:
            (isolated_media_root / key).write_bytes(b"image data")

        assert all((isolated_media_root / k).exists() for k in keys)

        monkeypatch.setattr(settings, "MEDIA_ROOT", str(isolated_media_root))

        with transaction.atomic():  # type: ignore[reportGeneralTypeIssues]
            ad.delete()
            # on_commit fires here — after the transaction commits.

        for key in keys:
            assert not (isolated_media_root / key).exists()
        assert not AdImage.objects.filter(pk=img.pk).exists()
        assert not Ad.objects.filter(pk=ad.pk).exists()

    def test_delete_photo_failure_does_not_rollback_cascade(
        self, seller, category, city, isolated_media_root, monkeypatch
    ):
        """A file-deletion failure inside on_commit does not roll back the DB cascade.

        The pre_delete signal defers file deletion to ``on_commit`` so the
        DB transaction commits first.  If ``delete_photo`` then raises
        (e.g. PermissionError), the exception is caught by the signal
        handler's try/except and the DB cascade persists.
        """
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        img = AdImage.objects.create(
            ad=ad,
            image="b2-failure-original.jpg",
            thumbnail_small="b2-failure-small.jpg",
            thumbnail_medium="b2-failure-medium.jpg",
            thumbnail_large="b2-failure-large.jpg",
        )
        keys = list(img.storage_keys())
        for key in keys:
            (isolated_media_root / key).write_bytes(b"image data")

        called_keys: list[str] = []

        def _failing_delete(storage_key: str) -> None:
            called_keys.append(storage_key)
            raise PermissionError("simulated disk error")

        monkeypatch.setattr("apps.media.signals.delete_photo", _failing_delete)
        monkeypatch.setattr(settings, "MEDIA_ROOT", str(isolated_media_root))

        with transaction.atomic():  # type: ignore[reportGeneralTypeIssues]
            ad.delete()
            # on_commit fires here; delete_photo raises but the exception
            # is caught by the signal handler's try/except.  The DB
            # transaction is already committed.

        # DB cascade persists despite file-deletion failure.
        assert not Ad.objects.filter(pk=ad.pk).exists()
        assert not AdImage.objects.filter(pk=img.pk).exists()
        # Signal callback fired (on_commit ran after commit).
        assert sorted(called_keys) == sorted(keys)

    def test_bulk_delete_triggers_signal(
        self, seller, category, city, isolated_media_root, monkeypatch
    ):
        """``AdImage.objects.filter(...).delete()`` (bulk path) fires the signal.

        Django's QuerySet.delete() fires ``pre_delete`` for each instance
        collected by the Collector, so the signal's ``on_commit`` callback
        runs after the bulk SQL DELETE commits.
        """
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        img = AdImage.objects.create(
            ad=ad,
            image="b2-bulk-original.jpg",
            thumbnail_small="b2-bulk-small.jpg",
            thumbnail_medium="b2-bulk-medium.jpg",
            thumbnail_large="b2-bulk-large.jpg",
        )
        keys = list(img.storage_keys())
        for key in keys:
            (isolated_media_root / key).write_bytes(b"image data")

        monkeypatch.setattr(settings, "MEDIA_ROOT", str(isolated_media_root))

        with transaction.atomic():  # type: ignore[reportGeneralTypeIssues]
            AdImage.objects.filter(ad=ad).delete()
            # on_commit fires here — after the transaction commits.

        for key in keys:
            assert not (isolated_media_root / key).exists()
        assert not AdImage.objects.filter(pk=img.pk).exists()
