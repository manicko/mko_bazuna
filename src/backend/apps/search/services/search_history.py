"""
Search history service for Mko Bazuna.

Records and retrieves user search query history with deduplication
and per-user pruning to 50 entries.
"""

import logging

from apps.search.models import SearchHistory

logger = logging.getLogger(__name__)

# Maximum number of search history entries per user.
_MAX_HISTORY: int = 50


def record_search_history(user_id: int | None, query: str) -> None:
    """
    Record a search query in the user's search history.

    If ``user_id`` is None (anonymous user), the call is a no-op.
    Uses a delete-before-create pattern for deduplication of the same
    normalized query.  Prunes the oldest entries when the per-user
    history exceeds ``_MAX_HISTORY``.

    Args:
        user_id: The user's primary key, or None for anonymous users.
        query: The raw search query string.
    """
    if user_id is None:
        return

    normalized = query.strip().lower()
    if not normalized:
        return

    # Deduplicate: delete existing entry with the same normalized query.
    SearchHistory.objects.filter(
        user_id=user_id,
        query_normalized=normalized,
    ).delete()

    # Create the new entry.
    SearchHistory.objects.create(
        user_id=user_id,
        query=query,
        query_normalized=normalized,
    )

    # Prune to _MAX_HISTORY entries per user.
    total = SearchHistory.objects.filter(user_id=user_id).count()
    if total > _MAX_HISTORY:
        excess = total - _MAX_HISTORY
        ids_to_delete = (
            SearchHistory.objects.filter(user_id=user_id)
            .order_by("created_at")
            .values_list("pk", flat=True)[:excess]
        )
        SearchHistory.objects.filter(pk__in=list(ids_to_delete)).delete()


def get_user_search_history(
    user_id: int | None,
    limit: int = 5,
) -> list[str]:
    """
    Return the most recent search queries for a user.

    Results are ordered by ``created_at`` descending.  If ``user_id``
    is None, an empty list is returned.

    Args:
        user_id: The user's primary key, or None for anonymous users.
        limit: Maximum number of entries to return (default 5).

    Returns:
        A list of query strings, most recent first.
    """
    if user_id is None:
        return []

    qs = (
        SearchHistory.objects.filter(user_id=user_id)
        .order_by("-created_at")
        .values_list("query", flat=True)[:limit]
    )

    return list(qs)