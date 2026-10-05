"""
Page-scoped rank restore guard for BLOCK 6 (13-PERF-010 validated 2026-09).

The search view's cache-hit branch restores FTS rank order with a positional
``Case``/``When``. Before this change the arms were built over the **whole**
cached id list (up to ``SEARCH_CACHE_MAX_HITS`` = 1000) and only then handed to
``Paginator``, which slices — so statement size and bind count scaled with the
cache cap rather than with ``per_page``. The fix slices the cached id list to
the requested page window first (``_rank_cache_hit_page``), so the compiled
statement scales with ``per_page``.

Two invariants are pinned here:

1. **The rendered ad-id order on a page is byte-identical before and after the
   change.** The first request is a cache miss and renders through the direct
   FTS queryset; the second is a cache hit and renders through the page-scoped
   rank queryset. The id sequence per page must match, across multiple pages.
2. **The compiled cache-hit statement scales with ``per_page``, not with
   ``SEARCH_CACHE_MAX_HITS``.** Measured statically — no database, no latency.
"""

from __future__ import annotations

import pytest
from django.db.models import Case, IntegerField, QuerySet, When
from django.test import Client

from apps.ads.models import Ad
from apps.ads.services.listings_query import ListingsQuery, ListingsQueryParams
from apps.categories.models import Category
from apps.core.enums import AdStatus
from apps.locations.models import City
from apps.search.services.cache import SEARCH_CACHE_MAX_HITS
from apps.search.views.search import _rank_cache_hit_page
from apps.users.models import User
from conftest import create_test_ads_bulk

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

# Seed size: more than one page (PER_PAGE = 24) so page 2 is a real window and
# the page slice is genuinely narrower than the result set.
_SEED_AD_COUNT: int = 30


class TestCacheHitPageRankPreservesRenderedOrder:
    """The rendered page order is unchanged by the page-scoping."""

    def test_cold_and_warm_requests_render_identical_id_order_per_page(
        self,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """The cold (FTS) and warm (page-scoped rank) paths agree per page.

        Seeds more than one page of matching ads, issues a first request (cache
        miss, direct FTS ordering) and a second request (cache hit, page-scoped
        ``Case``/``When``), and asserts the rendered ad-id sequence is identical
        for page 1 and page 2. This is the tripwire: changing the ordering is a
        semantics change, not a performance change (13-PERF-010).
        """
        create_test_ads_bulk(
            seller,
            category,
            city,
            _SEED_AD_COUNT,
            title_prefix="Общий товар",
            status=AdStatus.PUBLISHED,
        )

        client = Client()

        for page in (1, 2):
            # Cache miss on the first page visit, then a warm cache hit; the
            # page-scoped rank only runs on the cache-hit branch.
            cold = client.get(f"/search/?q=товар&page={page}&lang=ru")
            warm = client.get(f"/search/?q=товар&page={page}&lang=ru")

            cold_ids = [ad.id for ad in cold.context["page_obj"]]
            warm_ids = [ad.id for ad in warm.context["page_obj"]]

            assert cold_ids, f"page {page} rendered no rows"
            assert warm_ids == cold_ids, (
                f"page {page}: page-scoped rank changed the rendered order — "
                f"cold={cold_ids} warm={warm_ids}"
            )

    def test_warm_cache_hit_renders_full_page_window(
        self,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """A warm cache hit renders a full ``per_page`` window, not a truncated one.

        Guards against the page slice dropping rows: page 1 must carry
        ``ListingsQuery.PER_PAGE`` ads and page 2 must carry the remainder.
        """
        create_test_ads_bulk(
            seller,
            category,
            city,
            _SEED_AD_COUNT,
            title_prefix="Общий товар",
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        client.get("/search/?q=товар&lang=ru")  # warm the cache

        page1 = client.get("/search/?q=товар&lang=ru")
        page2 = client.get("/search/?q=товар&page=2&lang=ru")

        assert len(list(page1.context["page_obj"])) == ListingsQuery.PER_PAGE
        assert len(list(page2.context["page_obj"])) == (
            _SEED_AD_COUNT - ListingsQuery.PER_PAGE
        )


class TestCacheHitRankStatementScalesWithPage:
    """The page-scoped rank statement scales with ``per_page`` (static, no DB)."""

    def test_statement_arms_scale_with_page_not_cache_cap(self) -> None:
        """Built over a 1000-id list, page 1 carries ~``per_page`` arms only.

        Uses a 1000-id ``cached_ids`` list (the cache cap) and compiles the
        page-scoped queryset, reading ``len(sql)``, bind count, and ``WHEN``
        count. Statement size and bind count must scale with ``per_page``, not
        with ``SEARCH_CACHE_MAX_HITS``. No database, no latency.
        """
        cached_ids = list(range(1, SEARCH_CACHE_MAX_HITS + 1))
        params = ListingsQueryParams(page=1, per_page=ListingsQuery.PER_PAGE)
        ads = ListingsQuery.build_queryset(params)

        page_qs = _rank_cache_hit_page(ads, cached_ids, params)
        sql, sql_params = page_qs.query.get_compiler(using="default").as_sql()

        when_count = sql.count("WHEN")

        # The page window is exactly per_page arms — never the 1000-ad cap.
        assert when_count == ListingsQuery.PER_PAGE, (
            f"rank statement built {when_count} WHEN arms; expected the page "
            f"window ({ListingsQuery.PER_PAGE}), not the cache cap "
            f"({SEARCH_CACHE_MAX_HITS})"
        )
        assert when_count < SEARCH_CACHE_MAX_HITS

        # Bind count is O(per_page), nowhere near the ~1000 of the pre-change
        # shape. A generous ceiling documents the scale without pinning an
        # exact query-builder-dependent number.
        assert len(sql_params) < SEARCH_CACHE_MAX_HITS // 10, (
            f"rank statement bound {len(sql_params)} params; expected O(per_page)"
        )
        assert len(sql) < 8_000, (
            f"rank statement is {len(sql)} chars; the pre-change shape was "
            f"~35 KB over the full cache cap"
        )

    def test_full_cache_cap_statement_is_not_built(self) -> None:
        """A direct 1000-arm ``Case``/``When`` is strictly larger than the page shape.

        Positive control for the measurement: the pre-change shape (arms over
        the whole ``cached_ids`` list) produces ~1000 ``WHEN`` arms, proving the
        page-scoped statement is the scaled-down shape and the assertion above
        is not vacuous.
        """
        cached_ids = list(range(1, SEARCH_CACHE_MAX_HITS + 1))
        params = ListingsQueryParams(page=1, per_page=ListingsQuery.PER_PAGE)
        ads: QuerySet[Ad] = ListingsQuery.build_queryset(params)

        full_qs = ads.filter(pk__in=cached_ids).order_by(
            Case(
                *[When(pk=pk, then=pos) for pos, pk in enumerate(cached_ids)],
                default=len(cached_ids),
                output_field=IntegerField(),
            )
        )
        full_sql, _ = full_qs.query.get_compiler(using="default").as_sql()
        assert full_sql.count("WHEN") == SEARCH_CACHE_MAX_HITS
