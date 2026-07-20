"""
Django admin registration for locations app.

City management for ad locations.
"""

from apps.locations.models import City
from django.contrib import admin


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    """
    City admin for location management.
    """

    list_display = ["name", "slug", "country_code", "region"]
    list_filter = ["country_code", "region"]
    search_fields = ["name", "slug", "region"]

    def has_change_permission(self, request, obj=None) -> bool:
        return request.user.is_staff

    def has_delete_permission(self, request, obj=None) -> bool:
        return request.user.is_superuser