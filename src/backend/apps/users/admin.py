"""
Django admin registration for users app.

Custom admin with restricted access and consents visibility.
"""

from apps.users.models import ConsentRecord, LoginToken, User
from django.contrib import admin
from apps.users.services import withdraw_consent


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    """
    User admin with telegram_id, ban/deletion flags, and consent timestamps.

    Admin access restricted to is_staff/is_superuser.
    """

    list_display = [
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
    ]

    def has_add_permission(self, request) -> bool:
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None) -> bool:
        return request.user.is_staff

    def has_delete_permission(self, request, obj=None) -> bool:
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None) -> bool:
        return request.user.is_staff

    @admin.action(description="Withdraw consent for selected users")
    def withdraw_consent_action(self, request, queryset):
        """
        Admin action to trigger consent withdrawal for selected users.

        Calls withdraw_consent on each user, which sets consent_revoked_at,
        soft-deletes the user and their ads, and nullifies PII.
        """
        for user in queryset:
            withdraw_consent(user)
        self.message_user(request, f"Withdrew consent for {queryset.count()} user(s).")


@admin.register(ConsentRecord)
class ConsentRecordAdmin(admin.ModelAdmin):
    """
    Read-mostly admin for the consent audit log (GDPR Article 7(1)).
    """

    list_display = [
        "id",
        "consent_given_at",
        "user",
        "session_key",
        "choice",
        "consent_version",
    ]
    list_filter = ["choice", "consent_version", "consent_given_at"]
    search_fields = ["session_key"]
    readonly_fields = [
        "user",
        "session_key",
        "consent_given_at",
        "consent_version",
        "choice",
        "categories",
        "ip_address",
        "user_agent",
    ]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None) -> bool:
        return request.user.is_superuser


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
