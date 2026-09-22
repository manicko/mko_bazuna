"""
Tests for Django settings default values.

Verifies that REDIS_URL defaults to an empty string when the env var is absent
(finding 09-EXT-05). Settings are evaluated at import time, so these tests use
subprocess isolation with controlled os.environ.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from config.settings.tests import TEST_SECRET_KEY

pytestmark = [pytest.mark.unit, pytest.mark.settings]

_ROOT = Path(__file__).resolve().parent
while not (_ROOT / "pyproject.toml").exists():
    _ROOT = _ROOT.parent


def _run_in_subprocess(
    env: dict[str, str], import_code: str
) -> subprocess.CompletedProcess[str]:
    """Run Python code in a subprocess with the given environment."""
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
