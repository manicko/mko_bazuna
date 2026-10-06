"""
Tests for Block B3 — SLO regression guard (finding 13-PERF-001).

Verifies the two remaining PERF-001 deliverables:
  - ``PerformanceSLO`` constant values match the spec and rules.md references.
  - The ``/search/`` endpoint completes within the ≤2s SLO at seed volume
    (≥50 PUBLISHED ads), as defined in ``docs/01-spec/search-patterns.md``
    ("Target response time: ≤2 seconds for search queries").

This is a **robust in-repo guard** — one untimed warm-up request followed by the
**median** of N=7 timed samples — **not a percentile instrument**.  It is a
smoke-level regression signal for the request path: the warm-up absorbs the
dominant cold-start cost (template/tag compilation, first FTS plan, test-client
warm-up) and the median absorbs residual single-sample host spikes, so the
guard stays stable on a loaded Docker host.  A percentile SLO can only be
established by a load run: the CI ``load-test`` job's p95 gate is the **sole
percentile instrument** for that.

The ``django-prometheus`` wiring (INSTALLED_APPS, MIDDLEWARE, ``/metrics``,
nginx restriction) is already covered by ``apps/core/tests/test_observability.py``;
this module completes B3 with the SLO constants assertion and the latency
regression test that every PR is gated on.
"""

from __future__ import annotations

import statistics
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
        """Search response SLO is ≤2000ms (the ≤2s search-patterns.md target)."""
        assert PerformanceSLO.SEARCH_SLO_MS == 2000

    def test_cache_hit_rate_threshold(self) -> None:
        """Cache hit-rate SLO is 85% (rules.md:221)."""
        assert PerformanceSLO.CACHE_HIT_RATE_THRESHOLD == 85

    def test_load_test_p95_regression_threshold(self) -> None:
        """Load-test p95 regression threshold is 10% (rules.md:228)."""
        assert PerformanceSLO.LOAD_TEST_P95_REGRESSION_THRESHOLD == 10

    def test_search_slo_matches_spec(self) -> None:
        """search-patterns.md "≤2 seconds" target → SEARCH_SLO_MS = 2000."""
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
    """Robust guard: search at seed volume must complete within the ≤2s SLO.

    Seeds ≥50 PUBLISHED ads (approximating the seed volume referenced in the
    spec), then issues one **untimed** warm-up ``/search/`` request followed by
    **N=7 timed samples** of the same request; the assertion is on the **median**
    elapsed time.  This is a robust in-repo guard, **not a percentile
    instrument** — the CI ``load-test`` p95 job is the sole percentile
    instrument.
    """

    _SEED_AD_COUNT: int = 60  # well above the ≥50 minimum
    _SAMPLE_COUNT: int = 7  # N ≥ 5; median absorbs single-sample host spikes

    def test_search_at_seed_volume_meets_slo(self, seller, category, city) -> None:
        """Search at seed volume (≥50 published ads) must complete within SLO.

        The spec (``docs/01-spec/search-patterns.md``, "Target response time:
        ≤2 seconds for search queries") sets the bound.  This test seeds a
        representative catalog of 60 PUBLISHED ads, discards one untimed warm-up
        request, then takes N=7 timed samples of a real search request through
        the Django test client and asserts the **median** stays within
        ``PerformanceSLO.SEARCH_SLO_MS``.  It is a robust in-repo guard
        (warm-up + median), not a percentile instrument; the CI ``load-test``
        job's p95 gate is the sole percentile instrument.
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
        query = "/search/?q=товар&lang=ru"

        # --- untimed warm-up: absorb cold-start cost (templates, FTS plan) ---
        warm_up_response = client.get(query)
        assert warm_up_response.status_code == 200, (
            f"Search warm-up returned HTTP {warm_up_response.status_code}, "
            f"expected 200"
        )

        # --- N timed samples of the same request path ---
        samples_ms: list[float] = []
        for _ in range(self._SAMPLE_COUNT):
            start = time.monotonic()
            response = client.get(query)
            elapsed_ms = (time.monotonic() - start) * 1000
            assert response.status_code == 200, (
                f"Search returned HTTP {response.status_code}, expected 200"
            )
            samples_ms.append(elapsed_ms)

        median_ms = statistics.median(samples_ms)

        # --- SLO is not breached (median guard, not a percentile) ---
        slo_ms = int(PerformanceSLO.SEARCH_SLO_MS)
        samples_display = ", ".join(f"{sample:.0f}" for sample in samples_ms)
        assert median_ms <= slo_ms, (
            f"Search at seed volume had median {median_ms:.0f}ms, exceeding SLO "
            f"of {slo_ms}ms (PerformanceSLO.SEARCH_SLO_MS). "
            f"Samples (ms): [{samples_display}]. "
            f"Seeded {self._SEED_AD_COUNT} PUBLISHED ads. "
            f"Threshold source: docs/01-spec/search-patterns.md "
            f'("Target response time: ≤2 seconds for search queries")'
        )
