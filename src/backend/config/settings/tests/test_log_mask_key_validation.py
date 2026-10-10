"""Tests for the prod.py ``LOG_MASK_KEY`` guard and the shared validation helper (06-PII-112).

``LOG_MASK_KEY`` is an HMAC key, so unlike ``BOT_USERNAME`` its defect is
disclosure as well as correctness: a missing, placeholder or under-length value
reduces the Telegram-ID log mask to an enumerable digest and ships a false
security property. The guard therefore fails fast in production.

Environment discipline: ``_prod_env`` calls ``_prod_env_overrides()`` for its
**values**, then keeps only the keys in ``_PROD_ENV_ALLOWLIST`` and sets
``LOG_MASK_KEY`` from an explicit parameter. ``LOG_MASK_KEY`` is deliberately
absent from the allowlist, so no ambient value — from ``.env.test``, from
``os.environ``, or from a developer's shell — can reach the subprocess. That is
what makes this module green in both the Docker test container and the CI test
job by construction rather than by luck.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ImproperlyConfigured

from config.settings.secret_validation import validate_log_mask_key
from config.settings.tests.test_prod_logging import (
    _prod_env_overrides,
    _run_in_subprocess,
)

pytestmark = [pytest.mark.unit, pytest.mark.settings]

_PROD_MODULE = "config.settings.prod"
_DEFAULT_LOG_MASK_KEY = "test-log-mask-key-for-testing-only-not-a-secret"
_IMPORT_CODE = "import django; django.setup()"

# The only keys a subprocess is allowed to inherit. LOG_MASK_KEY is deliberately
# ABSENT: it is always set from an explicit parameter, so no value from .env.test,
# os.environ or a developer's shell can reach the assertion.
_PROD_ENV_ALLOWLIST = frozenset(
    {
        "DJANGO_SETTINGS_MODULE",
        "DEBUG",
        "DJANGO_SECRET_KEY",
        "BOT_TOKEN",
        "BOT_USERNAME",
        "GOOGLE_TRANSLATE_API_KEY",
        "SITE_URL",
        "ALLOWED_HOSTS",
        "CSRF_TRUSTED_ORIGINS",
        "REDIS_URL",
        "EMAIL_HOST",
        "EMAIL_PORT",
        "EMAIL_HOST_USER",
        "EMAIL_HOST_PASSWORD",
        "EMAIL_TIMEOUT",
        "EMAIL_BACKEND",
        "DEFAULT_FROM_EMAIL",
        "SUPPORT_NOTIFICATION_RECIPIENTS",
        "SENTRY_DSN",
        "DATABASE_URL",
        "PATH",
        "HOME",
    }
)


def _prod_env(*, log_mask_key: str = _DEFAULT_LOG_MASK_KEY) -> dict[str, str]:
    """A production environment with an explicit LOG_MASK_KEY and nothing ambient."""
    env = {
        key: value
        for key, value in _prod_env_overrides().items()
        if key in _PROD_ENV_ALLOWLIST
    }
    env["LOG_MASK_KEY"] = log_mask_key
    return env


# ---------------------------------------------------------------------------
# The helper itself
# ---------------------------------------------------------------------------


def test_validate_log_mask_key_accepts_a_wellformed_key() -> None:
    """A non-empty, non-placeholder, >= 32-byte value raises nothing."""
    validate_log_mask_key("LOG_MASK_KEY", _DEFAULT_LOG_MASK_KEY)


@pytest.mark.parametrize(
    "value",
    [
        "",  # missing/empty
        "<generate-a-random-32-byte-log-mask-key>",  # shipped template placeholder
        "short",  # below the 32-byte floor
    ],
)
def test_validate_log_mask_key_rejects_unusable_value(value: str) -> None:
    """Empty, placeholder and under-length values all raise ImproperlyConfigured."""
    with pytest.raises(ImproperlyConfigured) as excinfo:
        validate_log_mask_key("LOG_MASK_KEY", value)
    assert "LOG_MASK_KEY" in str(excinfo.value)
    # Value-free message contract: the value never appears in the output.
    if value:
        assert value not in str(excinfo.value)


# ---------------------------------------------------------------------------
# The prod guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "",
        "<generate-a-random-32-byte-log-mask-key>",
        "short",
    ],
)
def test_log_mask_key_rejects_unusable_value_in_production(value: str) -> None:
    """An empty, placeholder or under-length LOG_MASK_KEY fails the prod import."""
    env = _prod_env(log_mask_key=value)
    result = _run_in_subprocess(env, _IMPORT_CODE)
    assert result.returncode != 0, (
        "an unusable LOG_MASK_KEY did not break the prod import - this test's "
        "harness cannot observe a failure, so the guard assertion is worthless"
    )
    assert "ImproperlyConfigured" in result.stderr
    assert "LOG_MASK_KEY" in result.stderr


def test_log_mask_key_valid_value_accepted_in_production() -> None:
    """A well-formed LOG_MASK_KEY imports prod cleanly and reads back unchanged."""
    env = _prod_env()
    code = (
        "import django; django.setup(); "
        "from django.conf import settings; print(settings.LOG_MASK_KEY)"
    )
    result = _run_in_subprocess(env, code)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == _DEFAULT_LOG_MASK_KEY


# ---------------------------------------------------------------------------
# The two bypass directions the guard must keep working
# ---------------------------------------------------------------------------


def test_log_mask_key_guard_skipped_during_build() -> None:
    """DJANGO_BUILD=1 with a placeholder LOG_MASK_KEY imports with exit 0.

    An ungated guard would break the Docker builder stage, which runs
    ``collectstatic`` under config.settings.prod with ``DJANGO_BUILD=1`` and no
    ``.env`` at all.
    """
    env = _prod_env(log_mask_key="<generate-a-random-32-byte-log-mask-key>")
    env["DJANGO_BUILD"] = "1"
    result = _run_in_subprocess(env, _IMPORT_CODE)
    assert result.returncode == 0, result.stderr
    assert "ImproperlyConfigured" not in result.stderr
    assert "ValueError" not in result.stderr


def test_log_mask_key_guard_skipped_for_oneshot_bootstrap() -> None:
    """The placeholder passes under the bootstrap module, deliberately.

    The dev bootstrap one-shots load config.settings.oneshot, where
    ``_SKIP_SECRET_VALIDATION`` is True, so this guard is inert there.
    """
    env = _prod_env(log_mask_key="<generate-a-random-32-byte-log-mask-key>")
    env["DJANGO_SETTINGS_MODULE"] = "config.settings.oneshot"
    env["DJANGO_ONESHOT"] = "1"
    result = _run_in_subprocess(env, _IMPORT_CODE)
    assert result.returncode == 0, result.stderr
    assert "ImproperlyConfigured" not in result.stderr
    assert "ValueError" not in result.stderr
