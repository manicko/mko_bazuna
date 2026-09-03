"""
Django admin registration for core app.

SiteConfig singleton editing with add/delete disabled.
"""

from apps.core.models import SiteConfig
from django.contrib import admin


@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    """
    SiteConfig singleton admin.

    Exactly one row exists, edited by admin at runtime for centralized
    site name branding.
    """

    list_display = ["name"]
    readonly_fields = []

    def has_add_permission(self, request) -> bool:
        # Singleton - row created automatically if missing
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
