"""
Ad and AdImage models for Mko Bazuna.

Single ads table with lifecycle timestamps and native PostgreSQL FTS search.
"""


from apps.core.enums import AdSource, AdStatus
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Ad(models.Model):
    """
    Single ad table with lifecycle status and search support.

    Lifecycle transitions:
    - DRAFT -> ON_MODERATION
    - ON_MODERATION -> PUBLISHED | REJECTED | ON_MODERATION_FAILED
    - PUBLISHED -> ARCHIVED -> PUBLISHED (reactivation)
    - PUBLISHED -> ON_MODERATION (text edits, hidden)
    - any -> DELETED

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
                condition=Q(status=AdStatus.PUBLISHED),
            ),
            models.Index(
                name="IX_ads_user_status",
                fields=["user_id", "status"],
            ),
            models.Index(
                name="IX_ads_archive_sweep",
                fields=["status", "published_at"],
                condition=Q(status=AdStatus.PUBLISHED),
            ),
            models.Index(
                name="IX_ads_delete_sweep",
                fields=["status", "published_at"],
                condition=Q(status=AdStatus.ARCHIVED),
            ),
            models.Index(
                name="IX_ads_purge_failed",
                fields=["status", "moderation_failed_at"],
                condition=Q(status=AdStatus.ON_MODERATION_FAILED),
            ),
            models.Index(
                name="IX_ads_rejected_sweep",
                fields=["status", "rejected_at"],
                condition=Q(status=AdStatus.REJECTED),
            ),
        ]

    def __str__(self) -> str:
        return f"Ad {self.id}: {str(self.title)[:50]}"

    def transition_to(
            self,
            target: AdStatus,
            moderator_id: int | None = None,
        ) -> None:
            """
            Transition ad to target status with validation and timer side-effects.

            Enforces the allowed transition matrix:
            - DRAFT -> ON_MODERATION
            - ON_MODERATION -> PUBLISHED | REJECTED | ON_MODERATION_FAILED
            - PUBLISHED -> ARCHIVED
            - ARCHIVED -> PUBLISHED | ON_MODERATION
            - PUBLISHED -> ON_MODERATION
            - any -> DELETED

            Side-effects:
            - -> PUBLISHED: published_at = now(); original_published_at set once if None
            - -> DELETED: deleted_at = now()
            - -> ARCHIVED: archived_at = now()
            - -> ON_MODERATION_FAILED: moderation_failed_at = now()
            - -> REJECTED: rejected_at = now()
            - -> ON_MODERATION: clears moderation_failed_at, rejected_at, archived_at

            Args:
                target: The target AdStatus to transition to.
                moderator_id: Optional moderator ID for PUBLISHED/REJECTED transitions.

            Raises:
                ValueError: If the transition is not allowed.
            """
            # Define allowed transitions as a mapping
            ALLOWED_TRANSITIONS: dict[AdStatus, set[AdStatus]] = {
                AdStatus.DRAFT: {AdStatus.ON_MODERATION},
                AdStatus.ON_MODERATION: {
                    AdStatus.PUBLISHED,
                    AdStatus.REJECTED,
                    AdStatus.ON_MODERATION_FAILED,
                },
                AdStatus.PUBLISHED: {AdStatus.ARCHIVED, AdStatus.ON_MODERATION},
                AdStatus.ARCHIVED: {AdStatus.PUBLISHED, AdStatus.ON_MODERATION},
                AdStatus.REJECTED: set(),  # Terminal
                AdStatus.ON_MODERATION_FAILED: set(),  # Terminal
                AdStatus.DELETED: set(),  # Terminal
            }

            current = AdStatus(self.status)

            # DELETED is a terminal state - no transitions allowed from it
            if current == AdStatus.DELETED:
                raise ValueError(
                    f"Cannot transition from DELETED to {target.value}. DELETED is terminal."
                )

            # any -> DELETED is always allowed
            if target == AdStatus.DELETED:
                if current != AdStatus.DELETED:
                    self.status = AdStatus.DELETED
                    self.deleted_at = timezone.now()
                    self.save(update_fields=["status", "deleted_at"])
                return

            # Validate transition against allowed matrix
            allowed_targets = ALLOWED_TRANSITIONS.get(current, set())
            if target not in allowed_targets:
                raise ValueError(
                    f"Invalid transition: {current.value} -> {target.value}. "
                    f"Allowed targets from {current.value}: {', '.join(t.value for t in allowed_targets) or 'none'}"
                )

            # Apply transition with side-effects
            now_val = timezone.now()
            update_fields = ["status"]

            if target == AdStatus.PUBLISHED:
                # Reset published_at on every PUBLISHED transition
                self.published_at = now_val
                update_fields.append("published_at")

                # Set original_published_at once (immutable)
                if self.original_published_at is None:
                    self.original_published_at = now_val
                    update_fields.append("original_published_at")

                # Set published_by if moderator provided
                if moderator_id is not None:
                    self.published_by_id = moderator_id
                    update_fields.append("published_by")

            elif target == AdStatus.ARCHIVED:
                self.archived_at = now_val
                update_fields.append("archived_at")

            elif target == AdStatus.ON_MODERATION_FAILED:
                self.moderation_failed_at = now_val
                update_fields.append("moderation_failed_at")
                # Clear rejected_at if it was set (mutually exclusive)
                if self.rejected_at is not None:
                    self.rejected_at = None
                    update_fields.append("rejected_at")

            elif target == AdStatus.REJECTED:
                self.rejected_at = now_val
                update_fields.append("rejected_at")
                # Set moderated_by if moderator provided
                if moderator_id is not None:
                    self.moderated_by_id = moderator_id
                    update_fields.append("moderated_by")
                # Clear moderation_failed_at if it was set (mutually exclusive)
                if self.moderation_failed_at is not None:
                    self.moderation_failed_at = None
                    update_fields.append("moderation_failed_at")

            elif target == AdStatus.ON_MODERATION:
                # Clear moderation and archive timestamps when re-submitting for moderation
                if self.moderation_failed_at is not None:
                    self.moderation_failed_at = None
                    update_fields.append("moderation_failed_at")
                if self.rejected_at is not None:
                    self.rejected_at = None
                    update_fields.append("rejected_at")
                if self.archived_at is not None:
                    self.archived_at = None
                    update_fields.append("archived_at")

            self.status = target
            self.save(update_fields=update_fields)

    def get_title(self, locale: str = "ru") -> str:
        """Return localized title with fallback chain: locale → ru → first available."""
        # Priority: locale column > Russian > original
        for field in [f"title_{locale}", "title_ru", "title"]:
            val = getattr(self, field, None)
            if val:
                return val
        return ""

    def get_description(self, locale: str = "ru") -> str:
        """Return localized description with fallback chain: locale → ru → first available."""
        for field in [f"description_{locale}", "description_ru", "description"]:
            val = getattr(self, field, None)
            if val:
                return val
        return ""


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
        help_text="Storage key (UUID v4 + .jpg, no ad_id/user/telegram PII)",
    )
    telegram_file_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Telegram file_id; NOT used in <img src>",
    )
    position = models.PositiveIntegerField(
        default=0,
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
