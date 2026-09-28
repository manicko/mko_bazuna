"""
Tests for Django settings import-time secret validation.

Asserts that:
- Absent DJANGO_SECRET_KEY raises ImproperlyConfigured at settings import time.
- BOT_TOKEN empty with DEBUG=False (production) raises ImproperlyConfigured.
- BOT_TOKEN empty with DEBUG=True (development) is permitted.
- GOOGLE_TRANSLATE_API_KEY empty with DEBUG=False (production) raises
  ImproperlyConfigured (the guard that fires when .env.prod omits the key,
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

from config.settings.tests.test_prod_logging import TEST_SECRET_KEY, _prod_env_overrides

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


def _dev_env_overrides(**overrides: str) -> dict[str, str]:
    """Build an environment dict suitable for importing dev settings.

    Starts from os.environ and applies development env vars
    (DJANGO_SETTINGS_MODULE, DEBUG, DJANGO_SECRET_KEY) so the dev.py
    fail-fast guards pass. Callers can override any value (e.g. BOT_TOKEN).
    """
    env = {k: v for k, v in os.environ.items()}
    env["DJANGO_SETTINGS_MODULE"] = "config.settings.dev"
    env["DEBUG"] = "True"
    env["DJANGO_SECRET_KEY"] = overrides.pop("DJANGO_SECRET_KEY", TEST_SECRET_KEY)
    env["PYTHONPATH"] = os.pathsep.join(sys.path)
    env.update(overrides)
    return env


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


def test_django_secret_key_rejects_empty() -> None:
    """Importing prod settings with DJANGO_SECRET_KEY='' (present-but-empty) raises
    ImproperlyConfigured.

    django-environ's env() returns "" for an empty-but-present value (only raises
    when the var is unset). The prod.py SECRET_KEY guard must reject this at import
    time so a misconfigured .env.prod fails fast instead of booting with an empty
    signing key.
    """
    env = _prod_env_overrides(DJANGO_SECRET_KEY="")
    stderr = _run_in_subprocess(
        env,
        "import django; django.setup()",
    )
    assert "ImproperlyConfigured" in stderr
    assert "SECRET_KEY" in stderr


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
    """BOT_TOKEN empty with DEBUG=False (production) raises ImproperlyConfigured.

    BOT_TOKEN is set present-but-empty (rather than deleted) because the local
    Docker test gate bind-mounts .env.test (which sets BOT_TOKEN) and base.py's
    read_env() restores it when config.settings.prod is imported. Present-but-empty
    prevents read_env from restoring the value, pinning the guard to BOT_TOKEN.
    """
    env = {k: v for k, v in os.environ.items() if k != "BOT_TOKEN"}
    env["BOT_TOKEN"] = ""
    env["GOOGLE_TRANSLATE_API_KEY"] = "test-translate-key-for-testing-only"
    env["DJANGO_SECRET_KEY"] = TEST_SECRET_KEY
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
    assert "BOT_TOKEN" in result.stderr
    assert "GOOGLE_TRANSLATE_API_KEY" not in result.stderr


def test_google_translate_api_key_required_in_production() -> None:
    """GOOGLE_TRANSLATE_API_KEY empty with DEBUG=False (production) raises
    ImproperlyConfigured.

    This guard fires when .env.prod omits the key. The failure cascades:
    settings load fails → django.setup() is never called → get_commands()
    returns only core Django commands (settings.configured is False) → the
    bootstrap_reference_data management command is undiscoverable → the
    migrate container exits with KeyError masking the real ImproperlyConfigured.
    """
    env = {k: v for k, v in os.environ.items() if k != "GOOGLE_TRANSLATE_API_KEY"}
    env["DJANGO_SECRET_KEY"] = TEST_SECRET_KEY
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


def test_redis_url_required_in_production() -> None:
    """REDIS_URL empty with DEBUG=False (production) raises ImproperlyConfigured.

    base.py's env("REDIS_URL", default="") returns "" when the var is
    absent or present-but-empty, so a prod deployment missing REDIS_URL
    would silently fall back to MemoryStorage for the bot FSM and an empty
    cache location. This guard must fail fast at settings import time.
    """
    env = {k: v for k, v in os.environ.items() if k != "REDIS_URL"}
    env["DJANGO_SECRET_KEY"] = TEST_SECRET_KEY
    env["BOT_TOKEN"] = "test-bot-token-for-testing-only"
    env["SITE_URL"] = "https://example.com"
    env["GOOGLE_TRANSLATE_API_KEY"] = "test-translate-key-for-testing-only"
    env["EMAIL_HOST"] = "smtp.example.com"
    env["ALLOWED_HOSTS"] = "example.com"
    env["CSRF_TRUSTED_ORIGINS"] = "https://example.com"
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
    assert "REDIS_URL" in result.stderr


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
        "DJANGO_SECRET_KEY='=t$test-key-with-$dollar$ign$chars'\n"
    )
    monkeypatch.delenv("DJANGO_SECRET_KEY", raising=False)
    environ.Env.read_env(env_file, overwrite=True)

    assert os.environ["DJANGO_SECRET_KEY"] == (
        "=t$test-key-with-$dollar$ign$chars"
    )


def test_prod_secret_key_rejects_short() -> None:
    """A SECRET_KEY shorter than 50 chars must be rejected at prod import time."""
    env = _prod_env_overrides(DJANGO_SECRET_KEY="short")
    stderr = _run_in_subprocess(env, "import django; django.setup()")
    assert "ImproperlyConfigured" in stderr
    assert "SECRET_KEY" in stderr
    assert "at least 50" in stderr


def test_prod_secret_key_rejects_placeholder() -> None:
    """A <...> placeholder SECRET_KEY must be rejected at prod import time."""
    env = _prod_env_overrides(
        DJANGO_SECRET_KEY="<generate-with-django-secret-key-generator>"
    )
    stderr = _run_in_subprocess(env, "import django; django.setup()")
    assert "ImproperlyConfigured" in stderr
    assert "placeholder" in stderr.lower()


def test_prod_secret_key_rejects_dev_only_dummy() -> None:
    """A SECRET_KEY containing 'dev-only-dummy' must be rejected at prod import time."""
    env = _prod_env_overrides(
        DJANGO_SECRET_KEY="dev-only-dummy-key-not-for-production"
    )
    stderr = _run_in_subprocess(env, "import django; django.setup()")
    assert "ImproperlyConfigured" in stderr
    assert "dummy" in stderr.lower()


def test_prod_secret_key_still_rejects_empty() -> None:
    """Existing empty-key guard still fires (regression — must not be shadowed by strength check)."""
    env = _prod_env_overrides(DJANGO_SECRET_KEY="")
    stderr = _run_in_subprocess(env, "import django; django.setup()")
    assert "ImproperlyConfigured" in stderr
    assert "SECRET_KEY" in stderr


def test_prod_secret_key_accepts_strong_key() -> None:
    """A valid 50+ char non-placeholder SECRET_KEY passes all prod guards."""
    env = _prod_env_overrides()  # uses TEST_SECRET_KEY (53 chars)
    stderr = _run_in_subprocess(env, "import django; django.setup()")
    assert "" == stderr.strip() or "ImproperlyConfigured" not in stderr


def test_bot_token_required_in_dev() -> None:
    """A truthy-but-placeholder BOT_TOKEN (<...>) no longer rejects dev import.

    The placeholder guard moved out of config.settings.dev into the bot
    entrypoint (telegram_bot.main.main()). Importing dev settings with a
    placeholder token must therefore succeed; the refusal to start now happens
    when main() runs (asserted in src/telegram_bot/tests/test_main.py).

    Note the placeholder does NOT ship in .env.dev.example (which ships
    BOT_TOKEN= empty); <your-bot-token-from-botfather> ships only in
    .env.example and .env.prod.example.
    """
    env = _dev_env_overrides(BOT_TOKEN="<your-bot-token-from-botfather>")
    result = subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "ImproperlyConfigured" not in result.stderr


def test_bot_token_placeholder_rejects_in_dev() -> None:
    """A generic <placeholder> BOT_TOKEN no longer rejects dev import.

    Same contract as test_bot_token_required_in_dev: the placeholder guard now
    lives in telegram_bot.main.main(), so importing config.settings.dev with a
    placeholder token succeeds. The refusal to start is asserted at the bot
    entrypoint (test_main.py).
    """
    env = _dev_env_overrides(BOT_TOKEN="<placeholder>")
    result = subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "ImproperlyConfigured" not in result.stderr


def test_bot_token_real_value_allowed_in_dev() -> None:
    """A real-looking BOT_TOKEN imports dev settings cleanly.

    With the placeholder guard relocated to the bot entrypoint, a real-format
    token imports without error. The former docstring claimed this value
    "passes the dev placeholder guard" — that guard no longer exists at
    settings import time, and this test now documents the import-time
    behaviour only.
    """
    env = _dev_env_overrides(BOT_TOKEN="123456789:ABCdefGHIjkl-MNO")
    result = subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "ImproperlyConfigured" not in result.stderr


def test_prod_bot_token_rejects_placeholder() -> None:
    """BOT_TOKEN placeholder (<...>) is rejected when importing prod settings."""
    env = _prod_env_overrides(BOT_TOKEN="<your-bot-token-from-botfather>")
    stderr = _run_in_subprocess(env, "import django; django.setup()")
    assert "ImproperlyConfigured" in stderr
    assert "BOT_TOKEN" in stderr


def test_prod_google_translate_api_key_rejects_placeholder() -> None:
    """GOOGLE_TRANSLATE_API_KEY placeholder (<...>) is rejected when importing
    prod settings.
    """
    env = _prod_env_overrides(
        GOOGLE_TRANSLATE_API_KEY="<your-google-cloud-translation-api-key>"
    )
    stderr = _run_in_subprocess(env, "import django; django.setup()")
    assert "ImproperlyConfigured" in stderr
    assert "GOOGLE_TRANSLATE_API_KEY" in stderr


def test_prod_bot_token_rejects_dev_only_dummy() -> None:
    """BOT_TOKEN with 'dev-only-dummy' sentinel is rejected in prod settings."""
    env = _prod_env_overrides(BOT_TOKEN="dev-only-dummy-key-not-for-production")
    stderr = _run_in_subprocess(env, "import django; django.setup()")
    assert "ImproperlyConfigured" in stderr
    assert "dummy" in stderr.lower()


def test_prod_bot_token_accepts_real_token() -> None:
    """A real-format BOT_TOKEN passes prod placeholder validation."""
    env = _prod_env_overrides(BOT_TOKEN="123456789:ABCdefGHIjkl-MNO")
    stderr = _run_in_subprocess(env, "import django; django.setup()")
    assert "ImproperlyConfigured" not in stderr


def test_django_oneshot_bypasses_all_secrets() -> None:
    """DJANGO_ONESHOT=1 skips all prod secret guards, including EMAIL_HOST.

    One-shot bootstrap services (migrate, load_cities, load_catalog,
    create_admin, seed) run against prod settings but carry dev-only placeholder
    secrets and no SMTP config. DJANGO_ONESHOT=1 must bypass every
    secret-validation guard so those containers boot without editing .env.dev.
    """
    env = _prod_env_overrides(
        DJANGO_SECRET_KEY="dev-only-dummy-key-not-for-production",
        BOT_TOKEN="dev-only-dummy-key-not-for-production",
        GOOGLE_TRANSLATE_API_KEY="dev-only-dummy-key-not-for-production",
        EMAIL_HOST="",
        SITE_URL="",
    )
    env["CSRF_TRUSTED_ORIGINS"] = ""
    env["DJANGO_ONESHOT"] = "1"
    result = subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "ImproperlyConfigured" not in result.stderr
    assert "ValueError" not in result.stderr
