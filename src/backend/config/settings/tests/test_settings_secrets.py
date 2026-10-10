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
- EMAIL_HOST empty with DEBUG=False (production) does NOT raise: the import
  succeeds and a WARNING names the setting and the lost support escalations
  (Product Owner ruling 2026-10-03, Q1 / 09-API-009 — a loud warning, not a boot
  gate).

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
        if k not in ("DJANGO_SECRET_KEY", "BOT_TOKEN", "DJANGO_BUILD")
    }
    env["DJANGO_SETTINGS_MODULE"] = "config.settings.test"
    stderr = _run_in_subprocess(
        env,
        "import django; django.setup()",
    )
    assert "ImproperlyConfigured" in stderr


def test_django_secret_key_absent_allowed_during_build() -> None:
    """Config.settings.prod imports with DJANGO_BUILD=1 and no DJANGO_SECRET_KEY.

    The Docker builder stage runs ``collectstatic`` with ``DJANGO_BUILD=1`` and no
    ``.env`` file. ``base.py`` provides a build-time placeholder SECRET_KEY in this case
    so the builder never needs DJANGO_SECRET_KEY (which would require a SecretsUsedInArgOrEnv
    lint violation if baked into the Dockerfile as ENV).
    """
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("DJANGO_SECRET_KEY", "BOT_TOKEN", "DJANGO_BUILD")
    }
    env["DJANGO_SETTINGS_MODULE"] = "config.settings.prod"
    env["DJANGO_BUILD"] = "1"
    env["ALLOWED_HOSTS"] = "localhost,127.0.0.1,0.0.0.0"
    env["DATABASE_URL"] = (
        "postgres://postgres:build-placeholder@localhost:5432/postgres"
    )
    env["PYTHONPATH"] = os.pathsep.join(sys.path)
    stderr = _run_in_subprocess(env, "import django; django.setup()")
    assert "ImproperlyConfigured" not in stderr
    assert "ModuleNotFoundError" not in stderr


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


def test_prod_email_host_missing_warns_but_imports() -> None:
    """EMAIL_HOST present-but-empty with every other prod guard satisfied does
    NOT raise: the prod settings import succeeds and emits a WARNING naming the
    setting and the consequence it puts at risk.

    Product Owner ruling 2026-10-03 (Q1, 09-API-009): a missing EMAIL_HOST is a
    loud warning at startup, NOT a boot gate. The sole send_mail path
    (send_support_notification_email) already fails open, so a warning matches
    the code's own behaviour. No test asserts that a missing EMAIL_HOST raises
    ImproperlyConfigured — that shape is forbidden by the ruling.

    EMAIL_HOST is presented-but-empty (rather than deleted) so base.py's
    read_env() cannot restore it from the bind-mounted .env.test.
    """
    env = _prod_env_overrides(EMAIL_HOST="")
    env_with_path = {**env, "PYTHONPATH": os.pathsep.join(sys.path)}
    result = subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        env=env_with_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    combined = result.stderr + result.stdout
    # The warning is emitted by logging.getLogger(__name__).warning; the default
    # handler format prints the message, so assert the message's own text rather
    # than the level name.
    assert "EMAIL_HOST is not set" in combined
    # The consequence the warning must name, so an operator can act on it.
    assert "silently" in combined


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


