"""
Search history service for Mko Bazuna.

Records and retrieves search query history with deduplication
and per-user pruning to 50 entries.

Authenticated users are backed by the ``SearchHistory`` table. Anonymous
users are backed by the Django session (the ``db`` session store doubles as
the privacy retention policy), so no extra table is needed and history is
never merged into an account on login.
"""

import logging
from typing import Any

from apps.search.models import SearchHistory

logger = logging.getLogger(__name__)

# Maximum number of search history entries per user.
_MAX_HISTORY: int = 50

# Session key under which anonymous search history is stored.
_SESSION_KEY: str = "search_history"


def _record_session_history(session: Any, normalized: str, query: str) -> None:
    """Record a query in the session, deduped and capped at ``_MAX_HISTORY``.

    The session stores a list of ``{query, query_normalized}`` dicts ordered
    most-recent-first. The same normalized query replaces its previous entry
    (deduplication), and the list is pruned to ``_MAX_HISTORY`` entries.
    """
    entries = session.get(_SESSION_KEY) or []
    entries = [e for e in entries if e.get("query_normalized") != normalized]
    entries.insert(0, {"query": query, "query_normalized": normalized})
    session[_SESSION_KEY] = entries[:_MAX_HISTORY]


def record_search_history(user_id: int | None, query: str, session: Any = None) -> None:
    """
    Record a search query in the user's search history.

    Authenticated users (``user_id`` set) are stored in the database with a
    delete-before-create pattern for deduplication, then pruned to
    ``_MAX_HISTORY`` entries. Anonymous users (``user_id`` None) are stored in
    the provided Django ``session`` (deduped + capped) when one is supplied;
    without a session the call is a no-op.

    Args:
        user_id: The user's primary key, or None for anonymous users.
        query: The raw search query string.
        session: Optional Django session for anonymous session-scoped history.
    """
    normalized = query.strip().lower()
    if not normalized:
        return

    if user_id is None:
        if session is not None:
            _record_session_history(session, normalized, query)
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
    session: Any = None,
    prefix: str | None = None,
) -> list[str]:
    """
    Return the most recent search queries for a user.

    Authenticated users are ordered by ``created_at`` descending. Anonymous
    users are read from the provided Django ``session`` (most-recent-first,
    capped). When ``user_id`` is None and no session history exists, an empty
    list is returned.

    When ``prefix`` is provided, results are filtered so that only queries
    starting with the prefix (case-insensitive) are returned.

    Args:
        user_id: The user's primary key, or None for anonymous users.
        limit: Maximum number of entries to return (default 5).
        session: Optional Django session for anonymous session-scoped history.
        prefix: Optional prefix to filter queries by (case-insensitive).

    Returns:
        A list of query strings, most recent first.
    """
    if user_id is None:
        if session is not None:
            entries = session.get(_SESSION_KEY) or []
            if prefix:
                entries = [
                    e
                    for e in entries
                    if e.get("query", "").lower().startswith(prefix.lower())
                ]
            return [e["query"] for e in entries[:limit]]
        return []

    qs = SearchHistory.objects.filter(user_id=user_id).order_by("-created_at")
    if prefix:
        qs = qs.filter(query__istartswith=prefix)

    qs = qs.values_list("query", flat=True)[:limit]
    return list(qs)
