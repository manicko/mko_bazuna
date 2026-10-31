"""
FTS search pipeline service for Mko Bazuna.

Request-free extraction of the language-aware full-text-search pipeline that
previously lived in ``apps.search.views.search``. The buyer's search query is
matched against the **per-language** search vector column, so no external
translation runs on the search critical path.

The public entry points of the pipeline are the helpers below: the FTS filter +
relevance sort (:func:`_apply_fts_filtering`), the cache-hit page rank restore
(:func:`_rank_cache_hit_page`), the display count/truncation resolver
(:func:`_resolve_search_count`) and the single-word fuzzy category ladder
(:func:`_is_single_word`, :func:`_fuzzy_category_match`,
:func:`_fuzzy_match_by_name`, :func:`_ids_for_exact_name`,
:func:`_resolve_unique_category`).

Locale coupling. Every helper that needs the active search language takes an
explicit ``locale: LanguageLocale`` argument. The view resolves the locale once
from ``request.LANGUAGE_CODE`` and threads it down, so the pipeline itself never
touches an ``HttpRequest`` — the single approved de-coupling of the extraction.

Vector access is exclusively through :attr:`LanguageLocale.fts_vector_field` and
:attr:`LanguageLocale.fts_config`; no raw language string appears in this module.
Side effects (analytics, popular-search, search history) are deliberately NOT
part of this module — the caller records them so they fire for every
query-bearing search regardless of cache state.
"""

import re
from typing import Final

from django.contrib.postgres.search import SearchQuery, SearchRank
from django.core.paginator import Paginator
from django.db.models import Case, F, IntegerField, QuerySet, When

from apps.ads.services.listings_query import ListingsQueryParams
from apps.categories.models import Category
from apps.categories.services.fuzzy import match_category
from apps.core.enums import AdSort, LanguageLocale
from apps.search.services.cache import SEARCH_CACHE_MAX_HITS
from apps.search.services.category_fuzzy import get_active_category_names

# Maximum accepted length of a search query string. Truncating at the input edge
# prevents a DataError when the value is persisted into CharField(max_length=200)
# via increment_popular_search / record_search_history (SRH-001).
MAX_SEARCH_QUERY_LENGTH: Final[int] = 200


def _apply_fts_filtering(
    queryset: QuerySet,
    query: str,
    params: ListingsQueryParams,
    locale: LanguageLocale,
    *,
    all_categories: bool = False,
) -> QuerySet:
    """Apply per-language FTS filtering and relevance sort (pure, no side effects).

    Adds ``SearchRank`` annotation + TSVector filter on the locale's vector
    column, and overrides sort to keep ``-rank`` as a tiebreaker.

    ``locale`` is the active search language, resolved by the caller from
    ``request.LANGUAGE_CODE``. The vector column and text-search config are read
    from :attr:`LanguageLocale.fts_vector_field` / :attr:`LanguageLocale.fts_config`
    — no raw language string is used here.

    ``all_categories=True`` is the buyer's per-request opt-out of the single-word
    fuzzy category narrowing (O8): the narrowing block is skipped for that request
    only, so the same query runs against the whole tree. With the default
    ``all_categories=False`` this function is byte-identical to its pre-O8 form and
    ``_is_single_word`` still gates the narrowing.

    Side effects (analytics recording) are deliberately excluded — the caller
    should invoke ``_record_search_analytics`` separately so that analytics
    fire unconditionally for every query-bearing search regardless of cache state.
    """
    vector_field = locale.fts_vector_field
    config = locale.fts_config

    # One-word queries: apply fuzzy category detection (locale-aware), unless the
    # buyer opted out for this request (O8).
    if _is_single_word(query) and not all_categories:
        category_filter = _fuzzy_category_match(query, locale)
        if category_filter:
            descendant_ids = category_filter.get_descendants(
                include_self=True
            ).values_list("id", flat=True)
            queryset = queryset.filter(category_id__in=descendant_ids)

    # FTS search on the locale's per-language vector
    search_query = SearchQuery(query, search_type="websearch", config=config)
    queryset = queryset.annotate(
        rank=SearchRank(F(vector_field), search_query)
    ).filter(**{vector_field: search_query})

    # Sort FTS results by the requested key, keeping relevance (-rank)
    # as a secondary tiebreaker (PO-2=A). Replaces the service's base
    # sort because order_by() overwrites previous ordering.
    if params.sort == AdSort.PRICE_LOW:
        queryset = queryset.order_by(
            F("price_normalized_eur").asc(nulls_last=True),
            "-rank", "-published_at", "-id",
        )
    elif params.sort == AdSort.PRICE_HIGH:
        queryset = queryset.order_by(
            F("price_normalized_eur").desc(nulls_last=True),
            "-rank", "-published_at", "-id",
        )
    elif params.sort == AdSort.DATE_OLD:
        queryset = queryset.order_by("published_at", "-rank", "-id")
    else:  # DATE_NEW — relevance-first default
        queryset = queryset.order_by("-rank", "-published_at", "-id")

    return queryset


