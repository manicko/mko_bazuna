"""Locust load-test configuration for Mko Bazuna.

Pulls performance thresholds from the shared ``PerformanceSLO`` constants (B1)
so the locust p95 assertion and CI gate reference the same source of truth as
the SLO dashboard and profiling regression test.
"""

from benchmark.constants import PerformanceSLO

__all__ = [
    "P95_SLO_MS",
    "P99_SLO_MS",
    "SEARCH_SLO_MS",
    "CACHE_HIT_RATE_THRESHOLD",
    "LOAD_TEST_P95_REGRESSION_THRESHOLD",
    "USERS",
    "SPAWN_RATE",
    "RUN_TIME",
    "HOST",
    "STEP_LOAD",
]

# --- SLO thresholds (re-exported for convenience) ---
P95_SLO_MS: int = PerformanceSLO.P95_SLO_MS          # 500 ms
P99_SLO_MS: int = PerformanceSLO.P99_SLO_MS          # 2000 ms
SEARCH_SLO_MS: int = PerformanceSLO.SEARCH_SLO_MS    # 2000 ms — <=2 s search target
CACHE_HIT_RATE_THRESHOLD: int = PerformanceSLO.CACHE_HIT_RATE_THRESHOLD  # 85%
LOAD_TEST_P95_REGRESSION_THRESHOLD: int = (
    PerformanceSLO.LOAD_TEST_P95_REGRESSION_THRESHOLD
)  # 10%

# --- Load-test runtime configuration ---
USERS: int = 50
SPAWN_RATE: int = 10
RUN_TIME: str = "60s"
HOST: str = "http://localhost:8000"

# When True, locust ramps up users gradually (step load) rather than spawning
# all at once. Mirrors the Makefile `load` target defaults.
STEP_LOAD: bool = True
