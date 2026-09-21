"""
Unit tests for ``apps.core.utils.migrate_locked._build_steps``.

Verifies the env-gating of the ``backfill_translations`` step:

- Default (no env var / non-"true" value) -> step absent, exactly 3 steps.
- ``RUN_TRANSLATION_BACKFILL=true`` -> step appended as the last entry, 4 steps.

``_build_steps`` is a pure function that only reads the process environment, so
these are fast unit tests with no database or subprocess involvement.
"""

from __future__ import annotations

import pytest

from apps.core.utils.migrate_locked import _build_steps

pytestmark = [pytest.mark.unit]

_DEFAULT_STEPS: tuple[tuple[str, ...], ...] = (
    ("migrate", "--noinput", "--run-syncdb"),
    ("setup_search_triggers", "--backfill"),
    ("load_exchange_rates",),
)


class TestBuildStepsDefault:
    """Default behavior (env var absent) - no backfill step."""

    def test_backfill_absent_without_env_var(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When ``RUN_TRANSLATION_BACKFILL`` is unset, backfill is absent."""
        monkeypatch.delenv("RUN_TRANSLATION_BACKFILL", raising=False)
        steps = _build_steps()
        assert ("backfill_translations",) not in steps

    def test_default_has_three_steps(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Without the env var, exactly three core steps are returned."""
        monkeypatch.delenv("RUN_TRANSLATION_BACKFILL", raising=False)
        steps = _build_steps()
        assert len(steps) == 3

    def test_default_steps_match_expected_order(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The default steps preserve the canonical order and content."""
        monkeypatch.delenv("RUN_TRANSLATION_BACKFILL", raising=False)
        steps = _build_steps()
        assert steps == _DEFAULT_STEPS

    def test_non_true_value_excludes_backfill(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Only the exact string ``'true'`` enables backfill; other values do not."""
        monkeypatch.setenv("RUN_TRANSLATION_BACKFILL", "false")
        steps = _build_steps()
        assert ("backfill_translations",) not in steps
        assert len(steps) == 3


class TestBuildStepsEnvGated:
    """Env-gated behavior - ``RUN_TRANSLATION_BACKFILL=true``."""

    def test_backfill_present_when_env_true(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When ``RUN_TRANSLATION_BACKFILL=true``, backfill is appended."""
        monkeypatch.setenv("RUN_TRANSLATION_BACKFILL", "true")
        steps = _build_steps()
        assert ("backfill_translations",) in steps

    def test_backfill_is_last_step(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The backfill step is appended as the last entry."""
        monkeypatch.setenv("RUN_TRANSLATION_BACKFILL", "true")
        steps = _build_steps()
        assert steps[-1] == ("backfill_translations",)

    def test_four_steps_when_env_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """With the env var set, exactly four steps are returned."""
        monkeypatch.setenv("RUN_TRANSLATION_BACKFILL", "true")
        steps = _build_steps()
        assert len(steps) == 4

    def test_core_steps_preserved_when_backfill_enabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When backfill is enabled, the first three steps are unchanged."""
        monkeypatch.setenv("RUN_TRANSLATION_BACKFILL", "true")
        steps = _build_steps()
        assert steps[:3] == _DEFAULT_STEPS

    def test_case_sensitive_true_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Only lowercase ``'true'`` matches; ``'True'`` or ``'TRUE'`` do not."""
        monkeypatch.setenv("RUN_TRANSLATION_BACKFILL", "True")
        steps = _build_steps()
        assert ("backfill_translations",) not in steps
