"""
Django admin registration for users app.

Custom admin with restricted access and consents visibility.
"""

from apps.users.models import LoginToken, User
from django.contrib import admin


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    """
    User admin with telegram_id, ban/deletion flags, and consent timestamps.

    Admin access restricted to is_staff/is_superuser.
    """

    list_display = [
        "telegram_id",
        "is_banned",
        "is_deleted",
        "ads_auto_publish",
        "consent_given_at",
        "consent_revoked_at",
    ]
    list_filter = [
        "is_banned",
        "is_deleted",
        "ads_auto_publish",
        "is_staff",
        "is_superuser",
    ]
    search_fields = ["telegram_id"]
    readonly_fields = [
        "consent_given_at",
        "consent_revoked_at",
        "deleted_at",
        "hard_delete_at",
    ]

    def has_add_permission(self, request) -> bool:
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None) -> bool:
        return request.user.is_staff

    def has_delete_permission(self, request, obj=None) -> bool:
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None) -> bool:
        return request.user.is_staff


@admin.register(LoginToken)
class LoginTokenAdmin(admin.ModelAdmin):
    """
    LoginToken admin for debugging authentication flows.
    """

    list_display = ["id", "telegram_id", "created_at", "expires_at", "consumed_at"]
    list_filter = ["consumed_at"]
    search_fields = ["telegram_id"]
    readonly_fields = ["token_hash", "telegram_id", "created_at", "expires_at", "consumed_at"]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return request.user.is_superuser