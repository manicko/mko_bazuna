"""Tests for CSRF_TRUSTED_ORIGINS configuration (OPS-010).

Settings are evaluated at import time, so these tests use subprocess isolation
with controlled os.environ (same pattern as test_settings_secrets.py and
test_prod_logging.py).
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.settings]

# Resolve repository root — same pattern as test_prod_logging.py and
# test_compose_hardening.py.
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


def _prod_env(**overrides: str) -> dict[str, str]:
    """Build an environment dict suitable for importing prod settings.

    Starts from os.environ (excluding CSRF_TRUSTED_ORIGINS) and sets all
    required production env vars so the prod.py fail-fast guards pass,
    except for CSRF_TRUSTED_ORIGINS which the caller controls.
    """
    env = {k: v for k, v in os.environ.items() if k != "CSRF_TRUSTED_ORIGINS"}
    env["DJANGO_SETTINGS_MODULE"] = "config.settings.prod"
    env["DJANGO_SECRET_KEY"] = overrides.pop(
        "DJANGO_SECRET_KEY", "test-secret-key-for-testing-only"
    )
    env["BOT_TOKEN"] = overrides.pop("BOT_TOKEN", "test-bot-token-for-testing-only")
    env["GOOGLE_TRANSLATE_API_KEY"] = overrides.pop(
        "GOOGLE_TRANSLATE_API_KEY", "test-translate-key-for-testing-only"
    )
    env["SITE_URL"] = overrides.pop("SITE_URL", "https://example.com")
    env["ALLOWED_HOSTS"] = overrides.pop("ALLOWED_HOSTS", "example.com")
    env.update(overrides)
    return env


def test_csrf_trusted_origins_required_in_production() -> None:
    """Prod settings without CSRF_TRUSTED_ORIGINS raises ValueError (skip in build)."""
    env = _prod_env()
    result = _run_in_subprocess(env, "import django; django.setup()")
    assert result.returncode != 0, result.stderr
    assert "ValueError" in result.stderr
    assert "CSRF_TRUSTED_ORIGINS" in result.stderr


def test_csrf_trusted_origins_accepted_in_production() -> None:
    """Prod settings with CSRF_TRUSTED_ORIGINS set succeeds."""
    env = _prod_env(CSRF_TRUSTED_ORIGINS="https://example.com")
    result = _run_in_subprocess(
        env,
        "from django.conf import settings; print(settings.CSRF_TRUSTED_ORIGINS)",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "['https://example.com']"


def test_csrf_trusted_origins_skipped_during_build() -> None:
    """Prod settings with DJANGO_BUILD=1 skips the CSRF_TRUSTED_ORIGINS guard."""
    env = _prod_env()
    env["DJANGO_BUILD"] = "1"
    result = _run_in_subprocess(
        env,
        "from django.conf import settings; print(settings.CSRF_TRUSTED_ORIGINS)",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"


def test_csrf_trusted_origins_defaults_empty_in_dev() -> None:
    """Dev settings default CSRF_TRUSTED_ORIGINS to []."""
    env = {k: v for k, v in os.environ.items() if k != "CSRF_TRUSTED_ORIGINS"}
    env["DJANGO_SECRET_KEY"] = "test-secret-key-for-testing-only"
    env["DJANGO_SETTINGS_MODULE"] = "config.settings.dev"
    result = _run_in_subprocess(
        env,
        "from django.conf import settings; print(settings.CSRF_TRUSTED_ORIGINS)",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"


def test_csrf_trusted_origins_in_prod_example() -> None:
    """.env.prod.example must contain CSRF_TRUSTED_ORIGINS."""
    env_path = _ROOT / ".env.prod.example"
    assert env_path.exists(), f"{env_path} not found"
    text = env_path.read_text(encoding="utf-8", errors="replace")
    assert "CSRF_TRUSTED_ORIGINS=" in text


def test_csrf_trusted_origins_in_example() -> None:
    """.env.example must contain CSRF_TRUSTED_ORIGINS."""
    env_path = _ROOT / ".env.example"
    assert env_path.exists(), f"{env_path} not found"
    text = env_path.read_text(encoding="utf-8", errors="replace")
    assert "CSRF_TRUSTED_ORIGINS=" in text
