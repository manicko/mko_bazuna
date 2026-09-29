"""
Tests for Django settings default values.

Verifies that REDIS_URL defaults to an empty string when the env var is absent
(finding 09-EXT-05). Settings are evaluated at import time, so these tests use
subprocess isolation with controlled os.environ.
"""

import os
from pathlib import Path

import pytest

from config.settings.tests import TEST_SECRET_KEY
from config.settings.tests.test_prod_logging import (
    _prod_env_overrides,
    _run_in_subprocess,
)

pytestmark = [pytest.mark.unit, pytest.mark.settings]

_ROOT = Path(__file__).resolve().parent
while not (_ROOT / "pyproject.toml").exists():
    _ROOT = _ROOT.parent


def test_redis_url_defaults_empty() -> None:
    """REDIS_URL defaults to "" when the env var is absent (finding 09-EXT-05).

    Uses config.settings.test (which skips .env file reading when
    DJANGO_SETTINGS_MODULE contains 'test') with REDIS_URL filtered out
    of the subprocess environment. The base.py default should be "".
    """
    env = {k: v for k, v in os.environ.items() if k != "REDIS_URL"}
    env["DJANGO_SECRET_KEY"] = TEST_SECRET_KEY
    env["DJANGO_SETTINGS_MODULE"] = "config.settings.test"
    result = _run_in_subprocess(
        env,
        "from django.conf import settings; print(repr(settings.REDIS_URL))",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "''"


_CONSOLE_BACKEND = "django.core.mail.backends.console.EmailBackend"
_SMTP_BACKEND = "django.core.mail.backends.smtp.EmailBackend"


def test_prod_email_backend_env_override_is_ignored() -> None:
    """prod.py pins EMAIL_BACKEND, so the env override cannot route mail to stdout.

    base.py reads EMAIL_BACKEND from the environment with an SMTP default and no
    allow-list, so setting it to the console backend under a fully valid prod
    environment used to make Django write the message body to stdout — the JSONL
    log stream. prod.py now re-pins the SMTP backend, exactly as it pins DEBUG.
    This asserts the **resolved setting**, not the absence of a warning.
    """
    env = _prod_env_overrides(EMAIL_BACKEND=_CONSOLE_BACKEND)
    result = _run_in_subprocess(
        env,
        "import django; django.setup(); "
        "from django.conf import settings; "
        "print(f'email_backend={settings.EMAIL_BACKEND}')",
    )
    assert result.returncode == 0, result.stderr
    assert f"email_backend={_SMTP_BACKEND}" in result.stdout
    assert _CONSOLE_BACKEND not in result.stdout
