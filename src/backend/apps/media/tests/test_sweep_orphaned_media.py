"""
Integration tests for the sweep_orphaned_media management command (DB-004).

Verifies:
- Orphaned files (no AdImage reference) are deleted via delete_photo
- Referenced files (across all 4 AdImage fields) are preserved
- Files under the seed/ subdir are excluded from the sweep
- Dry-run mode is non-destructive
- File deletion is routed through delete_photo (not raw os.remove)

Uses an isolated temporary MEDIA_ROOT with real files on disk.
"""

from __future__ import annotations

import os
import re
import tempfile
from collections.abc import Generator
from contextlib import contextmanager, suppress
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from apps.ads.models import AdImage
from apps.core.enums import AdStatus
from apps.media.services.filesystem import STAGING_SUBDIR
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
# Tests
# ---------------------------------------------------------------------------


class TestSweepOrphanedMedia:
    """Integration tests for the sweep_orphaned_media management command."""

    def test_orphaned_file_is_deleted(
        self, seller, category, city, isolated_media_root
    ):
        """A file on disk with no AdImage reference is deleted by the sweep."""
        key = "orphaned-file.jpg"
        (isolated_media_root / key).write_bytes(b"orphan data")

        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            call_command("sweep_orphaned_media")

        assert not (isolated_media_root / key).exists()

    def test_referenced_file_is_kept(self, seller, category, city, isolated_media_root):
        """Files referenced by any AdImage field are preserved across all 4 fields.

        Creates a single AdImage with all four storage-key fields set
        (image, thumbnail_small, thumbnail_medium, thumbnail_large) plus an
        orphan file, then runs the sweep. All referenced files survive and
        the orphan is deleted — proving the sweep discriminates correctly.
        """
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)

        image_key = "referenced-original.jpg"
        small_key = "referenced-small.jpg"
        medium_key = "referenced-medium.jpg"
        large_key = "referenced-large.jpg"
        orphan_key = "orphan-to-delete.jpg"

        # Write physical files for all referenced keys + one orphan
        for key in (image_key, small_key, medium_key, large_key, orphan_key):
            (isolated_media_root / key).write_bytes(b"image data")

        AdImage.objects.create(
            ad=ad,
            image=image_key,
            thumbnail_small=small_key,
            thumbnail_medium=medium_key,
            thumbnail_large=large_key,
        )

        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            call_command("sweep_orphaned_media")

        # All 4 referenced fields' files must survive
        assert (isolated_media_root / image_key).is_file()
        assert (isolated_media_root / small_key).is_file()
        assert (isolated_media_root / medium_key).is_file()
        assert (isolated_media_root / large_key).is_file()
        # Orphan must be deleted
        assert not (isolated_media_root / orphan_key).exists()

    def test_seed_subdir_excluded(self, seller, category, city, isolated_media_root):
        """Orphan files under MEDIA_ROOT/seed/ are excluded from the sweep."""
        seed_subdir = isolated_media_root / "seed"
        seed_subdir.mkdir()
        (seed_subdir / "seed-orphan.jpg").write_bytes(b"seed data")

        # Regular orphan at top level — should be deleted
        (isolated_media_root / "regular-orphan.jpg").write_bytes(b"regular")

        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            call_command("sweep_orphaned_media")

        # Seed subdir file is NOT deleted (excluded from orphan sweep)
        assert (seed_subdir / "seed-orphan.jpg").exists()
        # Top-level orphan IS deleted
        assert not (isolated_media_root / "regular-orphan.jpg").exists()

    def test_dry_run_is_nondestructive(
        self, seller, category, city, isolated_media_root
    ):
        """--dry-run reports orphans without deleting any files."""
        key = "dry-run-orphan.jpg"
        (isolated_media_root / key).write_bytes(b"dry run data")

        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            call_command("sweep_orphaned_media", dry_run=True)

        # File must still exist — dry run is non-destructive
        assert (isolated_media_root / key).exists()

    def test_delete_photo_routing(
        self, seller, category, city, isolated_media_root, monkeypatch
    ):
        """The sweep routes file deletion through delete_photo, not raw os.remove.

        Replaces delete_photo in the command module with a spy. If the
        production code is ever reverted to os.remove, the spy will not be
        called and the file will be physically removed — both assertions fail.
        """
        key = "routing-test-orphan.jpg"
        (isolated_media_root / key).write_bytes(b"routing test")

        mock_delete = MagicMock()
        monkeypatch.setattr(
            "apps.media.management.commands.sweep_orphaned_media.delete_photo",
            mock_delete,
        )

        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            call_command("sweep_orphaned_media")

        # delete_photo spy must have been called with the orphan key
        mock_delete.assert_called_once_with(key)
        # File still exists because the spy is a no-op (real delete_photo
        # would have removed it)
        assert (isolated_media_root / key).exists()

    def test_staging_file_survives_sweep(
        self, seller, category, city, isolated_media_root
    ):
        """In-flight uploads in staging/ are protected from the orphan sweep."""
        staging_dir = isolated_media_root / STAGING_SUBDIR
        staging_dir.mkdir()
        staging_file = staging_dir / "in-flight.jpg"
        staging_file.write_bytes(b"in-flight")

        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            call_command("sweep_orphaned_media")

        # Staging file is NOT deleted (excluded from the orphan sweep)
        assert staging_file.exists(), "staging file was deleted by the sweep"
        assert staging_file.read_bytes() == b"in-flight"

    def test_stale_staging_file_reclaimed(
        self, seller, category, city, isolated_media_root
    ):
        """Staging files older than the 2-hour TTL are reclaimed by the sweep."""
        staging_dir = isolated_media_root / STAGING_SUBDIR
        staging_dir.mkdir()
        stale_file = staging_dir / "stale.jpg"
        stale_file.write_bytes(b"stale")

        # Set mtime to 3 hours ago (beyond the 2-hour TTL)
        stale_mtime = os.path.getmtime(stale_file) - (3 * 60 * 60)
        os.utime(stale_file, (stale_mtime, stale_mtime))

        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            call_command("sweep_orphaned_media")

        # Stale staging file IS deleted (beyond TTL)
        assert not stale_file.exists(), "stale staging file was not reclaimed"

    def test_fresh_staging_file_preserved(
        self, seller, category, city, isolated_media_root
    ):
        """Fresh staging files (within TTL) are preserved by the sweep."""
        staging_dir = isolated_media_root / STAGING_SUBDIR
        staging_dir.mkdir()
        fresh_file = staging_dir / "fresh.jpg"
        fresh_file.write_bytes(b"fresh")

        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            call_command("sweep_orphaned_media")

        # Fresh staging file IS preserved (within TTL)
        assert fresh_file.exists(), "fresh staging file was incorrectly reclaimed"


