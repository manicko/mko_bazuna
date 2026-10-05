"""Positive control for the locust p95 gate (PERF-001 validated 2026-09).

The CI ``load-test`` job's p95 gate is the ``_assert_p95`` hook in
``benchmark.locustfile``.  That hook runs only under locust — it is not a
pytest artifact and no pytest run executes it in CI.  This module is the fast
feedback for the hook's arithmetic so a broken (or silently disabled) gate
fails in the regular test run.

**Why this test never imports locust in-process.**  Importing ``locust`` runs
``gevent.monkey.patch_all()`` inside ``locust/__init__.py``.  In a
pytest-xdist worker (the canonical ``make test`` configuration uses
``-n auto``) that patch deadlocks the worker with
``gevent.exceptions.LoopExit``.  Every locust-touching assertion therefore runs
in a **child process** (``subprocess``), where a fresh interpreter performs the
patch harmlessly.  The hook's branching is exercised against duck-typed fakes
in-process; the installed-locust API contract is asserted by the child probe.

Asserted behaviours (all three demonstrated failing before the fix):

1. A run carrying responses yields the aggregate p95 and passes when within
   ``P95_SLO_MS``.
2. An empty run fails **loudly** — the hook raises and sets a non-zero process
   exit code.  This is the arm a resurrected ``stats.get("Total", ...)`` cannot
   survive: that expression resolves through ``EntriesDict.__missing__``,
   fabricates an empty entry, and returns p95 = 0, so the gate would pass
   forever.
3. The hook reads ``RequestStats.total`` and contains no ``__missing__``-
   resolving access.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

# Locate the ``src`` directory (the parent of both ``backend/`` and
# ``benchmark/``) so the child process can import ``benchmark.locustfile`` even
# when PYTHONPATH is not preconfigured.
_THIS = Path(__file__).resolve()
_SRC_DIR = next(
    parent
    for parent in _THIS.parents
    if (parent / "benchmark").is_dir() and (parent / "backend").is_dir()
)
_HOOK_PATH = _SRC_DIR / "benchmark" / "locustfile.py"

# The child probe imports the hook and the real locust stats, exercises the
# hook's three arms, and reports a JSON summary.  It runs in a fresh
# interpreter so locust's gevent monkey-patch cannot touch the pytest worker.
_PROBE = r"""
import json
from locust.stats import RequestStats
from benchmark.locustfile import _assert_p95
from benchmark.locust_test_config import P95_SLO_MS as _HOOK_P95_SLO_MS
from benchmark.constants import PerformanceSLO


class _Runner:
    def __init__(self, stats):
        self.stats = stats


class _Env:
    def __init__(self, stats):
        self.runner = _Runner(stats)
        self.process_exit_code = 0


def _run(stats):
    env = _Env(stats)
    raised = None
    try:
        _assert_p95(env)
    except RuntimeError as exc:
        raised = str(exc)
    return {"raised": raised, "exit_code": env.process_exit_code}


result = {}

# The threshold the hook actually enforces, bound to the shared source of truth.
result["hook_p95_slo_ms"] = _HOOK_P95_SLO_MS
result["configured_p95_slo_ms"] = PerformanceSLO.P95_SLO_MS

populated = RequestStats()
populated.log_request("GET", "search", 50, 100)
populated.log_request("GET", "search", 300, 100)
populated.log_request("GET", "search", 900, 100)
result["populated_num_requests"] = populated.total.num_requests
result["populated_p95"] = populated.total.get_response_time_percentile(0.95)
result["populated_hook"] = _run(populated)

fast = RequestStats()
fast.log_request("GET", "search", 10, 100)
fast.log_request("GET", "search", 20, 100)
result["fast_p95"] = fast.total.get_response_time_percentile(0.95)
result["fast_hook"] = _run(fast)

empty = RequestStats()
result["empty_hook"] = _run(empty)

# The report's prescribed expression resolves a missing key through
# EntriesDict.__missing__, fabricating an empty StatsEntry whose p95 is 0.
result["fabricated_p95"] = empty.get(
    "Total", "NONE"
).get_response_time_percentile(0.95)

