"""
Ad and AdImage models for Mko Bazuna.

Single ads table with lifecycle timestamps and native PostgreSQL FTS search.
"""


import os

from apps.core.enums import AdSource, AdStatus
from apps.lookups.enums import LookupGroupCode
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from django.db.models import Q
from django.utils import timezone

from django.conf import settings


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
    title_en = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Ad title in English",
    )
    title_bs = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Ad title in Bosnian",
    )
    description = models.TextField(
        help_text="Ad description in Russian (translated from seller input)",
    )
    description_en = models.TextField(
        blank=True,
        null=True,
        help_text="Ad description in English",
    )
    description_bs = models.TextField(
        blank=True,
        null=True,
        help_text="Ad description in Bosnian",
    )
    original_language = models.CharField(
        max_length=5,
        blank=True,
        null=True,
        help_text="Original language code of the ad (e.g. 'ru', 'en', 'bs')",
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

    # Listing purpose and features (lookup integration)
    listing_purpose = models.ForeignKey(
        "lookups.LookupItem",
        on_delete=models.PROTECT,
        limit_choices_to={"group__code": LookupGroupCode.LISTING_PURPOSE},
        related_name="ads",
        null=True,
        blank=True,
        help_text="What the user wants to do with the object",
    )
    features = models.ManyToManyField(
        "lookups.LookupItem",
        through="ads.AdFeature",
        through_fields=("ad", "feature"),
        blank=True,
        related_name="featured_ads",
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
        """Return localized title for *locale* with a fallback to the Russian base.

        The Russian base lives in the ``title`` column (``title_ru`` is not a
        real column), so the fallback chain is ``title_<locale>`` → ``title``.
        """
        for field in [f"title_{locale}", "title"]:
            val = getattr(self, field, None)
            if val:
                return val
        return ""

    def get_description(self, locale: str = "ru") -> str:
        """Return localized description for *locale* with a fallback to the Russian base.

        The Russian base lives in the ``description`` column
        (``description_ru`` is not a real column), so the fallback chain is
        ``description_<locale>`` → ``description``.
        """
        for field in [f"description_{locale}", "description"]:
            val = getattr(self, field, None)
            if val:
                return val
        return ""


class AdImage(models.Model):
    """Ad image with UUID v4 storage key for URL anonymity.

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
    thumbnail_small = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        help_text="Storage key for small thumbnail (<uuid>-small.jpg)",
    )
    thumbnail_medium = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        help_text="Storage key for medium thumbnail (<uuid>-medium.jpg)",
    )
    thumbnail_large = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        help_text="Storage key for large thumbnail (<uuid>-large.jpg)",
    )
    sha256 = models.CharField(
        max_length=64,
        db_index=True,
        blank=True,
        default="",
        help_text="SHA-256 hex digest for deduplication",
    )

    class Meta:
        db_table = "ad_images"
        ordering = ["position"]

    def __str__(self) -> str:
        return f"AdImage {self.id} for Ad {self.ad_id}"

    def save(self, *args, **kwargs) -> None:
        """Override save to auto-compute SHA-256 on creation and skip duplicates.

        If the same user already has an AdImage with the same SHA-256 hash,
        the duplicate is not created (returns early).
        """
        from apps.media.services.hash_service import FileHashService

        if self._state.adding or not self.sha256:
            media_root = settings.MEDIA_ROOT
            if isinstance(media_root, str):
                file_path = os.path.join(media_root, self.image)
            else:
                file_path = str(media_root / self.image)

            if os.path.exists(file_path):
                file_hash = FileHashService.calculate_sha256(file_path)
                self.sha256 = file_hash

                # Check for existing duplicate by same user
                if self._state.adding and self.ad_id:
                    user_id = Ad.objects.filter(id=self.ad_id).values_list(
                        "user_id", flat=True
                    ).first()
                    if user_id:
                        duplicate = AdImage.objects.filter(
                            sha256=file_hash,
                            ad__user_id=user_id,
                        ).exclude(id=self.id).exists()
                        if duplicate:
                            return  # Skip duplicate

        super().save(*args, **kwargs)

    @property
    def image_url(self) -> str:
        """Return the media URL for this image."""
        return f"{settings.MEDIA_URL}{self.image}"

    @property
    def thumbnail_small_url(self) -> str | None:
        if self.thumbnail_small:
            return f"{settings.MEDIA_URL}{self.thumbnail_small}"
        return None

    @property
    def thumbnail_medium_url(self) -> str | None:
        if self.thumbnail_medium:
            return f"{settings.MEDIA_URL}{self.thumbnail_medium}"
        return None

    @property
    def thumbnail_large_url(self) -> str | None:
        if self.thumbnail_large:
            return f"{settings.MEDIA_URL}{self.thumbnail_large}"
        return None


class AdFeature(models.Model):
    """Through model for Ad ↔ LookupItem (listing_feature) M:N relationship.

    Stores the display order of features on the ad page.
    """

    ad = models.ForeignKey(
        Ad,
        on_delete=models.CASCADE,
        related_name="ad_features",
    )
    feature = models.ForeignKey(
        "lookups.LookupItem",
        on_delete=models.CASCADE,
        limit_choices_to={"group__code": LookupGroupCode.LISTING_FEATURE},
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Display order of this feature on the ad page",
    )

    class Meta:
        db_table = "ad_features"
        unique_together = [("ad", "feature")]
        ordering = ["sort_order"]

    def __str__(self) -> str:
        return f"Ad {self.ad_id} -> {self.feature.slug}"
