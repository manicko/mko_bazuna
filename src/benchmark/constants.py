"""
Service-level objective (SLO) constants for Mko Bazuna performance.

All fixed performance values are modeled as an ``IntEnum`` per project rule 10,
matching the codebase convention for numeric constants (``AdvisoryLockId`` in
``apps/core/enums.py``). Millisecond and percentage thresholds are integers,
so ``IntEnum`` is the type-safe choice.

This module is a standalone Python package on the ``src/`` Python path root —
it is NOT a Django app and has no migrations, ``apps.py``, or
``INSTALLED_APPS`` entry. It is importable as ``benchmark.constants`` by the
Locust load tests, profiling commands, and CI regression tests.
"""

from enum import IntEnum

__all__ = ["PerformanceSLO"]


class PerformanceSLO(IntEnum):
    """Service-level objectives for Mko Bazuna performance (spec-derived).

    Values are derived from:
    - ``docs/01-spec/search-patterns.md:360`` — search response ≤2 seconds
    - ``docs/99-agent/rules.md:221`` — cache hit rate >85%
    - ``docs/99-agent/rules.md:228`` — p95 regression >10% threshold
    """

    P95_SLO_MS = 500
    P99_SLO_MS = 2000
    SEARCH_SLO_MS = 2000
    CACHE_HIT_RATE_THRESHOLD = 85
    LOAD_TEST_P95_REGRESSION_THRESHOLD = 10
