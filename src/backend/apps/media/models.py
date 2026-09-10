"""
Media models for Mko Bazuna.

``MediaDeletionError`` records filesystem deletion failures that exhausted
all retries in ``delete_photo``, enabling operational escalation (ME-003).
"""

from django.db import models


class MediaDeletionError(models.Model):
    """Record of a storage-key deletion that failed after all retries.

    Best-effort persistence — the recording call in ``delete_photo`` wraps
    this write in ``try/except`` so it can never raise and disrupt the
    sweep/cron job that triggered the deletion.

    No foreign keys are stored: ``delete_photo`` operates on a bare storage
    key with no ad or user context, so the row is self-contained for
    triage by operations staff.
    """

    storage_key = models.TextField(
        help_text="Storage key (UUID-based, no PII) of the file that could not be deleted",
    )
    error_type = models.CharField(
        max_length=120,
        help_text="Exception class name (e.g. PermissionError)",
    )
    error_message = models.CharField(
        max_length=1000,
        help_text="Truncated exception message",
    )
    attempts = models.PositiveSmallIntegerField(
        help_text="Number of deletion attempts made before giving up",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the deletion failure was recorded",
    )

    class Meta:
        db_table = "media_deletion_errors"
        indexes = [
            models.Index(
                fields=["created_at"],
                name="idx_media_del_err_created",
            ),
            models.Index(
                fields=["error_type"],
                name="idx_media_del_err_type",
            ),
        ]

    def __str__(self) -> str:
        return f"MediaDeletionError: {self.storage_key} ({self.error_type})"
