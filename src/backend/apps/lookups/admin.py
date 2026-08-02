"""
Admin registration for lookups app.

LookupGroup admin with inline LookupItem rows.
System groups protected from deletion.
"""

from apps.lookups.models import LookupGroup, LookupItem
from django.contrib import admin


class LookupItemInline(admin.TabularInline):
    """Inline editor for LookupItem within LookupGroup admin."""

    model = LookupItem
    fields = ["slug", "sort_order", "is_active", "icon", "color"]
    extra = 1
    ordering = ["sort_order"]


@admin.register(LookupGroup)
class LookupGroupAdmin(admin.ModelAdmin):
    """Admin for lookup groups with inline items and system group protection."""

    list_display = ["code", "sort_order", "is_system", "item_count"]
    list_filter = ["is_system"]
    search_fields = ["code"]
    inlines = [LookupItemInline]
    readonly_fields = ["is_system"]

    def item_count(self, obj: LookupGroup) -> int:
        """Display count of items in this group."""
        return obj.items.count()

    item_count.short_description = "Items"  # type: ignore[attr-defined]

    def has_delete_permission(self, request, obj=None) -> bool:
        """Block deletion of system groups."""
        if obj and obj.is_system:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(LookupItem)
class LookupItemAdmin(admin.ModelAdmin):
    """Admin for individual lookup items with group filter."""

    list_display = ["slug", "group", "is_active", "sort_order"]
    list_filter = ["group", "is_active"]
    search_fields = ["slug", "name_i18n"]
    ordering = ["group", "sort_order"]