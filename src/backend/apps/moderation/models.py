"""
Moderation models for Mko Bazuna.

ModerationCriteria singleton and ModeratorActionLog for audit trail.
"""

from django.db import models

from apps.core.enums import ModeratorActionType


class ModerationCriteria(models.Model):
    """
    Moderation criteria singleton for auto-moderation rules.

    Exactly one row exists. Edited by admin at runtime per US-A11.
    Applied to NEW ads (read current row at submit; no per-ad criteria_version).
    """

    title_min_length = models.PositiveIntegerField(
        default=5,
        help_text="Minimum title length in characters",
    )
    title_max_length = models.PositiveIntegerField(
        default=100,
        help_text="Maximum title length in characters",
    )
    description_min_length = models.PositiveIntegerField(
        default=10,
        help_text="Minimum description length in characters",
    )
    description_max_length = models.PositiveIntegerField(
        default=2000,
        help_text="Maximum description length in characters",
    )
    price_required = models.BooleanField(
        default=True,
        help_text="If True, price field is required for all ads",
    )
    min_images = models.PositiveIntegerField(
        default=1,
        help_text="Minimum number of images required",
    )
    max_images = models.PositiveIntegerField(
        default=5,
        help_text="Maximum number of images allowed",
    )
    banned_words = models.JSONField(
        default=list,
        blank=True,
        help_text="List of banned words for moderation (case-insensitive)",
    )
    max_ads_per_user = models.PositiveIntegerField(
        default=10,
        help_text="Maximum active ads per user",
    )
    duplicate_title_threshold = models.PositiveIntegerField(
        default=85,
        help_text="Percentage similarity threshold for duplicate title detection (0-100)",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Last update timestamp",
    )
    updated_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="criteria_updates",
        help_text="Admin user who last updated criteria",
    )

    class Meta:
        db_table = "moderation_criteria"
        verbose_name = "Moderation Criteria"
        verbose_name_plural = "Moderation Criteria"

    def __str__(self) -> str:
        return "Moderation Criteria"

    @classmethod
    def get_singleton(cls) -> ModerationCriteria:
        """Get the singleton instance, creating it if necessary."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class ModeratorActionLog(models.Model):
    """
    Moderator action audit log.

    Records all moderator actions for compliance and debugging.
    ad_id and user_id are nullable SET_NULL to preserve history on ad/user deletion.
    reason is TEXT and NEVER shown to seller (US-A11).
    """

    ad = models.ForeignKey(
        "ads.Ad",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="moderation_logs",
        help_text="Ad being moderated (SET NULL on deletion)",
    )
    user = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="moderation_actions",
        help_text="User who was moderated or performed action (SET NULL on erasure)",
    )
    action_type = models.CharField(
        max_length=20,
        choices=[(a.value, a.value) for a in ModeratorActionType],
        help_text="Type of moderator action",
    )
    reason = models.TextField(
        help_text="Moderation reason (INTERNAL ONLY - never shown to seller)",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Action timestamp",
    )

    class Meta:
        db_table = "moderation_action_logs"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Action {self.action_type} on Ad {self.ad_id}"