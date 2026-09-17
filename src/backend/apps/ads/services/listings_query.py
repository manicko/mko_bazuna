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
from typing import Any

from django.db.models import F, Q, QuerySet
from pydantic import BaseModel, Field, field_validator

from apps.ads.models import Ad
from apps.ads.views.favorite import annotate_favorites
from apps.categories.models import Category
from apps.categories.services.lookup_resolution import CategoryLookupResolver
from apps.core.enums import AdSort, AdStatus
from apps.locations.models import City
from apps.lookups.enums import LookupGroupCode
from apps.lookups.models import LookupItem

logger = logging.getLogger(__name__)


class ListingsQueryParams(BaseModel):
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
    feature_slugs: list[str] = Field(default_factory=list)
    sort: AdSort = AdSort.DATE_NEW
    user_id: int | None = None
    page: int = 1
    per_page: int = 24

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
        1. Base: ``PUBLISHED`` + null-safe category active filter.
        2. ``select_related`` / ``prefetch_related`` for efficient rendering.
        3. Category subtree filter (if ``category_slug`` resolves).
        4. City filter (if ``city_slug`` resolves).
        5. Price range filters.
        6. Purpose / condition single-select filters.
        7. Features multi-select (AND semantics) + ``distinct()``.
        8. Sort mapping.
        9. ``annotate_favorites``.
        """
        ads = (
            Ad.objects.filter(status=AdStatus.PUBLISHED)
            .filter(Q(category__isnull=True) | Q(category__is_active=True))
            .select_related("category", "city", "user")
            .prefetch_related("features", "user__trust_score")
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

        # Features filter (F5) — multi-select AND semantics.
        # Each ``features__slug=<slug>`` call adds a JOIN constraint requiring
        # that specific feature; ``distinct()`` prevents duplicate rows.
        if params.feature_slugs:
            for slug in params.feature_slugs:
                ads = ads.filter(features__slug=slug)
            ads = ads.distinct()

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