print(json.dumps(result))
"""


def _run_probe() -> dict:
    """Run the locust probe in a child process and return its JSON result."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_SRC_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def probe() -> dict:
    """The child-process probe result, computed once per module."""
    return _run_probe()


class TestP95GateArithmetic:
    """The hook's branching, against duck-typed fakes and the real locust probe."""

    def test_threshold_is_the_shared_slo_constant(self, probe: dict) -> None:
        """The hook enforces ``PerformanceSLO.P95_SLO_MS`` (the single source)."""
        assert probe["configured_p95_slo_ms"] == 500
        assert probe["hook_p95_slo_ms"] == probe["configured_p95_slo_ms"]

    def test_populated_run_extracts_nonzero_p95(self, probe: dict) -> None:
        """A run with responses yields a real, non-zero aggregate p95."""
        assert probe["populated_num_requests"] == 3
        assert probe["populated_p95"] > 0

    def test_hook_fails_when_p95_exceeds_slo(self, probe: dict) -> None:
        """900 ms p95 breaches the 500 ms SLO: the hook fails the run."""
        assert probe["populated_hook"]["raised"] is not None
        assert "exceeds SLO" in probe["populated_hook"]["raised"]
        assert probe["populated_hook"]["exit_code"] == 1

    def test_hook_passes_within_slo(self, probe: dict) -> None:
        """A fast populated run passes and leaves the exit code at 0."""
        assert probe["fast_p95"] <= 500
        assert probe["fast_hook"]["raised"] is None
        assert probe["fast_hook"]["exit_code"] == 0


class TestP95GateEmptyIsLoud:
    """An empty run must fail loudly, not report a green p95 of zero."""

    def test_empty_run_raises(self, probe: dict) -> None:
        """``num_requests == 0`` is a gate failure, not a fast run."""
        assert probe["empty_hook"]["raised"] is not None
        assert "no requests" in probe["empty_hook"]["raised"]

    def test_empty_run_sets_nonzero_exit_code(self, probe: dict) -> None:
        """The failure propagates as a non-zero process exit for CI."""
        assert probe["empty_hook"]["exit_code"] == 1


class TestP95GateReadsAggregate:
    """The hook must read ``RequestStats.total`` and never ``__missing__``."""

    def test_report_fix_would_be_permanently_green(self, probe: dict) -> None:
        """The report's expression fabricates p95 = 0, so it can never fail.

        This is the correction PERF-001 makes: ``stats.get("Total", "NONE")``
        returns an empty fabricated entry whose p95 is 0, and ``0 > 500`` is
        ``False``, so the gate would pass forever.
        """
        assert probe["fabricated_p95"] == 0

    def test_hook_reads_total_and_has_no_missing_access(self) -> None:
        """The hook's *code* reads ``.total`` and never ``stats.get(...)``.

        Inspects the hook's AST so the assertion cannot be satisfied — or
        broken — by prose in the docstring; only real attribute access and calls
        in the function body count.
        """
        import ast

        module = ast.parse(_HOOK_PATH.read_text(encoding="utf-8"))
        hook = next(
            node
            for node in ast.walk(module)
            if isinstance(node, ast.FunctionDef) and node.name == "_assert_p95"
        )
        # Collect the attribute paths the hook's code actually reads, e.g.
        # "stats.total", "total.num_requests", "total.get_response_time_percentile".
        attribute_paths = {
            f"{node.value.id}.{node.attr}"
            for node in ast.walk(hook)
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
        }
        # Collect method names the hook's code calls, e.g. "get".
        called_methods = {
            node.func.attr
            for node in ast.walk(hook)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert "stats.total" in attribute_paths, (
            "the hook must read the always-present RequestStats.total"
        )
        assert "total.num_requests" in attribute_paths, (
            "the hook must gate on a non-empty run"
        )
        assert "total.get_response_time_percentile" in attribute_paths, (
            "the hook must read the aggregate p95 from .total"
        )
        assert "get" not in called_methods, (
            "the hook must not call stats.get(...): a missing key resolves "
            "through EntriesDict.__missing__ and fabricates p95 = 0"
        )
