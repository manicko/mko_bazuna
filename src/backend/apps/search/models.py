"""
PopularSearch model for autocomplete suggestions.

Tracks popular search queries with hit count and last seen timestamp.
"""

import secrets

from apps.core.enums import AdSource
from django.db import models


class PopularSearch(models.Model):
    """Stores popular search queries for autocomplete suggestions."""

    query = models.CharField(max_length=200, db_index=True)
    query_normalized = models.CharField(max_length=200, db_index=True)
    hit_count = models.PositiveIntegerField(default=1)
    last_seen = models.DateTimeField(auto_now=True)

    # Origin of record (null = production, 'seed' = seed-generated)
    source = models.CharField(
        max_length=20,
        choices=[(s.value, s.value) for s in AdSource],
        default=None,
        null=True,
        blank=True,
        db_index=True,
        help_text="Origin of record (null = production, 'seed' = seed-generated)",
    )

    class Meta:
        db_table = "popular_searches"

    def __str__(self) -> str:
        return f"{self.query} ({self.hit_count})"


class SearchHistory(models.Model):
    """Stores user search queries for personalized autocomplete."""

    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="search_history",
    )
    query = models.CharField(max_length=200)
    query_normalized = models.CharField(max_length=200, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "search_history"
        indexes = [
            models.Index(fields=["user_id", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.query} (user={self.user_id})"


class SavedSearch(models.Model):
    """Stores saved search queries with filters for alert notifications."""

    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="saved_searches",
        help_text="User who saved this search",
    )
    query = models.TextField(
        blank=True,
        null=True,
        help_text="FTS query string (translated to Russian if Bosnian input)",
    )
    city = models.ForeignKey(
        "locations.City",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="saved_searches",
        help_text="Optional city filter",
    )
    category = models.ForeignKey(
        "categories.Category",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="saved_searches",
        help_text="Optional category filter (includes descendants)",
    )
    min_price = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="Minimum price filter, EUR-equivalent value (WR-04)",
    )
    max_price = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="Maximum price filter, EUR-equivalent value (WR-04)",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive searches do not receive notifications",
    )
    language = models.CharField(
        max_length=5,
        blank=True,
        null=True,
        default="bs",
        help_text="LanguageLocale code ('ru', 'bs' or 'en') used to search ads",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this saved search was created",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When this saved search was last modified",
    )
    last_notified_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Last time this search produced a notification",
    )
    unsubscribe_token = models.CharField(
        max_length=40,
        unique=True,
        db_index=True,
        null=True,
        blank=True,
        help_text=(
            "Opaque server-generated capability token for Telegram unsubscribe "
            "deep-links and inline callbacks (never derived from the PK)"
        ),
    )

    class Meta:
        db_table = "saved_searches"
        indexes = [
            models.Index(
                name="IX_saved_searches_user_active",
                fields=["user_id", "is_active"],
            ),
        ]

    def save(self, *args, **kwargs) -> None:
        """Auto-generate the opaque ``unsubscribe_token`` on creation."""
        if not self.unsubscribe_token:
            self.unsubscribe_token = secrets.token_urlsafe(24)  # 32 URL-safe chars
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"SavedSearch {self.id} for User {self.user_id}"


class SavedSearchNotification(models.Model):
    """Tracks sent notifications to prevent duplicate alerts for the same ad."""

    saved_search = models.ForeignKey(
        SavedSearch,
        on_delete=models.CASCADE,
        related_name="notifications",
        help_text="The saved search this notification belongs to",
    )
    ad = models.ForeignKey(
        "ads.Ad",
        on_delete=models.CASCADE,
        related_name="saved_search_notifications",
        help_text="The ad that was sent in the notification",
    )
    sent_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this notification was sent",
    )

    class Meta:
        db_table = "saved_search_notifications"
        constraints = [
            models.UniqueConstraint(
                fields=["saved_search", "ad"],
                name="uq_saved_search_ad",
            ),
        ]
        indexes = [
            models.Index(
                name="idx_saved_search_notif_sid",
                fields=["saved_search_id"],
            ),
        ]

    def __str__(self) -> str:
        return f"Notification {self.id}: saved_search={self.saved_search_id}, ad={self.ad_id}"
