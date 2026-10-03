"""
Read-only Django admin surface for ``MediaDeletionError`` (07-MEDIA-010).

``delete_photo`` writes a row whenever a deletion exhausts its retries, and
until now nothing could read them. Rows are never created, edited or deleted
here — this is a diagnostic reader only. The table is bounded by the
``purge_media_deletion_errors`` retention command.

This module introduces no editable field and no ``has_view_permission``
override: staff-only access is enforced by ``AdminSite.has_permission``, which
requires ``is_active`` and ``is_staff`` alongside the model view permission.
"""

from django.contrib import admin

from apps.media.models import MediaDeletionError


@admin.register(MediaDeletionError)
class MediaDeletionErrorAdmin(admin.ModelAdmin):
    """Changelist-only reader for recorded deletion failures."""

    list_display = ["created_at", "storage_key", "error_type", "attempts"]
    list_filter = ["error_type", "created_at"]
    readonly_fields = []
    ordering = ("-created_at",)

    def has_add_permission(self, request) -> bool:
        """Rows are written by delete_photo, never by an operator."""
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        """The reader is diagnostic; nothing here is editable."""
        return False
