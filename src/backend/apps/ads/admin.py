"""
Django admin registration for ads app.

Admin with status/category/city/date filters and reject/ban actions.
Includes listing_purpose and features display for lookup integration.

The ``AdAdmin`` change form is an explicit field contract (finding AD-001).
Django's auto-built form exposed 24 editable fields, four of which are traps:
``user`` (silent owner transfer), ``original_published_at`` (declared
IMMUTABLE, audit only) and the four ``search_vector*`` columns (rewritten by
the ``ads_search_vector_update`` trigger on every write, so a manual edit is
silently discarded). A POST selecting a status whose check constraint the
form cannot satisfy (``REJECTED`` / ``ON_MODERATION_FAILED``, or
``PUBLISHED`` / ``ARCHIVED`` / ``DELETED`` with a blank timestamp) raised an
``IntegrityError`` -> HTTP 500. ``save_model`` routes the status write
through ``Ad.transition_to`` so the matrix guards terminal states and the
audit row is written through the existing moderation service.
"""

import logging

from django import forms
from django.contrib import admin

from apps.ads.models import Ad, AdImage
from apps.core.enums import AdStatus, ModeratorActionType
from apps.moderation.admin_actions import (
    bulk_approve,
    bulk_ban_users,
    bulk_delete,
    bulk_reject,
    soft_delete_ad,
)
from apps.moderation.services.exceptions import MaxAdsExceeded
from apps.moderation.services.moderation_log import (
    set_published,
    set_rejected,
)
from apps.moderation.services.priority import PriorityService

logger = logging.getLogger(__name__)

# The timestamp column each status's check constraint requires. A form POST
# selecting one of these statuses is a 500 unless the constraint can be
# satisfied; ``AdAdminChangeForm.clean`` turns that into a form error.
_TIMESTAMP_FIELD_FOR_STATUS: dict[AdStatus, str] = {
    AdStatus.PUBLISHED: "published_at",
    AdStatus.ARCHIVED: "archived_at",
    AdStatus.DELETED: "deleted_at",
    AdStatus.REJECTED: "rejected_at",
    AdStatus.ON_MODERATION_FAILED: "moderation_failed_at",
}


class AdAdminChangeForm(forms.ModelForm):
    """Change form enforcing the constraints the raw model form cannot.

    ``clean`` turns what was an undeclared HTTP 500 into an actionable
    form error. Selecting a status whose check constraint the form cannot
    satisfy previously reached the database as a raw ``UPDATE`` and raised
    ``IntegrityError`` -> 500. Two classes are covered:

    * ``REJECTED`` / ``ON_MODERATION_FAILED`` — their required timestamp
      columns (``rejected_at`` / ``moderation_failed_at``) are read-only, so
      the form can never supply them;
    * ``PUBLISHED`` / ``ARCHIVED`` / ``DELETED`` — their own timestamp field is
      editable, so the form rejects a blank value.

    A POST that supplies the required timestamp for the latter group proceeds;
    the transition then writes/refreshes the timestamp through the matrix.
    """

    class Meta:
        model = Ad
        fields = "__all__"

    def clean(self):
        """Reject status values whose check constraint the form cannot satisfy.

        Runs after every field is cleaned. A field-level ``clean_status`` would
        not work: ``status`` precedes ``published_at``/``archived_at``/
        ``deleted_at`` in the field order, so those values are not yet in
        ``cleaned_data`` when ``clean_status`` runs.
        """
        cleaned = super().clean()
        status_value = cleaned.get("status")
        if status_value is None:
            return cleaned
        status = AdStatus(status_value)

        if (
            self.instance.pk
            and AdStatus(self.instance.status) == AdStatus.DELETED
            and status != AdStatus.DELETED
        ):
            self.add_error(
                "status",
                "DELETED is a terminal state; its status cannot be changed.",
            )
            return cleaned

        if status in (AdStatus.REJECTED, AdStatus.ON_MODERATION_FAILED):
            self.add_error(
                "status",
                f"Status '{status.value}' cannot be set from this form: its "
                "timestamp column is read-only. Use the moderation actions "
                "instead.",
            )
            return cleaned

        timestamp_field = _TIMESTAMP_FIELD_FOR_STATUS.get(status)
        if timestamp_field is None:
            return cleaned

        supplied = cleaned.get(timestamp_field)
        stored = getattr(self.instance, timestamp_field, None)
        if not supplied and not stored:
            self.add_error(
                "status",
                f"Status '{status.value}' requires '{timestamp_field}' to be set.",
            )
        return cleaned


