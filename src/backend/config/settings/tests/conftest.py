"""Conftest for settings-import tests.

Manages the ``no_cover`` marker: tests marked with it spawn subprocesses that
import Django settings with instrumentation (coverage ``COVERAGE_PROCESS_START``).
Such subprocesses produce partial, misleading ``.coverage.*`` fragments that are
not mergeable into the main run. For ``no_cover`` tests, the coverage
subprocess-data channel is disabled by clearing ``COVERAGE_PROCESS_START`` so
only the parent process's own coverage (if any) is collected.

The ``no_cover`` marker is documentation + this hook: the marker names the
intention; the hook enforces it by mutating the environment before each selected
test runs its subprocess.
"""

from __future__ import annotations

import os

import pytest


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Disable subprocess coverage data collection for ``no_cover`` tests.

    Sets ``COVERAGE_PROCESS_START`` to ``""`` for the duration of the test and
    restores it afterwards. The marker is opt-in per module so non-subprocess
    tests (e.g. ``test_settings_defaults.py`` which the contract excludes) are
    unaffected.
    """
    if "no_cover" in item.keywords:
        item._coverage_env = os.environ.get("COVERAGE_PROCESS_START")  # type: ignore[attr-defined]
        os.environ["COVERAGE_PROCESS_START"] = ""


def pytest_runtest_teardown(item: pytest.Item) -> None:
    """Restore ``COVERAGE_PROCESS_START`` after a ``no_cover`` test."""
    saved = getattr(item, "_coverage_env", None)
    if saved is not None:
        os.environ["COVERAGE_PROCESS_START"] = saved
