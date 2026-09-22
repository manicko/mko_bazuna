"""
Tests for Block B3 — SLO regression guard (finding 13-PERF-001).

Verifies the two remaining PERF-001 deliverables:
  - ``PerformanceSLO`` constant values match the spec and rules.md references.
  - The ``/search/`` endpoint completes within the ≤2s SLO at seed volume
    (≥50 PUBLISHED ads), as defined in ``docs/01-spec/search-patterns.md:360``.

The ``django-prometheus`` wiring (INSTALLED_APPS, MIDDLEWARE, ``/metrics``,
nginx restriction) is already covered by ``apps/core/tests/test_observability.py``;
this module completes B3 with the SLO constants assertion and the latency
regression test that every PR is gated on.
"""

from __future__ import annotations

import time

import pytest
from django.test import Client

from apps.core.enums import AdStatus
from benchmark.constants import PerformanceSLO
from conftest import create_test_ads_bulk

# ---------------------------------------------------------------------------
# SLO constant value assertions (unit, no database)
# ---------------------------------------------------------------------------


class TestSLOConstants:
    """Assert ``PerformanceSLO`` values match the spec and rules.md references.

    These are pure unit tests — no database, no Django ORM. They guard against
    accidental edits to the spec-derived SLO values in
    ``src/benchmark/constants.py`` (Block B1).
    """

    pytestmark = pytest.mark.unit

    def test_p95_slo_ms(self) -> None:
        """P95 latency SLO is 500ms (rules.md profiling threshold)."""
        assert PerformanceSLO.P95_SLO_MS == 500

    def test_p99_slo_ms(self) -> None:
        """P99 latency SLO is 2000ms (matches ≤2s search SLO)."""
        assert PerformanceSLO.P99_SLO_MS == 2000

    def test_search_slo_ms(self) -> None:
        """Search response SLO is ≤2000ms (search-patterns.md:360)."""
        assert PerformanceSLO.SEARCH_SLO_MS == 2000

    def test_cache_hit_rate_threshold(self) -> None:
        """Cache hit-rate SLO is 85% (rules.md:221)."""
        assert PerformanceSLO.CACHE_HIT_RATE_THRESHOLD == 85

    def test_load_test_p95_regression_threshold(self) -> None:
        """Load-test p95 regression threshold is 10% (rules.md:228)."""
        assert PerformanceSLO.LOAD_TEST_P95_REGRESSION_THRESHOLD == 10

    def test_search_slo_matches_spec(self) -> None:
        """search-patterns.md:360 defines ≤2 seconds → SEARCH_SLO_MS = 2000."""
        assert PerformanceSLO.SEARCH_SLO_MS == 2000

    def test_search_slo_is_p99_aligned(self) -> None:
        """The ≤2s search SLO is the p99 latency target."""
        assert PerformanceSLO.SEARCH_SLO_MS == PerformanceSLO.P99_SLO_MS

    def test_constants_are_int_enum(self) -> None:
        """PerformanceSLO is an IntEnum so values work as numeric thresholds."""
        assert isinstance(PerformanceSLO.SEARCH_SLO_MS, int)
        assert isinstance(PerformanceSLO.P95_SLO_MS, int)


# ---------------------------------------------------------------------------
# Search latency regression test (integration, database at seed volume)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.integration
class TestSearchResponseSLORegression:
    """Regression guard: search at seed volume must complete within the ≤2s SLO.

    Seeds ≥50 PUBLISHED ads (approximating the seed volume referenced in the
    spec) and times a real ``/search/`` request through the Django test client,
    asserting elapsed time stays within ``PerformanceSLO.SEARCH_SLO_MS``.
    """

    _SEED_AD_COUNT: int = 60  # well above the ≥50 minimum

    def test_search_latency_within_slo(self, seller, category, city) -> None:
        """Search at seed volume (≥50 published ads) must complete within SLO.

        The spec (``docs/01-spec/search-patterns.md:360``) defines the target
        response time as ≤2 seconds for search queries.  This test seeds a
        representative catalog of 60 PUBLISHED ads and times a real search
        request through the Django test client, asserting the elapsed time
        stays within ``PerformanceSLO.SEARCH_SLO_MS``.
        """
        # Seed ≥50 PUBLISHED ads to approximate seed volume.
        # All ads contain "товар" in the title so a single FTS query
        # matches them all — exercising the full result-set pipeline.
        create_test_ads_bulk(
            seller,
            category,
            city,
            self._SEED_AD_COUNT,
            title_prefix="Тестовый товар",
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        start = time.monotonic()
        response = client.get("/search/?q=товар&lang=ru")
        elapsed_ms = (time.monotonic() - start) * 1000

        # --- response is healthy ---
        assert response.status_code == 200, (
            f"Search returned HTTP {response.status_code}, expected 200"
        )

        # --- SLO is not breached ---
        slo_ms = int(PerformanceSLO.SEARCH_SLO_MS)
        assert elapsed_ms <= slo_ms, (
            f"Search at seed volume took {elapsed_ms:.0f}ms, exceeding SLO of "
            f"{slo_ms}ms (PerformanceSLO.SEARCH_SLO_MS). "
            f"Seeded {self._SEED_AD_COUNT} PUBLISHED ads. "
            f"Threshold source: docs/01-spec/search-patterns.md:360"
        )
