"""
Shared listings query service for Mko Bazuna.

Extracts the PUBLISHED-ad filter / sort / annotate pipeline that was
duplicated across ``apps.ads.views.listings`` and
``apps.search.views.search`` into a single service driven by a Pydantic
DTO of parsed request params.

The view layer remains responsible for request-scoped concerns:
- rate limiting
- did-you-mean suggestions (``suggest_city`` / ``_suggest_category``)
- ``CategoryLookupResolver`` for filter-option context
- save-search modal prefilters (``selected_city_id`` etc.)
- the FTS branch (``q`` param, per-language vector, ``SearchRank``)

This service owns the queryset-building pipeline only.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Annotated, Any, Final, NamedTuple

from django.db.models import Count, F, Q, QuerySet
from pydantic import Field, field_validator

from apps.ads.models import Ad, AdFeature
from apps.ads.services.favorites import annotate_favorites
from apps.ads.templatetags.price_tags import format_price_value
from apps.categories.models import Category
from apps.categories.services.lookup_resolution import CategoryLookupResolver
from apps.core.enums import AdSort, AdStatus
from apps.core.schemas import BaseInputModel
from apps.locations.models import City
from apps.lookups.enums import LookupGroupCode
from apps.lookups.models import LookupItem
from apps.users.services.account_state import account_state_q

logger = logging.getLogger(__name__)


# --- ?features= cardinality bound (08-SRCH-001) ----------------------------
#
# The bound is a CATALOGUE INVARIANT, not a magic number (Q2 RESOLVED
# 2026-10-03, option (b)): "the resolved feature set for any category",
# measured at seed volume, plus stated headroom. It is a secondary
# parameter-list guard — the real cost control is the single correlated
# subquery in ``build_queryset`` (BLOCK 1a), which makes the join count O(1)
# in N. This cap only stops an unauthenticated caller declaring an
# arbitrarily long parameter list at the DTO boundary.
#
# Measured maximum at seed volume: 13 resolved features (category ``goods``),
# over all 205 categories in ``apps/categories/catalog/categories.yaml``
# (``MAX_FEATURE_FILTER_SLUGS == MEASURED_MAX + MAX_FEATURE_FEATURES_HEADROOM``,
# i.e. 17 == 13 + 4).
#
# The guard test ``test_feature_catalogue_invariant.py`` re-measures every
# category's resolved feature set at seed volume and fails if any category ever
# resolves more than the invariant allows, so the ceiling cannot drift silently
# as the catalogue grows.
FEATURE_CATALOGUE_MAX_AT_SEED: Final[int] = 13
MAX_FEATURE_FEATURES_HEADROOM: Final[int] = 4
MAX_FEATURE_FILTER_SLUGS: Final[int] = (
    FEATURE_CATALOGUE_MAX_AT_SEED + MAX_FEATURE_FEATURES_HEADROOM
)


class ListingsQueryParams(BaseInputModel):
    """Validated filter + pagination parameters for PUBLISHED-ad listings.

    Replaces the inline ``request.GET`` parsing and silent
    ``except: pass`` coercion that was duplicated across the listings
    and search views.  Invalid scalar inputs (non-numeric prices, unknown
    sort values, non-integer page numbers) are coerced to safe defaults
    rather than rejecting the request with a 500.
    """

    category_slug: str | None = None
    city_slug: str | None = None
    min_price: int | None = None
    max_price: int | None = None
    purpose_slug: str | None = None
    condition_slug: str | None = None
    feature_slugs: Annotated[
        list[str],
        Field(max_length=MAX_FEATURE_FILTER_SLUGS),
    ] = Field(default_factory=list)
    sort: AdSort = AdSort.DATE_NEW
    user_id: int | None = None
    page: int = 1
    per_page: int = 24

    @field_validator("feature_slugs", mode="before")
    @classmethod
    def _clean_feature_slugs(cls, v: Any) -> list[str]:
        """Strip empty strings and dedupe ``feature_slugs`` (order-preserving).

        Runs before the ``max_length`` cardinality bound, so a bare ``?features=``
        (which ``request.GET.getlist`` yields as ``[""]``) and duplicated
        ``?features=a&features=a`` collapse first and cannot inflate the count
        or the AND-semantics threshold in ``build_queryset``. Cleaning only —
        never filtering to a catalogue whitelist, which would change the search
        cache key and the "unknown slug matches nothing" contract (08-SRCH-001).
        """
        if v is None:
            return []
        if isinstance(v, str):
            v = [v]
        seen: set[str] = set()
        cleaned: list[str] = []
        for item in v:
            slug = str(item).strip()
            if not slug or slug in seen:
                continue
            seen.add(slug)
            cleaned.append(slug)
        return cleaned

    @field_validator("min_price", "max_price", mode="before")
    @classmethod
    def _coerce_int_or_none(cls, v: Any) -> int | None:
        """Coerce a raw query-string value to ``int``, returning ``None`` on
        ``ValueError`` (replaces the old silent ``except: pass``).
        """
        if v is None or v == "":
            return None
        try:
            return int(v)
        except (ValueError, TypeError):
            return None

    @field_validator("sort", mode="before")
    @classmethod
    def _coerce_sort(cls, v: Any) -> AdSort:
        """Coerce a raw sort string to ``AdSort``.

        Unknown / empty values fall back to the default ``DATE_NEW``,
        mirroring the original ``else`` branch behaviour.
        """
        if v is None or v == "":
            return AdSort.DATE_NEW
        try:
            return AdSort(v)
        except ValueError:
            return AdSort.DATE_NEW

    @field_validator("page", mode="before")
    @classmethod
    def _coerce_page(cls, v: Any) -> int:
        """Coerce a raw page string to ``int``, defaulting to 1 on failure.

        Guarantees ``page >= 1`` so ``Paginator.get_page`` never receives a
        zero or negative index.
        """
        if v is None or v == "":
            return 1
        try:
            page = int(v)
            return max(page, 1)
        except (ValueError, TypeError):
            return 1


class ListingsQuery:
    """Builds the shared PUBLISHED-ad queryset used by listings and search.

    All filter, sort, and favorite-annotation logic lives here so that
    ``listings()`` and ``search()`` are thin adapters that only parse
    request params and assemble template context.
    """

    PER_PAGE = 24

    @classmethod
    def build_queryset(cls, params: ListingsQueryParams) -> QuerySet[Ad]:
        """Return the filtered, sorted, favorite-annotated queryset.

        Steps (order preserved from the original inline implementation):
        1. Base: ``PUBLISHED`` + account-state eligible + null-safe category
           active filter. The account-state term is the shared
           ``account_state_q("user__")`` declaration (06-PII-104), so a banned
           seller's ads are hidden here exactly as they are on the alert path —
           the *same* one predicate, not a second one (Q7 / 08-SRCH-008). A ban
           is a moderation sanction: removing the inventory is part of it, and
           this term must be read as ban enforcement, never as a consent fix.
        2. ``select_related`` / ``prefetch_related`` for efficient rendering.
        3. Category subtree filter (if ``category_slug`` resolves).
        4. City filter (if ``city_slug`` resolves).
        5. Price range filters.
        6. Purpose / condition single-select filters.
        7. Features multi-select (AND semantics, single correlated subquery over
           ``AdFeature`` — O(1) in N, 08-SRCH-001).
        8. Sort mapping.
        9. ``annotate_favorites``.
        """
        ads = (
            Ad.objects.filter(status=AdStatus.PUBLISHED)
            .filter(account_state_q("user__"))
            .filter(Q(category__isnull=True) | Q(category__is_active=True))
            .select_related("category", "city", "user")
            .prefetch_related("features", "user__trust_score", "images")
        )

        # Category subtree filter (get_descendants include self)
        if params.category_slug:
            try:
                category = Category.objects.get(
                    slug=params.category_slug, is_active=True
                )
                descendant_ids = category.get_descendants(
                    include_self=True
                ).values_list("id", flat=True)
                ads = ads.filter(category_id__in=descendant_ids)
            except Category.DoesNotExist:
                # Unknown / deactivated category — no filter applied.
                # The did-you-mean suggestion is a view-level concern.
                pass

        # City filter (exact slug match)
        if params.city_slug:
            try:
                city = City.objects.get(slug=params.city_slug)
                ads = ads.filter(city_id=city.id)
            except City.DoesNotExist:
                # Unknown city — no filter applied.
                # The did-you-mean suggestion is a view-level concern.
                pass

        # Price range filters (on EUR-normalized price, CR-10)
        if params.min_price is not None:
            ads = ads.filter(price_normalized_eur__gte=params.min_price)
        if params.max_price is not None:
            ads = ads.filter(price_normalized_eur__lte=params.max_price)

        # Listing purpose filter (F4) — single-select exact slug match
        if params.purpose_slug:
            ads = ads.filter(listing_purpose__slug=params.purpose_slug)

        # Listing condition filter — single-select exact slug match
        if params.condition_slug:
            ads = ads.filter(listing_condition__slug=params.condition_slug)

        # Features filter (F5) — multi-select AND semantics, O(1) in the number
        # of selected slugs (08-SRCH-001). The spec
        # (docs/01-spec/search-patterns.md) prescribes a single correlated
        # subquery over ``AdFeature`` with an ``IN`` clause, NOT a chaining
        # ``.filter(features__slug=...)`` per feature. The previous per-slug
        # chain emitted one JOIN per slug (2N+3 joins); N=60 cost 19.90 s and
        # OOM-killed the PostgreSQL backend.
        #
        # AND semantics are preserved by counting the distinct features an ad
        # carries from the selected set and requiring that count to equal the
        # number of distinct selected slugs. ``AdFeature.Meta.unique_together
        # = [("ad", "feature")]`` makes ``Count("feature_id")`` already
        # distinct. Unknown slugs match nothing for free: they are absent from
        # ``AdFeature``, so ``COUNT < N`` holds without any catalogue query.
        if params.feature_slugs:
            selected_slugs = set(params.feature_slugs)
            matched_ad_ids = (
                AdFeature.objects.filter(feature__slug__in=selected_slugs)
                .values("ad_id")
                .annotate(matched=Count("feature_id"))
                .filter(matched=len(selected_slugs))
                .values("ad_id")
            )
            ads = ads.filter(pk__in=matched_ad_ids)

        # Sort mapping (same semantics as the original inline if/elif)
        ads = cls._apply_sort(ads, params.sort)

        # Annotate favorite state for ad-card hearts (FT-001)
        ads = annotate_favorites(ads, params.user_id)

        return ads

    @staticmethod
    def _apply_sort(queryset: QuerySet[Ad], sort: AdSort) -> QuerySet[Ad]:
        """Apply the sort ordering to *queryset* and return the result."""
        if sort == AdSort.DATE_OLD:
            return queryset.order_by("published_at")
        if sort == AdSort.PRICE_LOW:
            return queryset.order_by(F("price_normalized_eur").asc(nulls_last=True))
        if sort == AdSort.PRICE_HIGH:
            return queryset.order_by(F("price_normalized_eur").desc(nulls_last=True))
        # DATE_NEW — default, newest first
        return queryset.order_by("-published_at")

    @staticmethod
    def active_price_range(
        params: ListingsQueryParams,
    ) -> tuple[Decimal | None, Decimal | None]:
        """Return ``(min, max)`` as ``Decimal`` for template rendering.

        ``params.min_price`` / ``max_price`` are already validated ``int``
        values (or ``None``); converting to ``Decimal`` matches the original
        behaviour and avoids try/except in the views.
        """
        lo = Decimal(params.min_price) if params.min_price is not None else None
        hi = Decimal(params.max_price) if params.max_price is not None else None
        return (lo, hi)

    @staticmethod
    def resolve_filter_options(
        breadcrumb_category: Category | None,
    ) -> tuple[
        list[LookupItem],
        list[LookupItem],
        list[LookupItem],
    ]:
        """Return ``(purposes, features, conditions)`` lookup options.

        When *breadcrumb_category* is set the options are constrained to the
        category's resolved feature set (via ``CategoryLookupResolver``);
        otherwise all active items are returned.  This logic was previously
        duplicated verbatim in ``listings()`` and ``search()``.
        """
        if breadcrumb_category:
            return (
                list(
                    CategoryLookupResolver.get_resolved_purposes(breadcrumb_category)
                ),
                list(
                    CategoryLookupResolver.get_resolved_features(breadcrumb_category)
                ),
                list(
                    CategoryLookupResolver.get_resolved_conditions(breadcrumb_category)
                ),
            )
        return (
            list(
                LookupItem.objects.filter(
                    group__code=LookupGroupCode.LISTING_PURPOSE, is_active=True
                ).order_by("sort_order")
            ),
            list(
                LookupItem.objects.filter(
                    group__code=LookupGroupCode.LISTING_FEATURE, is_active=True
                ).order_by("sort_order")
            ),
            list(
                LookupItem.objects.filter(
                    group__code=LookupGroupCode.LISTING_CONDITION, is_active=True
                ).order_by("sort_order")
            ),
        )


class ListingsContext(NamedTuple):
    """A built ``ListingsQueryParams`` plus the shared filter-context fragment.

    Returned by :func:`build_listings_context`. ``params`` drives the queryset
    each browse view builds; ``filter_context`` carries the template keys the
    listings and search views publish with *identical* values. Each view merges
    its own view-specific keys (pagination, did-you-mean suggestions, FTS state)
    on top.
    """

    params: ListingsQueryParams
    filter_context: dict[str, Any]


def build_listings_context(
    *,
    category_slug: str | None,
    city_slug: str | None,
    breadcrumb_category: Category | None,
    sort: str | None,
    min_price: str | None,
    max_price: str | None,
    purpose_slug: str | None,
    condition_slug: str | None,
    feature_slugs: list[str],
    page: str | None,
    user_id: int | None,
    per_page: int = ListingsQuery.PER_PAGE,
) -> ListingsContext:
    """Build the shared listings/search DTO and context from raw request values.

    Single entry point for the two browse views: it constructs the validated
    ``ListingsQueryParams``, resolves the category-constrained filter options
    and the active price range once, and assembles the template keys both views
    publish with identical values. The raw query-string values are passed in
    unchanged, so the DTO's field validators do the coercion; a rejected value
    raises ``ValidationError`` here and each view keeps its own 400 response.

    View-specific keys stay in the views: ``listings()`` and ``search()`` differ
    on ``query`` (``None`` vs the search term), ``page_obj`` (plain paginator vs
    the cache-hit re-rank), ``has_results`` and the did-you-mean suggestions, so
    those are deliberately not produced here.
    """
    params = ListingsQueryParams(
        category_slug=category_slug,
        city_slug=city_slug,
        min_price=min_price,
        max_price=max_price,
        purpose_slug=purpose_slug,
        condition_slug=condition_slug,
        feature_slugs=feature_slugs,
        sort=sort,
        user_id=user_id,
        page=page,
        per_page=per_page,
    )
    resolved_purposes, resolved_features, resolved_conditions = (
        ListingsQuery.resolve_filter_options(breadcrumb_category)
    )
    active_price_min, active_price_max = ListingsQuery.active_price_range(params)
    # The active-price chip renders the same localised, grouped numeric bounds the
    # cards do (14-I18N-010). ``active_price_range`` still returns Decimals - the
    # correct type at the query layer - and the display shape is built here, once,
    # through the single price formatter (BLOCK 3). No currency: the chip carries
    # numeric bounds only, so ``format_price_value`` is called in its currency-less
    # form. A ``None`` bound stays ``None`` (formatter returns "") and the template
    # keeps its current open-ended rendering.
    filter_context: dict[str, Any] = {
        "current_category": category_slug,
        "current_city": city_slug,
        "current_sort": params.sort,
        "min_price": min_price,
        "max_price": max_price,
        "active_price_min": (
            format_price_value(active_price_min, None)
            if active_price_min is not None
            else None
        ),
        "active_price_max": (
            format_price_value(active_price_max, None)
            if active_price_max is not None
            else None
        ),
        "current_listing_purpose": purpose_slug,
        "current_features": feature_slugs,
        "current_condition": condition_slug,
        "resolved_purposes": resolved_purposes,
        "resolved_features": resolved_features,
        "resolved_conditions": resolved_conditions,
        "show_filters": True,
    }
    return ListingsContext(params=params, filter_context=filter_context)