def _resolve_search_count(
    cached_ids: list[int] | None,
    ads: QuerySet,
) -> tuple[int, bool]:
    """Resolve the display count and truncation flag for a query search.

    Two outcomes based on the cache outcome of ``cached_ids``:

    - ``cached_ids is not None``: the cached id list is bounded by SQL to
      ``SEARCH_CACHE_MAX_HITS`` (13-PERF-006 #1 validated 2026-09), so the
      count is simply its length and no second FTS evaluation is run.  When the
      length reaches the cap the result set is truncated (more rows may exist
      beyond what was cached).
    - ``cached_ids is None`` (cold-miss loser, lock held): ``ads`` is already
      the FTS-filtered queryset, so its count is reused directly.

    The truncated branch never reports a total it did not compute (13-PERF-006
    #2, Q9 ruling 2026-10-03).  It reports ``SEARCH_CACHE_MAX_HITS + 1`` — the
    display value ruled on 2026-10-03 — and the notice carries the ``+`` that
    disambiguates it from the exact cap value.

    Returns:
        A ``(total_count, results_truncated)`` tuple.
    """
    if cached_ids is not None:
        if len(cached_ids) >= SEARCH_CACHE_MAX_HITS:
            return SEARCH_CACHE_MAX_HITS + 1, True
        return len(cached_ids), False

    # Cold-miss loser fallback: ads is already the FTS-filtered queryset, so a
    # true count is available. A truncated set still reports the capped display
    # value, never an un-computed total (13-PERF-006 #2, Q9 2026-10-03).
    total_count = ads.count()
    if total_count >= SEARCH_CACHE_MAX_HITS:
        return SEARCH_CACHE_MAX_HITS + 1, True
    return total_count, False


def _rank_cache_hit_page(
    ads: QuerySet,
    cached_ids: list[int],
    params: ListingsQueryParams,
) -> QuerySet:
    """Return the cache-hit page queryset with page-scoped rank restore.

    ``cached_ids`` is the full ordered id list (up to ``SEARCH_CACHE_MAX_HITS``)
    and preserves the FTS rank order.  Only the requested page's window enters
    the ``Case``/``When`` rank statement, so statement size and bind count scale
    with ``per_page`` rather than with the cache cap (13-PERF-010 validated
    2026-09).  The window is resolved with ``Paginator``'s own arithmetic so an
    out-of-range page clamps to the last page exactly as it did before; the
    rendered order of the rows on the page is byte-identical.
    """
    paginator = Paginator(range(len(cached_ids)), params.per_page)
    page = paginator.get_page(params.page)
    window_ids = cached_ids[page.start_index() - 1 : page.end_index()]
    if not window_ids:
        return ads.none()
    return ads.filter(pk__in=window_ids).order_by(
        Case(
            *[When(pk=pk, then=pos) for pos, pk in enumerate(window_ids)],
            default=len(window_ids),
            output_field=IntegerField(),
        )
    )


def _is_single_word(text: str) -> bool:
    """
    Check if text is a single word.

    Args:
        text: The text to check

    Returns:
        True if text contains only one word
    """
    if not text:
        return False
    # Split on whitespace and check
    words = re.split(r"\s+", text.strip())
    return len(words) == 1


def _ids_for_exact_name(name: str, locale: LanguageLocale) -> list[int]:
    """Every active category id whose localised display name equals *name*.

    Ambiguity is expected: ``Category.name`` carries no uniqueness constraint
    and ``name_i18n`` is free-form, so two active categories can share a
    localised display name. Returning the first hit would scope the search to
    an arbitrary branch that may hold no matching ads at all (08-VAL-003).

    The lookup is computed from ``get_active_category_names(locale)``, so a
    warm cache performs zero category SELECTs.

    Args:
        name: The display name to match (case-insensitive).
        locale: The active search locale.

    Returns:
        The ids of every active category whose localised name matches.
    """
    target = name.casefold()
    return [
        int(entry["id"])
        for entry in get_active_category_names(locale)
        if str(entry["name"]).casefold() == target
    ]


def _resolve_unique_category(ids: list[int]) -> Category | None:
    """Resolve a matched-name id set, refusing an ambiguous match.

    A single id is unambiguous and resolves to its ``Category``. Zero or more
    than one id means no guess: the caller applies no category narrowing, so a
    search is never silently scoped to an arbitrary branch (08-VAL-003).

    Args:
        ids: The candidate category ids that matched a display name.

    Returns:
        The unique matching ``Category``, or ``None`` when the match is absent
        or ambiguous.
    """
    if len(ids) == 1:
        return Category.objects.get(id=ids[0])
    return None


def _fuzzy_category_match(query: str, locale: LanguageLocale) -> Category | None:
    """
    Find category matching the query using the locale-appropriate name.

    A slug exact match is tried first (slug is unique, so the match is
    unambiguous regardless of the display-name ambiguity rule). Name resolution
    then delegates to :func:`_fuzzy_match_by_name`, which runs the shared
    category fuzzy ladder (the exact-name and fuzzy tiers).

    Args:
        query: The single-word search query
        locale: The active search locale

    Returns:
        Matching Category or None
    """
    # Try slug match first (slug is unique so first() is safe and a slug match
    # stays unambiguous regardless of the display-name ambiguity rule).
    by_slug = Category.objects.filter(slug__iexact=query, is_active=True).first()
    if by_slug:
        return by_slug
    return _fuzzy_match_by_name(query, locale)


def _fuzzy_match_by_name(query: str, locale: LanguageLocale) -> Category | None:
    """Resolve a query against the shared category fuzzy ladder.

    The exact-name and fuzzy tiers now come from
    :func:`apps.categories.services.fuzzy.match_category` over the cached
    active-category name list (versioned + locale-aware), so a warm cache runs
    the match with zero category SELECTs. The ladder cutoff is the ruled 0.8
    (:data:`~apps.categories.services.fuzzy.CATEGORY_FUZZY_CUTOFF`).

    An ambiguous display name (two or more matching ids) returns no guess so
    the search is not scoped to an arbitrary branch (08-VAL-003).

    Args:
        query: The single-word search query
        locale: The active search locale

    Returns:
        Matching Category or None
    """
    entries = get_active_category_names(locale)
    all_names = [str(entry["name"]) for entry in entries]
    match = match_category(query, all_names)
    if match:
        return _resolve_unique_category(_ids_for_exact_name(match, locale))
    return None
