"""Unit tests for ``PerformanceSLO`` enum integrity and spec-derived values.

The SLO constants in ``benchmark.constants`` are referenced by the Locust
load tests, the profiling regression command, and the CI search-SLO regression
test. These tests guard against:

- **Missing or renamed members** — if a member referenced by downstream
  code is deleted or renamed, these tests catch it at test time rather
  than letting it fail with ``AttributeError`` at runtime.
- **Value drift** — SLO thresholds are spec-derived; any change to a
  constant's value must be intentional and reflected in the spec docs.
"""

from __future__ import annotations

import pytest

from benchmark.constants import PerformanceSLO

pytestmark = [pytest.mark.unit]


class TestSLOConstants:
    """Assert every ``PerformanceSLO`` member has the spec-derived value."""

    def test_p95_slo_ms(self) -> None:
        """P95 latency SLO must be 500 ms."""
        assert PerformanceSLO.P95_SLO_MS == 500

    def test_p99_slo_ms(self) -> None:
        """P99 latency SLO must be 2000 ms."""
        assert PerformanceSLO.P99_SLO_MS == 2000

    def test_search_slo_ms(self) -> None:
        """Search SLO must be 2000 ms (matches search-patterns.md:360 ≤2s)."""
        assert PerformanceSLO.SEARCH_SLO_MS == 2000

    def test_cache_hit_rate_threshold(self) -> None:
        """Cache hit-rate threshold must be 85% (matches rules.md:221 >85%)."""
        assert PerformanceSLO.CACHE_HIT_RATE_THRESHOLD == 85

    def test_load_test_p95_regression_threshold(self) -> None:
        """Load-test regression threshold must be 10% (matches rules.md:228 >10%)."""
        assert PerformanceSLO.LOAD_TEST_P95_REGRESSION_THRESHOLD == 10


class TestSLOConstantsIsIntEnum:
    """Verify ``PerformanceSLO`` is an ``IntEnum`` with valid integer values."""

    def test_all_members_are_ints(self) -> None:
        """Every member value must be a plain ``int`` (IntEnum invariant)."""
        for member in PerformanceSLO:
            assert isinstance(member.value, int)
            assert type(member.value) is int

    def test_all_member_names_are_valid_identifiers(self) -> None:
        """Every member name must be a valid Python identifier for attribute access."""
        for member in PerformanceSLO:
            assert member.name.isidentifier(), (
                f"PerformanceSLO.{member.name} is not a valid Python identifier"
            )
