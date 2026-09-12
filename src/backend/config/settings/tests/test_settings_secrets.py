"""
Tests for Django settings import-time secret validation.

Asserts that:
- Absent DJANGO_SECRET_KEY raises ImproperlyConfigured at settings import time.
- BOT_TOKEN empty with DEBUG=False (production) raises ImproperlyConfigured.
- BOT_TOKEN empty with DEBUG=True (development) is permitted.
- GOOGLE_TRANSLATE_API_KEY empty with DEBUG=False (production) raises
  ImproperlyConfigured (the guard that fires when .env.docker omits the key,
  causing the migrate container's bootstrap_reference_data command to be
  undiscoverable — see KeyError → ImproperlyConfigured cascade).

Settings are evaluated at import time and Django caches them on first access,
so override_settings/monkeypatch cannot test import-time failure. These tests
use subprocess isolation with controlled os.environ to verify the guards fire
at module import.
"""

import os
import subprocess
import sys
from pathlib import Path

import environ
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.settings]


def _run_in_subprocess(env: dict[str, str], import_code: str) -> str:
    """Run Python code in a subprocess with the given environment."""
    env_with_path = {
        **env,
        "PYTHONPATH": os.pathsep.join(sys.path),
    }
    result = subprocess.run(
        [sys.executable, "-c", import_code],
        env=env_with_path,
        capture_output=True,
        text=True,
    )
    return result.stderr


def test_django_secret_key_required() -> None:
    """Importing settings without DJANGO_SECRET_KEY raises ImproperlyConfigured."""
    env = {
        k: v
        for k, v in os.environ.items()
        if k != "DJANGO_SECRET_KEY" and k != "BOT_TOKEN"
    }
    env["DJANGO_SETTINGS_MODULE"] = "config.settings.test"
    stderr = _run_in_subprocess(
        env,
        "import django; django.setup()",
    )
    assert "ImproperlyConfigured" in stderr


def test_bot_token_allowed_empty_in_debug() -> None:
    """BOT_TOKEN may be empty when DEBUG=True (development mode)."""
    env = dict(os.environ)
    env["BOT_TOKEN"] = ""
    env["DJANGO_SETTINGS_MODULE"] = "config.settings.dev"
    env["PYTHONPATH"] = os.pathsep.join(sys.path)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from django.conf import settings; print(settings.BOT_TOKEN)",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_bot_token_required_in_production() -> None:
    """BOT_TOKEN empty with DEBUG=False (production) raises ImproperlyConfigured."""
    env = {k: v for k, v in os.environ.items() if k != "BOT_TOKEN"}
    env["DJANGO_SECRET_KEY"] = "test-secret-key-for-testing-only"
    env["DJANGO_SETTINGS_MODULE"] = "config.settings.prod"
    env["PYTHONPATH"] = os.pathsep.join(sys.path)
    result = subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, result.stderr
    assert "ImproperlyConfigured" in result.stderr


def test_google_translate_api_key_required_in_production() -> None:
    """GOOGLE_TRANSLATE_API_KEY empty with DEBUG=False (production) raises
    ImproperlyConfigured.

    This guard fires when .env.docker omits the key. The failure cascades:
    settings load fails → django.setup() is never called → get_commands()
    returns only core Django commands (settings.configured is False) → the
    bootstrap_reference_data management command is undiscoverable → the
    migrate container exits with KeyError masking the real ImproperlyConfigured.
    """
    env = {k: v for k, v in os.environ.items() if k != "GOOGLE_TRANSLATE_API_KEY"}
    env["DJANGO_SECRET_KEY"] = "test-secret-key-for-testing-only"
    env["BOT_TOKEN"] = "test-bot-token-for-testing-only"
    env["SITE_URL"] = "https://example.com"
    env["DJANGO_SETTINGS_MODULE"] = "config.settings.prod"
    env["PYTHONPATH"] = os.pathsep.join(sys.path)
    result = subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, result.stderr
    assert "ImproperlyConfigured" in result.stderr
    assert "GOOGLE_TRANSLATE_API_KEY" in result.stderr


def test_secret_key_with_dollar_sign_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Single-quoted secret key containing '$' must be preserved by django-environ.

    Regression test for the '$xp' Docker Compose interpolation issue:
    Django secret keys may contain '$' characters. In .env files loaded by
    Docker Compose, unquoted values have '$VAR' interpolated (so '$xp' would
    be silently stripped). Single-quoting the value prevents this.

    This test guards the Django-side behavior: that django-environ correctly
    strips single quotes and preserves the literal '$xp' substring when
    reading the bind-mounted .env file at container startup.
    """
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DJANGO_SECRET_KEY='=0y-)6rzn_dfoe+u$xp)u#*3yn&h!@9d+t=1va0r+#mg1hj+k+'\n"
    )
    monkeypatch.delenv("DJANGO_SECRET_KEY", raising=False)
    environ.Env.read_env(env_file, overwrite=True)

    assert os.environ["DJANGO_SECRET_KEY"] == (
        "=0y-)6rzn_dfoe+u$xp)u#*3yn&h!@9d+t=1va0r+#mg1hj+k+"
    )
