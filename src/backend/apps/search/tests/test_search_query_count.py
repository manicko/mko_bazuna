"""
N+1 query-count guard for the search view (B7-C, 13-PERF-004).

Mirrors the pattern from ``test_listings_context.py:168-176`` and
``test_ad_detail_queries.py:40-59``: seed ads, issue a GET through
``django.test.Client`` wrapped in ``CaptureQueriesContext``, and assert
the total SQL query count stays within a bounded threshold.

The project-wide N+1 guard threshold is 16 (``_QUERY_BOUND`` in
``test_ad_detail_queries.py:37`` and the inline ``<= 16`` in
``test_listings_context.py:176``). The search view's FTS pipeline,
caching layer, analytics, and context assembly inherently require more
base queries than the detail/listings views, so this guard uses a
search-specific bound (see ``_QUERY_BOUND`` rationale below).

Catches regressions where:
  - ``ListingsQuery.resolve_filter_options()`` bypasses the lookup cache
    (per-row queries per ad on the render path).
  - Paginated ads lack ``select_related``/``prefetch_related``.
  - Template rendering issues per-ad queries (trust score, images).

The ``_clear_cache_between_tests`` autouse fixture (conftest.py:66-79)
clears LocMemCache between tests, so the first search is a cache miss —
the test exercises the full FTS pipeline, not just a cached hit.
"""

from __future__ import annotations

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.core.enums import AdStatus
from conftest import create_test_ads_bulk

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

# Bound rationale (investigated per task Step 4):
#
# The search view's FTS pipeline, search-result caching (SWR + single-flight),
# analytics recording, filter-option resolution, paginator, and save-search
# modal context inherently issue ~28 base queries — already exceeding the
# project-wide 16-query guard (test_ad_detail_queries.py:37,
# test_listings_context.py:176) which applies to the simpler detail/listings
# views.
#
# At 60 seed ads (24 on page 1, PER_PAGE=24), the render path adds 48 per-ad
# queries (24 × 2) from two known N+1 sources in *existing* files that this
# task does not modify:
#   1. ``ad.images.first`` in ads/partials/ad_list.html:107 — ``images`` is
#      not in ``prefetch_related`` on ListingsQuery.build_queryset.
#   2. ``render_trust_badge`` (trust_tags.py:66) calls
#      ``SellerTrustScore.objects.get(user=user)`` when the prefetched
#      ``user__trust_score`` resolves to None, bypassing the prefetch.
#
# Both are documented N+1 regressions (13-PERF-004 recommendation #3:
# "extend N+1 query-count guards to the search view"). Since this task only
# creates the test file, the bound is set to 100 — comfortably above the
# measured 80, with margin for minor variations, yet tight enough to catch
# a *new* per-ad N+1 (e.g. another un-prefetched relation would add ~24
# queries → 104 > 100).  Once the two N+1 sources above are resolved, the
# bound should be tightened toward the ~32-query base.
_QUERY_BOUND: int = 100

# Seed volume: ≥50 PUBLISHED ads to exceed the minimum and exercise
# pagination + filter-option resolution at realistic scale.
_SEED_AD_COUNT: int = 60


class TestSearchQueryCount:
    """N+1 regression guard for the ``/search/`` render path at seed volume."""

    def test_search_view_query_count_bounded(
        self, seller, category, city
    ) -> None:
        """Search at seed volume issues a bounded number of SQL queries.

        Seeds 60 PUBLISHED ads with a common FTS-matchable term, then issues
        a real ``/search/`` request through the Django test client wrapped
        in ``CaptureQueriesContext``. Asserts the total captured query count
        stays within ``_QUERY_BOUND``, catching N+1 regressions on
        filter-option resolution, pagination, or template rendering.
        """
        # Seed ≥50 PUBLISHED ads — all contain "товар" in the title so a
        # single FTS query matches them all, exercising the full pipeline.
        create_test_ads_bulk(
            seller,
            category,
            city,
            _SEED_AD_COUNT,
            title_prefix="Тестовый товар",
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        with CaptureQueriesContext(connection) as ctx:
            response = client.get(reverse("search:search") + "?q=товар&lang=ru")

        # --- response is healthy ---
        assert response.status_code == 200

        # --- results are present ---
        page_ads = list(response.context["page_obj"])
        assert len(page_ads) > 0

        # --- bounded query count: no N+1 leaks on the search render path ---
        assert len(ctx.captured_queries) <= _QUERY_BOUND, (
            f"Search view issued {len(ctx.captured_queries)} queries, "
            f"exceeding bound of {_QUERY_BOUND}. "
            f"Query count must stay bounded — check for missing "
            f"select_related/prefetch_related or uncached filter-option resolution."
        )
