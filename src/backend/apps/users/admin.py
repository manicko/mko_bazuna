"""
Django admin registration for users app.

Custom admin with restricted access and consents visibility.
"""

from django.contrib import admin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from apps.core.utils.sanitize import mask_telegram_id
from apps.users.models import ConsentRecord, LoginToken, User
from apps.users.services import withdraw_consent
from apps.users.services.deactivation import (
    DeactivationResult,
    deactivate_users,
    reactivate_users,
)

# Operator-facing message fragments. These are deliberately English-only
# literals (like the fieldset headings below) on a staff-only surface, and are
# named constants so the action tests pin a stable substring. The tests assert
# **hard-coded** copies of these substrings, not the constants, so a reword that
# drops the invariant fails the test (the guard must be able to go red).
#
# ``DEACTIVATION_ENFORCEMENT_NOTE`` states the current enforcement truth
# plainly. ``is_active = False`` is enforced on **both** tiers (plan 19,
# ``19-D2``): the web session dies on the next request (``ModelBackend``), and
# the Telegram bot's per-message ``AccountStateMiddleware`` gate — which now
# reads ``is_active`` from the shared ``get_account_state`` predicate — refuses
# the account every path. In the bot the account can neither create ads nor be
# contacted as a seller. The **only** carve-out is the support restoration
# channel: the user can still reach Support to request reactivation. Operators
# must read the toast as "enforced on both tiers, with a Support escape hatch",
# not as "locked out everywhere". The invariants a test pins are the hard-coded
# substrings ``immediately on the website``, ``enforced in the Telegram bot``
# and ``contact Support``.
DEACTIVATION_ENFORCEMENT_NOTE = (
    "This takes effect immediately on the website, and is also enforced in the "
    "Telegram bot (the account cannot create ads or be contacted as a seller). "
    "The user can still contact Support to request restoration."
)
# Invariant a test pins: the literal ``Skipped:`` label appears whenever rows
# were dropped for any reason.
SKIPPED_ROWS_PREFIX = "Skipped:"
# Invariant a test pins: the ``already in the requested state`` wording appears
# whenever selected rows were dropped as no-ops, so a partial selection never
# reads as a full success (finding ``18-D1`` / risk ``R-5``).
ALREADY_IN_STATE_CLAUSE = "already in the requested state"


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

    Known gap (deferred to phase 15 ``15-AUTHZ-003``): ``ReadOnlyPasswordHashWidget``
    renders a "Reset password" link pointing at ``../password/``, which has **no
    route** to land on. ``django.contrib.auth.admin.UserAdmin`` serves that URL
    through its own ``get_urls()`` (``<id>/password/`` -> ``auth_user_password_change``),
    and that hook also injects the ``password_url`` context variable the widget
    template falls back from. This class declares no ``get_urls()``, so the link
    has no target: ``admin:auth_user_password_change`` does not resolve and the
    change view's own URLconf sends ``/admin/users/user/<id>/password/`` to the
    change route with a literal object id of ``<id>/password``. ``ModelAdmin.get_object``
    then calls ``pk.to_python("1/password")``, which raises ``ValidationError``,
    swallows it and returns ``None`` — so following the link is a 302 to the admin
    index carrying *"user with ID "1/password" doesn't exist. Perhaps it was
    deleted?"*. That reads as data loss, which is worse than a 404 would have been.
    The button did **not** exist before ``B-01``: it arrived only because ``B-01``
    switched the change view to ``UserChangeForm``; the pre-``B-01`` auto-built form
    rendered ``password`` as a plain writable ``CharField`` and showed no such button.

    The endpoint is **deliberately not built** here. An in-admin password-change
    view is a credential-write surface, and the gate this class can offer for it —
    ``has_change_permission`` -> ``is_staff`` — ignores ``obj``, so it would let a
    plain moderator overwrite a *superuser's* password (a moderator -> superuser
    takeover). ``get_urls()`` has **no** ``permissions`` hook, so that gate would
    have to live in the view or be tightened in the predicate; both are owned by
    phase 15, not by this documentation block.
    """

    form = UserChangeForm
    add_form = UserCreationForm

    # The group headings below ("Identity", "Account state", "Preferences",
    # "Audit") are bare literals, not ``gettext_lazy`` msgids, and Django emits
    # them into the admin HTML, so they are user-visible English-only labels on
    # a staff-only surface. This is a deliberate scope decision: translating
    # them requires adding ``ru``/``bs`` msgids, and the ``.po`` catalogs are
    # owned by whoever owns the i18n phase, not this one. The i18n completeness
    # gate does not cover ``apps/*/admin.py`` (``test_no_hardcoded_visible_text``
    # scans templates only), so nothing here will flag them; the decision is
    # recorded here instead. Field *names* in the tuples are model fields, not
    # labels, and need no translation.
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
    # Operator actions. The action strings must stay in sync with the method
    # names below. ``deactivate_user``/``reactivate_user`` route through
    # ``has_deactivate_permission`` via ``permissions=["deactivate"]``;
    # ``withdraw_consent_action`` routes through ``has_delete_permission`` (the
    # superuser-only predicate) via ``permissions=["delete"]``.
    actions = ["deactivate_user", "reactivate_user", "withdraw_consent_action"]

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

    def has_deactivate_permission(self, request) -> bool:
        """
        Gate whether the deactivate/reactivate actions may run (``18-D1``).

        Superusers and moderators may both run the actions; this matches
        ``User.role == ADMIN`` (``is_staff or is_superuser``) — the existing
        ``staff_required`` answer, not a new divergence. It is a distinct
        predicate from ``has_delete_permission`` on purpose: widening one must
        not widen the other, and a named predicate is discoverable by phase
        15's registry contract test (``15-AUTHZ-003`` / BLOCK 9).

        This predicate answers **"may this actor run the action"**, not **"may
        this actor act on this row"**. The latter is the target scope and lives
        in the service (``apps.users.services.deactivation``, ``18-Q7``):
        Django's ``permissions=`` mechanism cannot express a per-row scope, so
        a moderator's selection containing a staff/superuser row has that row
        removed by the service and reported back to the operator.
        """
        return request.user.is_staff or request.user.is_superuser

    @admin.action(
        description="Deactivate selected users", permissions=["deactivate"]
    )
    def deactivate_user(self, request, queryset) -> None:
        """Disable the selected accounts and report what was skipped."""
        result = deactivate_users(queryset, request.user)
        self.message_user(request, self._deactivation_message("Deactivated", result))

    @admin.action(
        description="Reactivate selected users", permissions=["deactivate"]
    )
    def reactivate_user(self, request, queryset) -> None:
        """Re-enable the selected accounts and report what was skipped."""
        result = reactivate_users(queryset, request.user)
        self.message_user(request, self._deactivation_message("Reactivated", result))

    def _deactivation_message(self, verb: str, result: DeactivationResult) -> str:
        """
        Build the operator toast for a deactivation/reactivation.

        Two requirements are mandatory (``18-D2``, risk ``R-5``): the message
        must state the **enforcement truth** on both tiers plus the Support
        carve-out (``DEACTIVATION_ENFORCEMENT_NOTE``), and it must **report
        dropped rows** so a partial selection does not read as success. Dropped
        rows are self/privileged refusals plus rows already in the requested
        state (``already_in_state``); a selection of 10 rows of which 3 were
        already disabled must not say "Deactivated 7 user(s)" with no hint that
        3 were dropped.
        """
        message = f"{verb} {result.changed} user(s). {DEACTIVATION_ENFORCEMENT_NOTE}"
        dropped: list[str] = []
        if result.skipped_self:
            dropped.append(f"{result.skipped_self} self")
        if result.skipped_privileged:
            dropped.append(f"{result.skipped_privileged} privileged (not permitted)")
        if result.already_in_state:
            dropped.append(f"{result.already_in_state} {ALREADY_IN_STATE_CLAUSE}")
        if dropped:
            message += f" {SKIPPED_ROWS_PREFIX} " + ", ".join(dropped) + "."
        return message

    # Registered in ``UserAdmin.actions`` above, superuser-gated via
    # ``permissions=["delete"]`` (Q-D7 resolved as WIRE). Gate ``G-B`` /
    # deferred work ``D-8`` originally left it unregistered so that the
    # irreversible PII erasure was not reachable from the admin; Q-D7 chose to
    # wire it because the phase-04 readonly field contract leaves this as the
    # only staff-side consent mutation. ``permissions=["delete"]`` is the whole
    # gate: Django's ``_filter_actions_by_permissions`` dispatches it to
    # ``has_delete_permission`` (``request.user.is_superuser``), so the action
    # is filtered out of ``get_actions()`` for a plain moderator AND a forged
    # POST is refused by action-form validation before the function is called.
    # No in-body ``is_superuser`` check is added — the framework hook is the
    # single gate.
    @admin.action(
        description="Withdraw consent for selected users", permissions=["delete"]
    )
    def withdraw_consent_action(self, request, queryset):
        """
        Withdraw consent for the selected users and report what was skipped.

        Superuser-gated via ``permissions=["delete"]``. Calls
        ``withdraw_consent`` per row, which sets consent_revoked_at, soft-deletes
        the user and their ads, nullifies PII, and writes the WITHDRAWN
        ``ConsentRecord`` audit row inside the same per-user transaction.

        Limitation (``06-NEW-02``): ``ConsentRecord`` has **no actor column**, so
        a staff-initiated revocation is evidenced as "the subject withdrew" —
        indistinguishable from a self-service withdrawal. The admin-initiated
        row also carries **no IP and no user agent** (the action supplies
        neither). No column is invented and no migration is added.

        A row already soft-deleted (``is_deleted=True``) is a no-op and is
        reported as skipped rather than counted as a withdrawal.
        """
        users = list(queryset)
        withdrawn = 0
        skipped = 0
        for user in users:
            if user.is_deleted:
                skipped += 1
                continue
            withdraw_consent(user)
            withdrawn += 1
        message = f"Withdrew consent for {withdrawn} user(s)."
        if skipped:
            message += (
                f" {SKIPPED_ROWS_PREFIX} {skipped} {ALREADY_IN_STATE_CLAUSE}."
            )
        self.message_user(request, message)


@admin.register(ConsentRecord)
class ConsentRecordAdmin(admin.ModelAdmin):
    """
    Read-mostly admin for the consent audit log (GDPR Article 7(1)).
    """

    list_display = [
        "id",
        "consent_given_at",
        "user",
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
