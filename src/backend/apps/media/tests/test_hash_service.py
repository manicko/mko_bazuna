"""
Unit tests for ``FileHashService.calculate_sha256``.

Verifies:
- SHA-256 digest matches the expected value for known input.
- Empty files produce the well-known all-zero digest.
- Large files (multi-chunk) are hashed correctly.
- Non-existent files raise ``FileNotFoundError``.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from apps.media.services.hash_service import FileHashService

pytestmark = [pytest.mark.unit]


class TestFileHashServiceCalculateSha256:
    """``FileHashService.calculate_sha256`` — SHA-256 hex digest computation."""

    def test_known_input(self, tmp_path: Path) -> None:
        """The digest matches ``hashlib.sha256`` for known bytes."""
        data = b"hello, world"
        file_path = tmp_path / "sample.bin"
        file_path.write_bytes(data)

        expected = hashlib.sha256(data).hexdigest()
        result = FileHashService.calculate_sha256(str(file_path))

        assert result == expected
        assert len(result) == 64

    def test_empty_file(self, tmp_path: Path) -> None:
        """An empty file produces the SHA-256 all-zero digest."""
        file_path = tmp_path / "empty.bin"
        file_path.write_bytes(b"")

        expected = hashlib.sha256(b"").hexdigest()
        result = FileHashService.calculate_sha256(str(file_path))

        assert result == expected
        assert result == hashlib.sha256().hexdigest()

    def test_large_file_multi_chunk(self, tmp_path: Path) -> None:
        """A file larger than the 64 KiB read chunk is hashed correctly.

        The service reads in 65 536-byte chunks; a 200 KiB file exercises the
        multi-iteration ``iter`` loop, exercising the same path production uses
        for photo deduplication.
        """
        data = os.urandom(200_000)
        file_path = tmp_path / "large.bin"
        file_path.write_bytes(data)

        expected = hashlib.sha256(data).hexdigest()
        result = FileHashService.calculate_sha256(str(file_path))

        assert result == expected

    def test_nonexistent_file_raises(self, tmp_path: Path) -> None:
        """A missing file raises ``FileNotFoundError`` (no swallow)."""
        missing = tmp_path / "absent.bin"

        with pytest.raises(FileNotFoundError):
            FileHashService.calculate_sha256(str(missing))

    def test_returns_consistent_hex_digest(self, tmp_path: Path) -> None:
        """Two calls on the same file yield the same digest."""
        file_path = tmp_path / "repeat.bin"
        file_path.write_bytes(b"repeat me")

        first = FileHashService.calculate_sha256(str(file_path))
        second = FileHashService.calculate_sha256(str(file_path))

        assert first == second
