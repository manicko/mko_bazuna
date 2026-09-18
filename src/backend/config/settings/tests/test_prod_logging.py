"""Subprocess-based tests for prod.py logging and Sentry initialization.

Settings are evaluated at import time and Django caches them on first access,
so override_settings/monkeypatch cannot test import-time configuration.
These tests use subprocess isolation with controlled os.environ.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.settings]

# Resolve repository root — same pattern as test_compose_hardening.py.
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


def _prod_env_overrides(**overrides: str) -> dict[str, str]:
    """Build an environment dict suitable for importing prod settings.

    Starts from os.environ and applies required production env vars
    (DJANGO_SECRET_KEY, BOT_TOKEN, GOOGLE_TRANSLATE_API_KEY, SITE_URL,
    ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS) so the prod.py fail-fast guards
    pass. Callers can override any value.
    """
    env = {k: v for k, v in os.environ.items()}
    env["DJANGO_SETTINGS_MODULE"] = "config.settings.prod"
    env["DEBUG"] = "False"
    env["DJANGO_SECRET_KEY"] = overrides.pop("DJANGO_SECRET_KEY", "test-secret-key-for-testing-only")
    env["BOT_TOKEN"] = overrides.pop("BOT_TOKEN", "test-bot-token-for-testing-only")
    env["GOOGLE_TRANSLATE_API_KEY"] = overrides.pop(
        "GOOGLE_TRANSLATE_API_KEY", "test-translate-key-for-testing-only"
    )
    env["SITE_URL"] = overrides.pop("SITE_URL", "https://example.com")
    env["ALLOWED_HOSTS"] = overrides.pop("ALLOWED_HOSTS", "example.com")
    env["CSRF_TRUSTED_ORIGINS"] = overrides.pop(
        "CSRF_TRUSTED_ORIGINS", "https://example.com"
    )
    env["SENTRY_DSN"] = overrides.pop("SENTRY_DSN", "")
    env.update(overrides)
    return env


def test_sentry_initialized_when_dsn_configured() -> None:
    """prod settings with SENTRY_DSN set and DEBUG=False initializes sentry_sdk."""
    env = _prod_env_overrides(SENTRY_DSN="https://test@example.com/42")
    env["PYTHONPATH"] = os.pathsep.join(sys.path)
    import_code = (
        "import django; django.setup(); "
        "import sentry_sdk; "
        "client = sentry_sdk.get_client(); "
        "print('SENTRY_INITIALIZED' if client.dsn is not None else 'NO_CLIENT')"
    )
    result = _run_in_subprocess(env, import_code)
    assert result.returncode == 0, result.stderr
    assert "SENTRY_INITIALIZED" in result.stdout


def test_sentry_not_initialized_without_dsn() -> None:
    """prod settings without SENTRY_DSN does not initialize sentry_sdk and does not crash."""
    env = _prod_env_overrides(SENTRY_DSN="")
    env["PYTHONPATH"] = os.pathsep.join(sys.path)
    import_code = (
        "import django; django.setup(); "
        "import sentry_sdk; "
        "client = sentry_sdk.get_client(); "
        "print('NO_CLIENT' if client.dsn is None else 'HAS_CLIENT')"
    )
    result = _run_in_subprocess(env, import_code)
    assert result.returncode == 0, result.stderr
    assert "NO_CLIENT" in result.stdout


def test_prod_logging_uses_json_formatter() -> None:
    """prod settings LOGGING dict configures RedactingJsonFormatter."""
    env = _prod_env_overrides()
    env["PYTHONPATH"] = os.pathsep.join(sys.path)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import django; django.setup(); "
                "from django.conf import settings; "
                "fmt_class = settings.LOGGING['formatters']['json'].get('()', ''); "
                "handler_fmt = settings.LOGGING['handlers']['console'].get('formatter', ''); "
                "print(f'formatter_class={fmt_class}'); "
                "print(f'handler_formatter={handler_fmt}'); "
                "print(f'root_level={settings.LOGGING[\"root\"][\"level\"]}')"
            ),
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "RedactingJsonFormatter" in result.stdout
    assert "handler_formatter=json" in result.stdout
    assert "root_level=WARNING" in result.stdout


def test_sentry_dsn_in_env_examples() -> None:
    """Both .env.prod.example and .env.example contain SENTRY_DSN."""
    prod_example = _ROOT / ".env.prod.example"
    example = _ROOT / ".env.example"

    assert prod_example.exists(), f"{prod_example} not found"
    assert example.exists(), f"{example} not found"

    prod_content = prod_example.read_text(encoding="utf-8", errors="replace")
    example_content = example.read_text(encoding="utf-8", errors="replace")

    assert "SENTRY_DSN=" in prod_content, ".env.prod.example missing SENTRY_DSN"
    assert "SENTRY_DSN=" in example_content, ".env.example missing SENTRY_DSN"


def test_sentry_sdk_in_pyproject_dependencies() -> None:
    """pyproject.toml includes sentry-sdk in project dependencies."""
    pyproject = _ROOT / "pyproject.toml"
    assert pyproject.exists(), f"{pyproject} not found"

    with pyproject.open("rb") as fh:
        data = tomllib.load(fh)

    deps = data["project"]["dependencies"]
    sentry_deps = [d for d in deps if d.startswith("sentry-sdk")]
    assert len(sentry_deps) == 1, f"Expected exactly one sentry-sdk dep, got {sentry_deps}"
    assert "sentry-sdk" in sentry_deps[0]
