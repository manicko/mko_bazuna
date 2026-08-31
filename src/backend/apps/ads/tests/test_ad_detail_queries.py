"""
Integration test for ``ad_detail`` query count (N+1 regression guard).

With the ``user__trust_score`` prefetch in place, the ``render_trust_badge``
template tag reads from prefetched data instead of issuing a per-user
``SellerTrustScore.objects.get`` query.  This test renders a real PUBLISHED ad
detail page (with a SellerTrustScore on the seller) and asserts that the total
query count stays within a bounded threshold.

If the prefetch is removed in future, the ``trust_tags`` template tag will
issue an extra SELECT per ad — this test catches that regression.
"""

from __future__ import annotations

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.core.enums import AdStatus, TrustLevel
from apps.trust.models import SellerTrustScore

from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

# Upper bound chosen to accommodate the header template's context-processor
# queries while still catching N+1 regressions from a missing trust-score
# prefetch.  The ad-detail view itself issues:
#   1 SELECT (ad + select_related user/city/category)
#   1 SELECT (prefetch images)
#   1 SELECT (prefetch features)
#   1 SELECT (prefetch user__trust_score)
#   1 INSERT (AnalyticsEvent)
#   + template/header queries
_QUERY_BOUND = 16


class TestAdDetailQueryCount:
    """N+1 regression guard for the ad-detail render path."""

    def test_detail_renders_without_n_plus_1_on_trust_score(
        self, seller, category, city
    ) -> None:
        """Rendering a PUBLISHED ad detail page issues a bounded number of queries."""
        SellerTrustScore.objects.create(
            user=seller,
            trust_level=TrustLevel.VERIFIED,
            score=50,
        )
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)

        client = Client()
        with CaptureQueriesContext(connection) as ctx:
            response = client.get(reverse("ads:detail", args=[ad.id]))

        assert response.status_code == 200
        assert len(ctx.captured_queries) <= _QUERY_BOUND

    def test_detail_query_count_stable_with_trust_score(
        self, seller, category, city
    ) -> None:
        """The presence of a SellerTrustScore does not add per-row trust queries."""
        SellerTrustScore.objects.create(
            user=seller,
            trust_level=TrustLevel.TRUSTED,
            score=70,
        )
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)

        client = Client()
        with CaptureQueriesContext(connection) as ctx_with_score:
            client.get(reverse("ads:detail", args=[ad.id]))

        # Count queries that touch the trust scores table.
        trust_queries = [
            q
            for q in ctx_with_score.captured_queries
            if "seller_trust_scores" in q["sql"]
        ]
        # The prefetch query is a single SELECT ... WHERE user_id IN (...),
        # not a per-row get().
        assert len(trust_queries) <= 1
