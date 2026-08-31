"""
File hash service for content-addressable storage and deduplication.
"""

import hashlib


class FileHashService:
    """Compute file hashes for deduplication and integrity verification."""

    @staticmethod
    def calculate_sha256(file_path: str) -> str:
        """Compute SHA-256 hex digest of a file.

        Args:
            file_path: Absolute or relative path to the file.

        Returns:
            Hex digest string (64 characters).
        """
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
