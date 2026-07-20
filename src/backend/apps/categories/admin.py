"""
Django admin registration for categories app.

Uses django-mptt admin for hierarchical category tree.
"""

from django.contrib import admin
from mptt.admin import MPTTModelAdmin

from apps.categories.models import Category


@admin.register(Category)
class CategoryAdmin(MPTTModelAdmin):
    """
    Category admin with MPTT tree support.

    Allows add/edit/deactivate operations on hierarchical categories.
    """

    list_display = ["name", "slug", "is_active", "parent"]
    list_filter = ["is_active"]
    search_fields = ["name", "slug"]
    readonly_fields = []

    def has_change_permission(self, request, obj=None) -> bool:
        return request.user.is_staff

    def has_delete_permission(self, request, obj=None) -> bool:
        # Soft deactivate via is_active, hard delete only for superuser
        return request.user.is_superuser