def user_link(obj: Ad) -> str:
    """Display user telegram_id as link (INTERNAL ONLY — staff-only).

    This column is rendered in ``AdAdmin.list_display`` and is restricted to
    staff/superuser via ``AdAdmin.has_view_permission`` and
    ``AdAdmin.has_change_permission``. Erased accounts render blank because
    ``withdraw_consent`` nulls ``telegram_id`` (``deletion.py:132``) inside
    ``transaction.atomic()``.
    """
    if obj.user:
        return str(obj.user)
    return "-"


user_link.short_description = "User ID"  # type: ignore[attr-defined]


def rejected_reason(obj: Ad) -> str:
    """Display rejection reason from moderation log (INTERNAL ONLY)."""
    log = obj.moderation_logs.filter(action_type=ModeratorActionType.REJECT).last()
    if log:
        return log.reason[:100] if len(log.reason) > 100 else log.reason
    return "-"


rejected_reason.short_description = "Rejection Reason"  # type: ignore[attr-defined]


def action_ad_link(obj: AdImage) -> str:
    """Display parent ad as link."""
    return str(obj.ad_id)


action_ad_link.short_description = "Ad ID"  # type: ignore[attr-defined]


def features_list(obj: Ad) -> str:
    """Display features as comma-separated slugs."""
    return ", ".join(f.slug for f in obj.features.all())


features_list.short_description = "Features"  # type: ignore[attr-defined]


