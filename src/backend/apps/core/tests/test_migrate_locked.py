"""
Unit tests for ``apps.core.utils.migrate_locked._build_steps``.

Verifies the env-gating of the ``backfill_translations`` step:

- Default (no env var / non-"true" value) -> step absent, exactly 3 steps.
- ``RUN_TRANSLATION_BACKFILL=true`` -> step appended as the last entry, 4 steps.

``_build_steps`` is a pure function that only reads the process environment, so
these are fast unit tests with no database or subprocess involvement.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import subprocess
from contextlib import nullcontext
from unittest.mock import patch

import django
import pytest

import apps.core.utils.migrate_locked as migrate_locked
from apps.core.enums import AdvisoryLockId
from apps.core.utils import advisory_lock
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


class TestMainTimeout:
    """Verify migrate_locked.main() handles a subprocess TimeoutExpired."""

    def test_main_timeout_logs_error_and_returns_nonzero(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A timeout is logged as an ERROR and main() returns non-zero."""

        def raising_run(
            *args: object, **kwargs: object
        ) -> subprocess.CompletedProcess[bytes]:
            raise subprocess.TimeoutExpired(
                cmd=["python", "manage.py", "migrate"], timeout=1800
            )

        monkeypatch.setattr(django, "setup", lambda: None)
        monkeypatch.setattr(
            advisory_lock,
            "advisory_lock",
            lambda *args, **kwargs: nullcontext(),
        )
        monkeypatch.setattr(migrate_locked.subprocess, "run", raising_run)
        monkeypatch.delenv("RUN_TRANSLATION_BACKFILL", raising=False)

        with caplog.at_level(
            logging.ERROR, logger="apps.core.utils.migrate_locked"
        ):
            rc = migrate_locked.main()

        assert rc == 1
        assert any(
            "timed out" in record.message
            and record.levelno == logging.ERROR
            for record in caplog.records
        )


class TestDefaultSettings:
    """Verify migrate_locked.main() defaults to the prod settings module."""

    def test_main_defaults_to_prod_settings(self) -> None:
        """``os.environ.setdefault`` in ``main()`` targets ``config.settings.prod``."""
        source = inspect.getsource(migrate_locked.main)
        assert 'os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")' in source

    def test_main_does_not_default_to_dev_settings(self) -> None:
        """The default is ``config.settings.prod``, never ``config.settings.dev``."""
        source = inspect.getsource(migrate_locked.main)
        assert 'os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")' not in source

    def test_manage_defaults_to_prod_settings(self) -> None:
        """``manage.py``'s ``os.environ.setdefault`` targets ``config.settings.prod``."""
        source = inspect.getsource(importlib.import_module("manage").main)
        assert 'os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")' in source

    def test_manage_does_not_default_to_dev_settings(self) -> None:
        """``manage.py``'s default is ``config.settings.prod``, never ``config.settings.dev``."""
        source = inspect.getsource(importlib.import_module("manage").main)
        assert 'os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")' not in source


class TestSessionLockAcquisitionLog:
    """Session-scoped advisory_lock logs acquisition intent BEFORE acquiring.

    The session branch issues the blocking ``pg_advisory_lock``; a contending
    run blocks until the lock is granted. Without a pre-acquisition INFO line
    the operator sees a silent hang (ENT-006 residual), so the log line must
    fire before the acquisition statement executes.
    """

    def test_session_lock_logs_request_before_acquire(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The 'requesting' INFO line is emitted before pg_advisory_lock runs.

        The cursor's acquire call is patched to raise, so the lock is never
        granted. Asserting the request line is already in the log proves it is
        emitted on the acquisition side (before the blocking call), not after
        the lock is granted.
        """
        caplog.set_level(logging.INFO, logger="apps.core.utils.advisory_lock")

        def _acquire_raises(sql: str, params: object | None = None) -> None:
            if "pg_advisory_lock" in sql:
                raise RuntimeError("simulated block on pg_advisory_lock")

        with patch("apps.core.utils.advisory_lock.connection") as mock_conn:
            mock_conn.cursor.return_value.__enter__.return_value.execute.side_effect = (
                _acquire_raises
            )
            with pytest.raises(RuntimeError, match="simulated block"):
                with advisory_lock.advisory_lock(AdvisoryLockId.MIGRATE, session=True):
                    pass  # pragma: no cover - never reached because acquire raises

        messages = [r.message for r in caplog.records]
        assert any(
            "Requesting session advisory lock" in m for m in messages
        ), (
            "expected a pre-acquisition INFO line ('Requesting session advisory "
            "lock') before pg_advisory_lock executes; without it a blocked run "
            "is a silent hang"
        )