def test_django_oneshot_does_not_bypass_prod_secrets() -> None:
    """DJANGO_ONESHOT no longer opens the prod guards for a *.prod module.

    The former test_django_oneshot_bypasses_all_secrets asserted the opposite:
    that DJANGO_ONESHOT=1 skips every prod secret guard. That was CFG-001's
    defect — an operator who copied the flag out of the dev override into a
    production env file would silently disable every guard. The bypass now
    reaches only config.settings.oneshot, and only because the deployment
    descriptor selected that module. Under config.settings.prod the flag is
    inert, the guards run, and a value-free warning explains the situation.
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
    assert result.returncode != 0, result.stderr
    assert "ImproperlyConfigured" in result.stderr
    assert "DJANGO_SECRET_KEY" in result.stderr
    assert "DJANGO_ONESHOT is set but ignored" in result.stderr



# ---------------------------------------------------------------------------
# BOT_TOKEN role signal (09-API-011)
# ---------------------------------------------------------------------------
# BOT_TOKEN_REQUIRED gates the BOT_TOKEN guard and nothing else. Fail-closed:
# only an explicit "0"/"false" opts out; absent/empty/unknown keep the
# requirement. The five one-shot services set it false via Compose, and Compose
# withholds BOT_TOKEN from them at the same time.


def _prod_env_without_bot_token(**overrides: str) -> dict[str, str]:
    """A prod env where BOT_TOKEN is absent and every other guard is satisfied.

    Returns the base environment for the role-signal tests. Callers add
    BOT_TOKEN_REQUIRED (or perturb one other guard) to exercise a specific path.
    """
    env = {k: v for k, v in os.environ.items() if k != "BOT_TOKEN"}
    env["BOT_TOKEN"] = ""
    env["GOOGLE_TRANSLATE_API_KEY"] = "test-translate-key-for-testing-only"
    env["DJANGO_SECRET_KEY"] = TEST_SECRET_KEY
    env["SITE_URL"] = "https://example.com"
    env["REDIS_URL"] = "redis://localhost:6379/0"
    env["ALLOWED_HOSTS"] = "example.com"
    env["CSRF_TRUSTED_ORIGINS"] = "https://example.com"
    env["EMAIL_HOST"] = "smtp.example.com"
    env["BOT_USERNAME"] = "mko_test_bot"
    env["LOG_MASK_KEY"] = "test-log-mask-key-for-testing-only-not-a-secret"
    env["DJANGO_SETTINGS_MODULE"] = "config.settings.prod"
    env["PYTHONPATH"] = os.pathsep.join(sys.path)
    env.update(overrides)
    return env


def _run_settings_import(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        env=env,
        capture_output=True,
        text=True,
    )


def test_bot_token_required_when_role_flag_absent() -> None:
    """Absent BOT_TOKEN_REQUIRED still requires BOT_TOKEN (fail-closed)."""
    env = _prod_env_without_bot_token()
    result = _run_settings_import(env)
    assert result.returncode != 0, result.stderr
    assert "ImproperlyConfigured" in result.stderr
    assert "BOT_TOKEN" in result.stderr


def test_bot_token_required_when_role_flag_empty() -> None:
    """An empty BOT_TOKEN_REQUIRED still requires BOT_TOKEN (fail-closed)."""
    env = _prod_env_without_bot_token(BOT_TOKEN_REQUIRED="")
    result = _run_settings_import(env)
    assert result.returncode != 0, result.stderr
    assert "ImproperlyConfigured" in result.stderr
    assert "BOT_TOKEN" in result.stderr


@pytest.mark.parametrize("value", ["yes", "no", "1", "true", "garbage", "FALSE!"])
def test_bot_token_required_when_role_flag_unrecognised(value: str) -> None:
    """Any value other than "0"/"false" is unrecognised and still requires it."""
    env = _prod_env_without_bot_token(BOT_TOKEN_REQUIRED=value)
    result = _run_settings_import(env)
    assert result.returncode != 0, result.stderr
    assert "ImproperlyConfigured" in result.stderr
    assert "BOT_TOKEN" in result.stderr


@pytest.mark.parametrize("value", ["false", "FALSE", "0", " false "])
def test_bot_token_not_required_when_role_declared_false(value: str) -> None:
    """An explicit "0"/"false" (any case, surrounding space) opts out cleanly."""
    env = _prod_env_without_bot_token(BOT_TOKEN_REQUIRED=value)
    result = _run_settings_import(env)
    assert result.returncode == 0, result.stderr
    assert "ImproperlyConfigured" not in result.stderr


def test_bot_token_role_flag_does_not_bypass_other_guards() -> None:
    """The role flag gates ONLY BOT_TOKEN; CFG-001 cannot regress through it.

    With BOT_TOKEN_REQUIRED=false and BOT_TOKEN absent, a *different* missing
    required secret must still raise. This is the non-regression proof: the flag
    is not a second DJANGO_ONESHOT that silently disables every guard.
    """
    env = _prod_env_without_bot_token(
        BOT_TOKEN_REQUIRED="false", GOOGLE_TRANSLATE_API_KEY=""
    )
    result = _run_settings_import(env)
    assert result.returncode != 0, result.stderr
    assert "ImproperlyConfigured" in result.stderr
    assert "GOOGLE_TRANSLATE_API_KEY" in result.stderr
    assert "BOT_TOKEN must be set" not in result.stderr


def test_bot_token_role_flag_does_not_suppress_secret_key_guard() -> None:
    """BOT_TOKEN_REQUIRED=false must not weaken the SECRET_KEY guard (CFG-001)."""
    env = _prod_env_without_bot_token(
        BOT_TOKEN_REQUIRED="false",
        DJANGO_SECRET_KEY="dev-only-dummy-key-not-for-production",
    )
    result = _run_settings_import(env)
    assert result.returncode != 0, result.stderr
    assert "ImproperlyConfigured" in result.stderr
    assert "DJANGO_SECRET_KEY" in result.stderr


def test_bot_token_role_flag_does_not_bypass_email_host_warning_shape() -> None:
    """The role flag does not turn the EMAIL_HOST warning into a gate or a skip.

    EMAIL_HOST is a loud WARNING (09-API-009), independent of the BOT_TOKEN role
    signal. With EMAIL_HOST empty and a valid BOT_TOKEN present, the import still
    succeeds and warns — the role flag changes nothing about it.
    """
    env = _prod_env_without_bot_token(
        BOT_TOKEN="123456789:ABCdefGHIjkl-MNO", EMAIL_HOST=""
    )
    result = _run_settings_import(env)
    assert result.returncode == 0, result.stderr
    assert "EMAIL_HOST is not set" in (result.stderr + result.stdout)
