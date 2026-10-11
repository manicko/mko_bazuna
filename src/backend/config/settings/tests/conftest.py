"""Conftest for settings-import tests.

Manages three concerns:

1. **``no_cover`` marker** — tests marked with it spawn subprocesses that import
   Django settings with instrumentation (coverage ``COVERAGE_PROCESS_START``).
   Such subprocesses produce partial, misleading ``.coverage.*`` fragments that are
   not mergeable into the main run. For ``no_cover`` tests, the coverage
   subprocess-data channel is disabled by clearing ``COVERAGE_PROCESS_START`` so
   only the parent process's own coverage (if any) is collected.

2. **Shared subprocess helper** (``_run_in_subprocess``) — runs Python code in a
   subprocess with the caller's env plus ``PYTHONPATH`` derived from ``sys.path``.
   Extracted from ``test_prod_logging.py`` to eliminate the three duplicated
   definitions across the settings test package.

3. **Shared prod-env builder** (``_prod_env_overrides``) — builds an environment
   dict with all production fail-fast guards satisfied, so importing
   ``config.settings.prod`` succeeds. Moved here from ``test_prod_logging.py``
   as the single source of truth.

The ``no_cover`` marker is documentation + ``pytest_runtest_setup``/``teardown``
hooks: the marker names the intention; the hooks enforce it by mutating the
environment before each selected test runs its subprocess.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from config.settings.tests import TEST_SECRET_KEY


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


def _run_in_subprocess(
    env: dict[str, str], import_code: str
) -> subprocess.CompletedProcess[str]:
    """Run Python code in a subprocess with the given environment.

    ``PYTHONPATH`` is set from ``sys.path`` so the subprocess can import the
    project's settings modules. The full ``CompletedProcess`` is returned so
    callers can inspect ``returncode``, ``stdout`` and ``stderr`` independently.
    """
    env_with_path = {
        **env,
        "PYTHONPATH": os.pathsep.join(sys.path),
    }
    return subprocess.run(
        [sys.executable, "-c", import_code],
        env=env_with_path,
        capture_output=True,
        text=True,
    )


def _prod_env_overrides(**overrides: str) -> dict[str, str]:
    """Build an environment dict suitable for importing prod settings.

    Starts from ``os.environ`` and applies all required production env vars
    so the ``prod.py`` fail-fast guards pass. Callers can override any value.
    """
    env = {k: v for k, v in os.environ.items()}
    env["DJANGO_SETTINGS_MODULE"] = "config.settings.prod"
    env["DEBUG"] = "False"
    env["DJANGO_SECRET_KEY"] = overrides.pop("DJANGO_SECRET_KEY", TEST_SECRET_KEY)
    env["BOT_TOKEN"] = overrides.pop("BOT_TOKEN", "test-bot-token-for-testing-only")
    # Must be explicit: without it the builder inherits whatever the ambient
    # environment supplies, which differs between the Docker test container
    # (.env.test) and the CI test job (no .env). See BLOCK 5 decision D1.
    env["BOT_USERNAME"] = overrides.pop("BOT_USERNAME", "test_bot_for_testing_only")
    # LOG_MASK_KEY is required by the prod.py fail-fast guard (06-PII-112).
    # Must be non-empty, non-placeholder and >= 32 bytes.
    env["LOG_MASK_KEY"] = overrides.pop(
        "LOG_MASK_KEY", "test-log-mask-key-for-testing-only-not-a-secret"
    )
    env["GOOGLE_TRANSLATE_API_KEY"] = overrides.pop(
        "GOOGLE_TRANSLATE_API_KEY", "test-translate-key-for-testing-only"
    )
    env["SITE_URL"] = overrides.pop("SITE_URL", "https://example.com")
    env["ALLOWED_HOSTS"] = overrides.pop("ALLOWED_HOSTS", "example.com")
    env["CSRF_TRUSTED_ORIGINS"] = overrides.pop(
        "CSRF_TRUSTED_ORIGINS", "https://example.com"
    )
    env["SENTRY_DSN"] = overrides.pop("SENTRY_DSN", "")
    # REDIS_URL must be non-empty to pass the prod.py fail-fast guard
    # (see prod.py: REDIS_URL required in production).
    env["REDIS_URL"] = overrides.pop("REDIS_URL", "redis://redis:6379/0")
    # EMAIL_* defaults — EMAIL_HOST is not a guard: since the Product Owner
    # ruling of 2026-10-03 a missing EMAIL_HOST only logs a warning
    # (see prod.py and 09-API-009). A non-empty default keeps the fixture quiet.
    env["EMAIL_HOST"] = overrides.pop("EMAIL_HOST", "smtp.example.com")
    env["EMAIL_PORT"] = overrides.pop("EMAIL_PORT", "587")
    env["EMAIL_HOST_USER"] = overrides.pop("EMAIL_HOST_USER", "")
    env["EMAIL_HOST_PASSWORD"] = overrides.pop("EMAIL_HOST_PASSWORD", "")
    env["EMAIL_TIMEOUT"] = overrides.pop("EMAIL_TIMEOUT", "10")
    env["EMAIL_BACKEND"] = overrides.pop(
        "EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend"
    )
    env["DEFAULT_FROM_EMAIL"] = overrides.pop(
        "DEFAULT_FROM_EMAIL", "noreply@example.com"
    )
    env["SUPPORT_NOTIFICATION_RECIPIENTS"] = overrides.pop(
        "SUPPORT_NOTIFICATION_RECIPIENTS", "support@example.com"
    )
    env.update(overrides)
    return env
