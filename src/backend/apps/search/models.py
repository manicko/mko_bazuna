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

class SearchHistory(models.Model):
    """Stores user search queries for personalized autocomplete."""

    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    query = models.CharField(max_length=200)
    query_normalized = models.CharField(max_length=200, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "search_history"
