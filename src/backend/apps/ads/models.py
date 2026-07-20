"""
Ad and AdImage models for Mko Bazuna.

Single ads table with lifecycle timestamps and native PostgreSQL FTS search.
"""

import uuid

from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models

from apps.core.enums import AdSource, AdStatus


class Ad(models.Model):
    """
    Single ad table with lifecycle status and search support.

    Lifecycle transitions:
    - DRAFT → ON_MODERATION
    - ON_MODERATION → PUBLISHED | REJECTED | ON_MODERATION_FAILED
    - PUBLISHED → ARCHIVED → PUBLISHED (reactivation)
    - PUBLISHED → ON_MODERATION (text edits, hidden)
    - any → DELETED

    published_at resets on every PUBLISHED transition; original_published_at immutable.
    moderation_failed_at and rejected_at are mutually exclusive.
    """

    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="ads",
        help_text="Ad owner",
    )
    title = models.CharField(
        max_length=200,
        help_text="Ad title in Russian (translated from seller input)",
    )
    description = models.TextField(
        help_text="Ad description in Russian (translated from seller input)",
    )
    price = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="Whole BAM units; multi-currency deferred (YAGNI)",
    )

    # Foreign keys to reference data (task_023)
    category = models.ForeignKey(
        "categories.Category",
        on_delete=models.PROTECT,
        related_name="ads",
        help_text="Ad category",
    )
    city = models.ForeignKey(
        "locations.City",
        on_delete=models.PROTECT,
        related_name="ads",
        help_text="Ad city location",
    )

    # Denormalized category name (editable=False, trigger-synced)
    category_name = models.CharField(
        max_length=200,
        editable=False,
        help_text="Denormalized Russian category name; trigger-synced",
    )

    # Lifecycle
    status = models.CharField(
        max_length=20,
        choices=[(s.value, s.value) for s in AdStatus],
        default=AdStatus.DRAFT,
        help_text="Ad lifecycle status",
    )
    source = models.CharField(
        max_length=20,
        choices=[(s.value, s.value) for s in AdSource],
        default=AdSource.TELEGRAM,
        help_text="Origin of ad (phase 1 = bot only)",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Drives archive/delete timers; UPDATED on every PUBLISHED transition",
    )
    original_published_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Set once on FIRST publish; IMMUTABLE, audit only",
    )
    archived_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Auto-archive (2mo) or manual archive",
    )
    deleted_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Soft delete timestamp",
    )

    # Moderation timestamps (mutually exclusive)
    moderation_failed_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Failed auto-check; drives 7-day purge (mutually exclusive with rejected_at)",
    )
    rejected_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Manually rejected; drives 90-day cleanup (mutually exclusive with moderation_failed_at)",
    )

    # Search vector (NOT GENERATED ALWAYS - maintained by trigger)
    search_vector = SearchVectorField(
        blank=True,
        null=True,
        help_text="TSVECTOR for native PostgreSQL FTS; NOT GENERATED ALWAYS",
    )

    # Moderator references
    published_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="published_ads",
        help_text="Moderator who manually published",
    )
    moderated_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="moderated_ads",
        help_text="Moderator who manually rejected",
    )

    class Meta:
        db_table = "ads"
        indexes = [
            GinIndex(
                name="IX_ads_search_gin",
                fields=["search_vector"],
            ),
            models.Index(
                name="IX_ads_pub_listing",
                fields=["status", "category_id", "city_id", "-published_at"],
            ),
            models.Index(
                name="IX_ads_user_status",
                fields=["user_id", "status"],
            ),
            models.Index(
                name="IX_ads_archive_sweep",
                fields=["status", "published_at"],
            ),
            models.Index(
                name="IX_ads_delete_sweep",
                fields=["status", "published_at"],
            ),
            models.Index(
                name="IX_ads_purge_failed",
                fields=["status", "moderation_failed_at"],
            ),
            models.Index(
                name="IX_ads_rejected_sweep",
                fields=["status", "rejected_at"],
            ),
        ]

    def __str__(self) -> str:
        return f"Ad {self.id}: {str(self.title)[:50]}"


class AdImage(models.Model):
    """
    Ad image with UUID v4 storage key for URL anonymity.

    Only compressed Telegram photos accepted. Key contains NO user_id/telegram_id/username.
    """

    ad = models.ForeignKey(
        Ad,
        on_delete=models.CASCADE,
        related_name="images",
        help_text="Parent ad",
    )
    image = models.CharField(
        max_length=64,
        help_text="Storage key (ad_id + UUID v4, no user/telegram PII)",
    )
    telegram_file_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Telegram file_id; NOT used in <img src>",
    )
    position = models.PositiveIntegerField(
        default=0,  # pyright: ignore[reportArgumentType]
        help_text="Image order in gallery",
    )

    class Meta:
        db_table = "ad_images"
        ordering = ["position"]

    def __str__(self) -> str:
        return f"AdImage {self.id} for Ad {self.ad_id}"

    @property
    def image_url(self) -> str:
        """Return the media URL for this image."""
        from django.conf import settings

        return f"{settings.MEDIA_URL}{self.image}"

    @classmethod
    def generate_storage_key(cls) -> str:
        """Generate a UUID v4 storage key for anonymity."""
        return str(uuid.uuid4())