# ---------------------------------------------------------------------------
# MED-001 regression guard: deletion loop must run inside advisory-lock scope
# ---------------------------------------------------------------------------


class TestSweepLockScope:
    """Verify filesystem mutations occur within the advisory-lock scope.

    MED-001 found that the deletion loop in ``sweep_orphaned_media`` ran
    *after* the advisory lock was released, allowing concurrent sweeps to
    race during file deletion.  These tests spy on ``advisory_lock`` and
    ``delete_photo`` to assert every deletion happens while the lock is held.
    """

    def test_delete_photo_called_within_lock_scope(
        self, seller, category, city, isolated_media_root, monkeypatch
    ):
        """All ``delete_photo`` calls must occur while advisory_lock is held.

        This is a genuine regression guard: it **fails** on the pre-fix code
        (deletion loop outside the lock) and **passes** after the fix.
        """
        key = "orphaned-file.jpg"
        (isolated_media_root / key).write_bytes(b"orphan data")

        # Shared mutable flag: True while the spy advisory_lock block is entered.
        lock_state = {"held": False}

        # Spy for advisory_lock: a no-op context manager that records enter/exit
        # on the shared ``lock_state`` flag.  Does not acquire a real PostgreSQL
        # lock — the goal is purely to demarcate the lock scope boundary.
        @contextmanager
        def spy_advisory_lock(*_args, **_kwargs):
            lock_state["held"] = True
            try:
                yield
            finally:
                lock_state["held"] = False

        monkeypatch.setattr(
            "apps.media.management.commands.sweep_orphaned_media.advisory_lock",
            spy_advisory_lock,
        )

        # Spy for delete_photo: records whether the lock was held at each call.
        delete_call_lock_state: list[bool] = []

        def spy_delete_photo(storage_key: str) -> None:
            delete_call_lock_state.append(lock_state["held"])

        monkeypatch.setattr(
            "apps.media.management.commands.sweep_orphaned_media.delete_photo",
            spy_delete_photo,
        )

        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            call_command("sweep_orphaned_media")

        # The orphan file must have triggered at least one delete_photo call.
        assert delete_call_lock_state, (
            "delete_photo was never called — test fixture did not produce an "
            "orphan, so lock-scope timing cannot be validated"
        )
        # Every call must have occurred while the lock was held (inside the
        # ``with advisory_lock(...)`` block).  A single False entry means a
        # deletion ran after lock release — the MED-001 bug.
        assert all(delete_call_lock_state), (
            "delete_photo was called outside the advisory-lock scope: "
            f"{delete_call_lock_state}"
        )


# ---------------------------------------------------------------------------
# BLOCK 6: dangling-row reconciliation (--check) + truthful deletion counter
# ---------------------------------------------------------------------------


def _deleted_count(stdout: str) -> int:
    """Extract the deletion count from the command's success line.

    The count is the *channel*; the surrounding prose is deliberately not
    pinned.  A regex over the ``Deleted <n> orphaned`` fragment keeps the
    assertion on the number while tolerating message edits.
    """
    match = re.search(r"Deleted (\d+) orphaned", stdout)
    assert match is not None, f"deletion count not found in output: {stdout!r}"
    return int(match.group(1))


