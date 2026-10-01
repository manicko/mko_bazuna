"""
Django admin registration for users app.

Custom admin with restricted access and consents visibility.
"""

from django.contrib import admin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from apps.core.utils.sanitize import mask_telegram_id
from apps.users.models import ConsentRecord, LoginToken, User
from apps.users.services import withdraw_consent


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    """
    User admin with telegram_id, ban/deletion flags, and consent timestamps.

    Admin access restricted to is_staff/is_superuser.

    The change form is an explicit field contract (finding 04-AUT-005). Django's
    auto-built form would expose every editable ``User`` field, including
    ``password`` as a writable text input rendering the stored hash, plus
    ``is_superuser``/``is_staff``/``groups``/``user_permissions`` and every
    consent/account-state flag. ``UserChangeForm`` declares ``password`` as a
    disabled ``ReadOnlyPasswordHashField``: a POSTed plaintext is discarded
    before validation, ``save_model`` writes the stored hash back unchanged and
    the widget renders ``hasher.safe_summary()`` (masked). The add view closes
    the same plaintext hole through ``UserCreationForm``.
    """

    form = UserChangeForm
    add_form = UserCreationForm

    fieldsets = (
        (
            None,
            {"fields": ("username", "password")},
        ),
        (
            "Identity",
            {"fields": ("telegram_id", "first_name", "last_name", "email")},
        ),
        (
            "Account state",
            {
                "fields": (
                    "is_active",
                    "is_banned",
                    "is_deleted",
                    "is_declined",
                    "ads_auto_publish",
                    "telegram_premium",
                ),
            },
        ),
        (
            "Preferences",
            {"fields": ("telegram_language", "preferred_city")},
        ),
        (
            "Audit",
            {
                "fields": (
                    "source",
                    "date_joined",
                    "last_login",
                    "consent_given_at",
                    "consent_revoked_at",
                    "deleted_at",
                ),
            },
        ),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "telegram_id",
                    "chat_id",
                    "password1",
                    "password2",
                ),
            },
        ),
    )
    readonly_fields = [
        "consent_given_at",
        "consent_revoked_at",
        "deleted_at",
        "is_banned",
        "is_deleted",
        "is_declined",
        "ads_auto_publish",
        "telegram_premium",
        "telegram_id",
        "username",
        "first_name",
        "last_name",
        "email",
        "is_active",
        "telegram_language",
        "source",
        "date_joined",
        "last_login",
    ]

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

    def get_readonly_fields(self, request, obj=None):  # pyright: ignore[reportIncompatibleMethodOverride] - Django's own UserAdmin overrides this untyped hook the same way
        """
        Apply the inert-but-visible field set to the change view only.

        ``ModelAdmin.get_form()`` extends the form's ``exclude`` with
        ``get_readonly_fields()`` for both add and change. The add view must
        keep ``username`` and ``telegram_id`` writable (``add_fieldsets`` names
        them; ``Field.get_default()`` gives ``chat_id`` no usable value and
        ``create_admin_user`` is the only credential-granting path). Returning
        the read-only set only when ``obj`` is set keeps creation working while
        making every identity, consent and account-state field inert on change.
        """
        if obj is None:
            return ()
        return self.readonly_fields

    def get_fieldsets(self, request, obj=None):  # pyright: ignore[reportIncompatibleMethodOverride] - Django's own UserAdmin overrides this untyped hook the same way
        """Use the creation field set when adding, the change contract otherwise."""
        if not obj:
            return self.add_fieldsets
        return super().get_fieldsets(request, obj)

    def get_form(self, request, obj=None, **kwargs):  # pyright: ignore[reportIncompatibleMethodOverride] - Django's own UserAdmin overrides this untyped hook the same way
        """Use ``UserCreationForm`` for the add view, ``UserChangeForm`` otherwise."""
        defaults = {}
        if obj is None:
            defaults["form"] = self.add_form
        defaults.update(kwargs)
        return super().get_form(request, obj, **defaults)

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

    list_display = [
        "id",
        "telegram_id_display",
        "created_at",
        "expires_at",
        "consumed_at",
    ]
    list_filter = ["consumed_at"]
    search_fields = ["telegram_id"]
    readonly_fields = [
        "token_hash",
        "telegram_id",
        "created_at",
        "expires_at",
        "consumed_at",
    ]

    @admin.display(description="Telegram ID (masked)", ordering="telegram_id")
    def telegram_id_display(self, obj: LoginToken) -> str:
        """Display the masked Telegram ID of the token claimer (PII-001/VAL-001)."""
        return mask_telegram_id(obj.telegram_id)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return request.user.is_superuser
