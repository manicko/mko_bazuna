"""
PopularSearch model for autocomplete suggestions.

Tracks popular search queries with hit count and last seen timestamp.
"""

from django.db import models


class PopularSearch(models.Model):
    """Stores popular search queries for autocomplete suggestions."""

    query = models.CharField(max_length=200, db_index=True)
    query_normalized = models.CharField(max_length=200, db_index=True)
    hit_count = models.PositiveIntegerField(default=1)
    last_seen = models.DateTimeField(auto_now=True)

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

    user = models.ForeignKey("users.User", on_delete=models.CASCADE)
    query = models.TextField(blank=True, null=True)
    city = models.ForeignKey("locations.City", on_delete=models.SET_NULL, blank=True, null=True)
    category = models.ForeignKey("categories.Category", on_delete=models.SET_NULL, blank=True, null=True)
    min_price = models.PositiveIntegerField(blank=True, null=True)
    max_price = models.PositiveIntegerField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "saved_searches"

    def __str__(self) -> str:
        return f"SavedSearch(user={self.user_id}, query={self.query})"

class SavedSearchNotification(models.Model):
    """Tracks sent notifications to prevent duplicate alerts for the same ad."""

    saved_search = models.ForeignKey(
        SavedSearch, on_delete=models.CASCADE, related_name="notifications"
    )
    ad = models.ForeignKey("ads.Ad", on_delete=models.CASCADE, related_name="saved_search_notifications")
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "saved_search_notifications"
        constraints = [
            models.UniqueConstraint(fields=["saved_search", "ad"], name="uq_saved_search_ad")
        ]

    def __str__(self) -> str:
        return f"SavedSearchNotification(saved_search={self.saved_search_id}, ad={self.ad_id})"