class TestSweepCheckMode:
    """``--check`` reconciles the store against the database, read-only."""

    def test_check_reports_dangling_seed_reference(
        self, seller, category, city, isolated_media_root
    ):
        """A referenced ``seed/`` key whose file is gone is reported.

        The probe must use the **verbatim** key and the report scope must
        **include ``seed/``**.  The present seed file guards the verbatim rule:
        a probe that stripped the ``seed/`` prefix would look for
        ``present.jpg`` at the top level, miss, and flag a live file as
        dangling.
        """
        seed_dir = isolated_media_root / "seed"
        seed_dir.mkdir()
        (seed_dir / "present.jpg").write_bytes(b"seed data")

        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        AdImage.objects.create(ad=ad, image="seed/present.jpg", position=0)
        AdImage.objects.create(ad=ad, image="seed/missing.jpg", position=1)

        out = StringIO()
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            with pytest.raises(CommandError):
                call_command("sweep_orphaned_media", check=True, stdout=out)

        report = out.getvalue()
        assert "seed/missing.jpg" in report
        assert "seed/present.jpg" not in report

    def test_check_reports_nothing_when_store_matches(
        self, seller, category, city, isolated_media_root
    ):
        """A store that agrees with the database yields no mismatch, seed included."""
        seed_dir = isolated_media_root / "seed"
        seed_dir.mkdir()
        (seed_dir / "present.jpg").write_bytes(b"seed data")
        (isolated_media_root / "top-level.jpg").write_bytes(b"image data")

        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        AdImage.objects.create(ad=ad, image="seed/present.jpg", position=0)
        AdImage.objects.create(ad=ad, image="top-level.jpg", position=1)

        out = StringIO()
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            call_command("sweep_orphaned_media", check=True, stdout=out)

        assert "Media store matches the database." in out.getvalue()

    def test_check_suppresses_staging_references(
        self, seller, category, city, isolated_media_root
    ):
        """A row referencing a missing ``staging/`` file is not a dangling row.

        ``staging/`` is the only suppression: it is the one directory the sweep
        ignores by design, so its files are bounded by the TTL, never by row
        presence.
        """
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        AdImage.objects.create(ad=ad, image="staging/legacy-uuid.jpg")

        out = StringIO()
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            call_command("sweep_orphaned_media", check=True, stdout=out)

        assert "staging/legacy-uuid.jpg" not in out.getvalue()

    def test_check_and_dry_run_are_mutually_exclusive(
        self, seller, category, city, isolated_media_root
    ):
        """``--check`` and ``--dry-run`` cannot be combined.

        The flags are passed as **command-line arguments** deliberately: when
        both are supplied as ``call_command`` keyword arguments, Django merges
        them into ``options`` and bypasses argparse, so the mutual-exclusion
        group never runs.  String args go through ``CommandParser.error``,
        which ``call_command`` wraps as ``CommandError``.
        """
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            with pytest.raises(CommandError):
                call_command("sweep_orphaned_media", "--dry-run", "--check")

    def test_both_modes_are_nondestructive(
        self, seller, category, city, isolated_media_root
    ):
        """Neither ``--dry-run`` nor ``--check`` deletes an orphan file."""
        for mode in ("dry_run", "check"):
            key = "non-destructive-orphan.jpg"
            (isolated_media_root / key).write_bytes(b"orphan data")

            out = StringIO()
            with override_settings(MEDIA_ROOT=str(isolated_media_root)):
                with suppress(CommandError):
                    call_command("sweep_orphaned_media", stdout=out, **{mode: True})

            assert (isolated_media_root / key).exists(), (
                f"{mode} deleted {key}"
            )


class TestSweepDeletionCounter:
    """The reported count equals the files actually removed, not attempts."""

    def test_count_excludes_failed_removals(
        self, seller, category, city, isolated_media_root, monkeypatch
    ):
        """A FileNotFoundError and a retry exhaustion are not counted.

        Three orphan files exist.  ``os.remove`` is driven so that one file is
        genuinely removed, one raises the terminal ``FileNotFoundError``, and
        one raises ``PermissionError`` on every attempt (retry exhaustion).
        The reported count must be ``1`` — the number actually removed — not
        ``3`` (attempts) and not ``2``.
        """
        removed_key = "counted-removed.jpg"
        terminal_key = "counted-terminal.jpg"
        exhausted_key = "counted-exhausted.jpg"
        for key in (removed_key, terminal_key, exhausted_key):
            (isolated_media_root / key).write_bytes(b"orphan data")

        real_remove = os.remove

        def fake_remove(path: str) -> None:
            name = os.path.basename(path)
            if name == terminal_key:
                raise FileNotFoundError(path)
            if name == exhausted_key:
                raise PermissionError(path)
            real_remove(path)

        monkeypatch.setattr(
            "apps.media.services.filesystem.os.remove", fake_remove
        )

        out = StringIO()
        with override_settings(MEDIA_ROOT=str(isolated_media_root)):
            call_command("sweep_orphaned_media", stdout=out)

        assert not (isolated_media_root / removed_key).exists()
        assert (isolated_media_root / terminal_key).exists()
        assert (isolated_media_root / exhausted_key).exists()
        assert _deleted_count(out.getvalue()) == 1

