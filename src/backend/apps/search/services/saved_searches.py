"""
Saved-search mutator service (shared by the HTML callers).

Extracted from the two HTML mutator stacks so that one request-free service
owns every ``SavedSearch`` write: the create modal
(``apps.search.views.save_search``) and the cabinet management views
(``apps.cabinet.views.saved_searches``) become thin callers.

All four operations are **request-free** (the project's service contract):
callers pass a ``User`` and a ``SavedSearchInput`` DTO, never an ``HttpRequest``.
Shared state is the ``SavedSearchInput`` DTO (``apps.search.schemas``) — the
single validated boundary both HTML callers already funnel their four optional
filters through (10-CQ-004).

Ownership: every row-scoped operation is scoped to the caller and raises
``SavedSearch.DoesNotExist`` when the row is missing or owned by another user.
Each caller maps that to its own response shape (the HTML views raise
``Http404``) — the same contract
``apps.ads.services.favorites.toggle_favorite`` uses.

Token semantics: the opaque ``unsubscribe_token`` is generated once, by
``SavedSearch.save()`` on creation, and is **never regenerated** by update,
toggle or delete. That behavior is preserved byte-for-byte by this extraction
(the service never writes the column).
"""

import logging

from apps.categories.models import Category
from apps.core.enums import LanguageLocale
from apps.core.utils.sanitize import redact_free_text
from apps.locations.models import City
from apps.search.models import SavedSearch
from apps.search.schemas import SavedSearchInput
from apps.users.models import User

logger = logging.getLogger(__name__)

# The persisted ``SavedSearch.query`` column bound; values over this are refused
# at the boundary rather than silently truncated (08-SRCH-011). Redaction runs
# first and never lengthens a value, so it can never turn a legal query into an
# over-cap one.
QUERY_MAX_LENGTH: int = 200


class QueryTooLongError(ValueError):
    """Raised by :func:`create_saved_search` when the redacted query is over cap.

    Carries the offending length so the caller can log and map it to its own
    refusal shape (the HTML view returns ``400``). Nothing is persisted when
    this is raised (08-SRCH-011).
    """

    def __init__(self, length: int) -> None:
        self.length = length
        super().__init__(
            f"Saved-search query is {length} chars, over the {QUERY_MAX_LENGTH} cap"
        )


def bound_query(query: str) -> str:
    """Strip, PII-redact and length-bound a raw saved-search query.

    This is the exact query pipeline the create view used before extraction:
    strip, redact (``redact_free_text`` — no truncation), then refuse a value
    over ``QUERY_MAX_LENGTH``. Redaction never lengthens its input and is
    idempotent, so the cap cannot be violated by the redaction step itself and
    a second pass is a no-op (08-SRCH-011).

    Callers persist the returned value via :func:`create_saved_search`; the
    refused case raises ``QueryTooLongError`` so the caller maps it to its own
    HTTP shape and stores nothing.

    Args:
        query: The raw query string.

    Returns:
        The stripped, redacted, at-or-under-cap query (possibly empty).

    Raises:
        QueryTooLongError: If the redacted query exceeds ``QUERY_MAX_LENGTH``.
    """
    redacted = redact_free_text(query.strip())
    if len(redacted) > QUERY_MAX_LENGTH:
        raise QueryTooLongError(len(redacted))
    return redacted


def create_saved_search(
    user: User,
    *,
    query: str,
    filters: SavedSearchInput,
    language: str | None = None,
) -> SavedSearch:
    """Create an active saved search for ``user`` from a raw query + filters.

    The query is bounded through :func:`bound_query` (strip + redact + cap) so
    this function is safe standalone: a caller that passes a raw query still
    gets a redacted, at-or-under-cap value persisted. ``bound_query`` is
    idempotent, so passing its output again is a no-op. Stores ``None`` for an
    empty query (the column is nullable) and ``is_active=True``. The
    ``unsubscribe_token`` is generated once by ``SavedSearch.save()``.

    Args:
        user: The owner of the new saved search.
        query: The raw query string (or an already-bounded one; re-redaction is
            a no-op).
        filters: The validated four optional filters (``SavedSearchInput``).
        language: The request locale code; falls back to the model default
            (``LanguageLocale.BOSNIAN``) when falsy — matching the create view.

    Returns:
        The freshly created :class:`SavedSearch`.

    Raises:
        QueryTooLongError: If the bounded query exceeds ``QUERY_MAX_LENGTH``.
            Nothing is stored.
    """
    bounded = bound_query(query)
    saved_search = SavedSearch.objects.create(
        user=user,
        query=bounded or None,
        city_id=filters.city_id,
        category_id=filters.category_id,
        min_price=filters.min_price,
        max_price=filters.max_price,
        language=language or LanguageLocale.BOSNIAN.value,
        is_active=True,
    )
    logger.info("Saved search %s created for user %s", saved_search.pk, user.pk)
    return saved_search