@admin.register(Ad)
class AdAdmin(admin.ModelAdmin):
    """
    Ad admin with listing filters and reject/ban moderation actions.

    Failed-ads list shows rejection reason (INTERNAL ONLY, never to seller).
    The ``user_link`` column in ``list_display`` (non-identifying ``str(obj.user)``)
    is staff-only INTERNAL ONLY — access is gated by ``has_view_permission`` /
    ``has_change_permission`` (``is_staff or is_superuser`` only).

    The change form is an explicit field contract (finding AD-001):

    * ``user`` is read-only — no story authorises reassigning an ad, and a save
      would silently move the ad, its analytics and its ``AdFavorite`` rows.
    * ``original_published_at`` is read-only — ``db-schema.md`` and the model's
      own ``help_text`` declare it IMMUTABLE, audit only.
    * the four ``search_vector*`` columns are dropped from the form entirely —
      the ``ads_search_vector_update`` trigger rewrites them on every write, so
      a manual edit is silently discarded.

    ``status`` stays editable deliberately: Q1 (may a moderator move an ad's
    status, and through which seam?) is an open owner decision and BLOCK 6B
    decides it. ``save_model`` routes a form-driven status change through
    ``Ad.transition_to`` so the matrix guards terminal states, and through the
    existing moderation services so the audit row has exactly one writer.
    """

    form = AdAdminChangeForm

    list_display = [
        "id",
        "title",
        "status",
        "category",
        "city",
        "listing_purpose",
        user_link,
        "published_at",
        rejected_reason,
    ]
    list_filter = [
        "status",
        "category",
        "city",
        "listing_purpose",
        "created_at",
        "published_at",
        "moderation_priority__priority_level",
    ]
    search_fields = ["title", "description"]
    # Fields that are inert through the change form. ``archived_at`` stays
    # editable: its blank-timestamp case is a form validation error (see
    # ``AdAdminChangeForm.clean``) and the ARCHIVED transition itself
    # runs through the matrix, which writes the timestamp.
    readonly_fields = [
        "moderation_failed_at",
        "rejected_at",
        "published_by",
        "moderated_by",
        "listing_purpose",
        "user",
        "original_published_at",
    ]
    # The four ``search_vector*`` columns are dropped from the form entirely.
    # They are excluded (not read-only) because the trigger rewrites them on
    # every write; rendering them read-only would advertise editable data that
    # the database then discards.
    exclude = [
        "search_vector",
        "search_vector_ru",
        "search_vector_bs",
        "search_vector_en",
    ]
    date_hierarchy = "created_at"
    actions = [
        "action_reject",
        "action_ban_user",
        "action_soft_delete",
        "action_approve",
    ]

    def get_queryset(self, request):
        """Optimize queryset with related select and priority prefetch."""
        qs = super().get_queryset(request)
        return qs.select_related(
            "user", "category", "city", "listing_purpose"
        ).prefetch_related("moderation_priority", "features")

    def has_view_permission(self, request, obj=None) -> bool:
        """Restrict view to staff/superuser only."""
        return request.user.is_staff or request.user.is_superuser

    def has_change_permission(self, request, obj=None) -> bool:
        """Restrict change to staff/superuser only."""
        return request.user.is_staff or request.user.is_superuser

    def save_model(self, request, obj, form, change):
        """Persist the form's fields, then route any status change through the matrix.

        Two clearly separated paths, branched on ``change`` because
        ``_changeform_view`` calls ``save_form`` (which does **not** assign a pk
        on add) before ``save_model``:

        * **Add** (``change is False``): there is no stored row and therefore no
          source status to read. ``user`` is read-only on this form (finding
          AD-001: a save must not silently transfer ownership), so the acting
          staff user becomes the owner — the only value that satisfies the
          ``NOT NULL`` constraint and the one a moderator creating an ad in the
          admin owns by definition. The requested status is applied through the
          sanctioned seam **without** a source-status lookup.

        * **Change** (``change is True``): ``Ad.transition_to`` starts with
          ``refresh_from_db()``, which would discard every in-memory field value
          the form just cleaned (title, description, price, ...). The safe
          ordering is therefore: (1) write the form's data **without** the
          status change, so the raw ``UPDATE`` can never violate a check
          constraint, then (2) perform the status change through the sanctioned
          service. Read-only/excluded fields (including
          ``original_published_at`` and the four ``search_vector*`` columns) are
          not on the form, so the instance still carries their stored values and
          the raw UPDATE leaves them untouched.

        A status change to a target with an audit service is routed through
        that service (``set_published`` / ``set_rejected`` / ``soft_delete_ad``)
        so there is exactly one writer of ``ModeratorActionLog``. A transition
        to a target with no audit service (``ARCHIVED`` / ``ON_MODERATION`` /
        ``DRAFT`` / ``ON_MODERATION_FAILED``) still goes through
        ``Ad.transition_to`` for the matrix guard but writes no audit row —
        the residual recorded for BLOCK 6B.

        No audit row is written when the source already equals the target
        (``transition_to`` returns the source status). ``MaxAdsExceeded`` on
        publish is surfaced as an admin message rather than a 500.
        """
        if not change:
            # Add path: no source status exists yet, so no lookup is possible.
            # ``user`` is read-only on the form; the acting staff user owns the
            # row the admin creates.
            obj.user_id = request.user.id
            super().save_model(request, obj, form, change)
            self._route_status_change(request, obj, AdStatus(obj.status))
            return

        status_changed = "status" in form.changed_data
        target_status = AdStatus(obj.status)

        if not status_changed:
            super().save_model(request, obj, form, change)
            return

        # Step 1: persist the non-status form data. ``status`` must be the
        # model's current value so the raw write satisfies every check
        # constraint; ``transition_to`` will set the real target afterwards.
        current_status = Ad.objects.values_list("status", flat=True).get(pk=obj.pk)
        obj.status = current_status

        super().save_model(request, obj, form, change)

        # Step 2: apply the status change through the sanctioned seam.
        self._route_status_change(request, obj, target_status)

    def _route_status_change(
        self, request, obj: Ad, target: AdStatus
    ) -> None:
        """Apply *target*, surfacing business failures as admin messages.

        ``MaxAdsExceeded`` (the owner hit the active-ads cap) and
        ``ValueError`` (the state machine refused the transition) are expected
        business outcomes of a form-driven status change, not faults: render
        each as an admin message rather than an HTTP 500. Neither branch
        swallows ``Ad.DoesNotExist`` — that would re-introduce the add-view
        defect this method's callers exist to prevent.
        """
        try:
            self._apply_status_change(request, obj, target)
        except MaxAdsExceeded as exc:
            self.message_user(
                request,
                f"Ad {obj.pk} was not published: the owner has reached "
                f"max {exc.limit} active ads (currently {exc.current_count}).",
                level="error",
            )
        except ValueError as exc:
            self.message_user(
                request, f"Ad {obj.pk} status not changed: {exc}", level="error"
            )

    def _apply_status_change(self, request, obj: Ad, target: AdStatus) -> None:
        """Route a form-driven status change through the sanctioned write path.

        The source status is read from the row once, here, and the write is
        skipped when it already equals ``target`` — so a concurrent writer that
        won the race produces no duplicate audit row. This is the consumer of
        ``Ad.transition_to``'s returned source status: the no-audit-on-no-op
        guarantee is enforced at this boundary, and the non-service targets read
        the same ``current`` rather than issuing a second query.

        The acting staff user's ID is passed only to the services that accept
        it (``set_published`` / ``set_rejected``). ``soft_delete_ad`` writes its
        own audit row with a reason.

        ``REJECTED`` is not reachable through the form in BLOCK 6A (its
        timestamp column is read-only, so ``clean`` refuses it); its
        ``set_rejected`` branch is retained as the seam BLOCK 6B selects.
        """
        current = AdStatus(
            Ad.objects.values_list("status", flat=True).get(pk=obj.pk)
        )
        if current == target:
            # A concurrent writer already made the change; no audit row is
            # written for a no-op.
            return

        if target == AdStatus.PUBLISHED:
            set_published(obj, moderator_id=request.user.id)
        elif target == AdStatus.REJECTED:
            set_rejected(
                obj,
                moderator_id=request.user.id,
                reason="Status set by moderator via admin change form",
            )
        elif target == AdStatus.DELETED:
            soft_delete_ad(
                obj,
                moderator_id=request.user.id,
                reason="Status set by moderator via admin change form",
            )
        else:
            # ARCHIVED / ON_MODERATION / DRAFT / ON_MODERATION_FAILED have no
            # status+audit service. Run the transition for the matrix guard
            # without inventing a second writer of ModeratorActionLog. This is
            # the recorded residual for BLOCK 6B. The returned source is the
            # same value the no-op guard above already consumed.
            source = obj.transition_to(target, moderator_id=request.user.id)
            logger.debug(
                "Admin form transitioned ad %s from %s to %s",
                obj.pk,
                source.value,
                target.value,
            )

    @admin.action(description="Reject selected ads")
    def action_reject(self, request, queryset):
        """Bulk reject action for moderation."""
        count = bulk_reject(
            queryset, request.user.id, "Bulk rejection via admin action"
        )
        self.message_user(request, f"Rejected {count} ad(s).", level="success")

    @admin.action(description="Approve selected ads")
    def action_approve(self, request, queryset):
        """Bulk approve action for moderation."""
        count = bulk_approve(queryset, request.user.id)
        self.message_user(
            request, f"Approved {count} ad(s) for publication.", level="success"
        )

    @admin.action(description="Ban users from selected ads")
    def action_ban_user(self, request, queryset):
        """Bulk ban users from selected ads."""
        count = bulk_ban_users(queryset, request.user.id, "Bulk ban via admin action")
        self.message_user(request, f"Banned {count} user(s).", level="success")

    @admin.action(description="Soft delete selected ads")
    def action_soft_delete(self, request, queryset):
        """Bulk soft delete action for moderation."""
        count = bulk_delete(queryset, request.user.id, "Bulk deletion via admin action")
        self.message_user(request, f"Deleted {count} ad(s).", level="success")

    def changelist_view(self, request, extra_context=None):
        """Custom changelist with moderation queue presets and priority stats."""
        extra_context = extra_context or {}

        # Add quick filter links for moderation queues
        extra_context["moderation_queues"] = [
            {"name": "On Moderation", "status": AdStatus.ON_MODERATION},
            {"name": "Failed", "status": AdStatus.ON_MODERATION_FAILED},
            {"name": "Rejected", "status": AdStatus.REJECTED},
        ]

        # Add priority queue stats for admin dashboard
        service = PriorityService()
        extra_context["priority_queue_stats"] = service.get_priority_counts()

        return super().changelist_view(request, extra_context=extra_context)


@admin.register(AdImage)
class AdImageAdmin(admin.ModelAdmin):
    """
    AdImage admin for managing ad images.
    """

    list_display = ["id", action_ad_link, "position"]
    list_filter = ["position"]
    search_fields = ["ad__title"]
    readonly_fields = ["image", "telegram_file_id", "position"]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_view_permission(self, request, obj=None) -> bool:
        return request.user.is_staff or request.user.is_superuser

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
