"""
Django admin registration for categories app.

Uses django-mptt admin for hierarchical category tree.
Includes inlines for CategoryPath, CategoryListingPurpose, and CategoryListingFeature.
"""

from apps.categories.models import (
    Category,
    CategoryListingFeature,
    CategoryListingPurpose,
    CategoryPath,
)
from django.contrib import admin
from mptt.admin import MPTTModelAdmin


class CategoryPathInline(admin.TabularInline):
    """Inline for CategoryPath — alternative parent routes."""

    model = CategoryPath
    fk_name = "category"
    fields = ["parent", "sort_order", "is_automatic"]
    readonly_fields = ["is_automatic"]
    extra = 1
    ordering = ["sort_order"]
    autocomplete_fields = ["parent"]
    verbose_name_plural = "Alternative parent paths"


class CategoryListingPurposeInline(admin.TabularInline):
    """Inline for CategoryListingPurpose — binding listing purposes to categories."""

    model = CategoryListingPurpose
    fields = ["listing_purpose", "is_default"]
    extra = 1
    autocomplete_fields = ["listing_purpose"]


class CategoryListingFeatureInline(admin.TabularInline):
    """Inline for CategoryListingFeature — binding listing features to categories."""

    model = CategoryListingFeature
    fields = ["feature"]
    extra = 1
    autocomplete_fields = ["feature"]


@admin.register(Category)
class CategoryAdmin(MPTTModelAdmin):
    """
    Category admin with MPTT tree support and lookup binding inlines.

    Allows add/edit/deactivate operations on hierarchical categories.
    """

    list_display = ["name", "slug", "is_active", "parent"]
    list_filter = ["is_active"]
    search_fields = ["name", "slug"]
    readonly_fields = []
    inlines = [
        CategoryPathInline,
        CategoryListingPurposeInline,
        CategoryListingFeatureInline,
    ]

    def has_change_permission(self, request, obj=None) -> bool:
        return request.user.is_staff

    def has_delete_permission(self, request, obj=None) -> bool:
        # Soft deactivate via is_active, hard delete only for superuser
        return request.user.is_superuser