def update_saved_search(
    user: User,
    pk: int,
    *,
    query: str,
    filters: SavedSearchInput,
    language: str | None = None,
) -> SavedSearch:
    """Update ``user``'s saved search ``pk`` from a raw query + filters.

    Applies the same field semantics as the cabinet edit view: the query is
    stripped and stored as ``None`` when blank; ``city``/``category`` are
    resolved by primary key to stored rows (or ``None``); prices come straight
    from the DTO. ``language`` only overwrites the stored value when truthy
    (the edit view keeps the existing language otherwise). The
    ``unsubscribe_token`` is never touched — ``save(update_fields=...)`` omits it.

    Args:
        user: The caller; ownership is enforced.
        pk: The saved search primary key.
        query: The raw query string.
        filters: The validated four optional filters (``SavedSearchInput``).
        language: The request locale code, or a falsy value to keep the stored one.

    Returns:
        The updated :class:`SavedSearch`.

    Raises:
        SavedSearch.DoesNotExist: If no row ``pk`` is owned by ``user``.
    """
    saved_search = SavedSearch.objects.get(pk=pk, user=user)
    _apply_filters(saved_search, filters, query)
    saved_search.language = language or saved_search.language
    saved_search.save(
        update_fields=[
            "query",
            "city",
            "category",
            "min_price",
            "max_price",
            "language",
            "updated_at",
        ]
    )
    return saved_search


def toggle_saved_search(user: User, pk: int) -> SavedSearch:
    """Flip ``is_active`` on ``user``'s saved search ``pk`` (disable ≠ delete — D9).

    Writes exactly ``is_active`` + ``updated_at``; the ``unsubscribe_token`` is
    neither read nor regenerated.

    Args:
        user: The caller; ownership is enforced.
        pk: The saved search primary key.

    Returns:
        The updated :class:`SavedSearch`.

    Raises:
        SavedSearch.DoesNotExist: If no row ``pk`` is owned by ``user``.
    """
    saved_search = SavedSearch.objects.get(pk=pk, user=user)
    saved_search.is_active = not saved_search.is_active
    saved_search.save(update_fields=["is_active", "updated_at"])
    logger.info(
        "Saved search %s for user %s set active=%s",
        saved_search.pk,
        user.pk,
        saved_search.is_active,
    )
    return saved_search


def delete_saved_search(user: User, pk: int) -> None:
    """Delete ``user``'s saved search ``pk`` (removal, distinct from disable — D9).

    Args:
        user: The caller; ownership is enforced.
        pk: The saved search primary key.

    Raises:
        SavedSearch.DoesNotExist: If no row ``pk`` is owned by ``user``.
    """
    saved_search = SavedSearch.objects.get(pk=pk, user=user)
    logger.info(
        "Deleting saved search %s for user %s",
        saved_search.pk,
        user.pk,
    )
    saved_search.delete()


def _apply_filters(
    saved_search: SavedSearch, filters: SavedSearchInput, query: str
) -> None:
    """Copy the raw query + validated filters onto the saved search.

    Mirrors ``apps.cabinet.views.saved_searches._apply_filters`` exactly: the
    query is stripped and stored as ``None`` when blank; ``city``/``category``
    are resolved to stored rows by primary key (or ``None`` when unset).
    """
    saved_search.query = query.strip() or None

    saved_search.city = (
        City.objects.filter(pk=filters.city_id).first() if filters.city_id else None
    )
    saved_search.category = (
        Category.objects.filter(pk=filters.category_id).first()
        if filters.category_id
        else None
    )

    saved_search.min_price = filters.min_price
    saved_search.max_price = filters.max_price
