"""Tests for the config.settings.oneshot bootstrap module (CFG-001).

The oneshot module star-imports prod and re-pins DEBUG=False. It exists so the
dev one-shot bootstrap services (migrate, load_cities, load_catalog,
create_admin, seed) can run with dev placeholder secrets without opening the
prod secret guards, and only because the deployment descriptor resolves
DJANGO_SETTINGS_MODULE=config.settings.oneshot — never because a .env file can
select it.

Settings are evaluated at import time and Django caches them on first access,
so override_settings/monkeypatch cannot test import-time configuration. These
tests use subprocess isolation (reusing the helper from test_prod_logging) with
controlled os.environ. No new subprocess helper or prod-env builder is defined
here — both are imported from config.settings.tests.test_prod_logging.
"""

from __future__ import annotations

import pytest

from config.settings.tests.test_prod_logging import (
    _prod_env_overrides,
    _run_in_subprocess,
)

pytestmark = [pytest.mark.unit, pytest.mark.settings]

_BOOTSTRAP_MODULE = "config.settings.oneshot"
_PROD_MODULE = "config.settings.prod"
_DEV_DUMMY_SECRET = "dev-only-dummy-key-not-for-production"
_JSON_FORMATTER = "apps.core.utils.json_logging.RedactingJsonFormatter"
_SMTP_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
_REDIS_CACHE = "django_redis.cache.RedisCache"


def _bootstrap_env(*, oneshot_flag: bool = True) -> dict[str, str]:
    """Build a subprocess env that resolves the bootstrap module.

    Starts from the prod env builder and applies the dev-dummy profile plus the
    bootstrap module name. The DJANGO_ONESHOT flag is present only when
    requested, so the same env can exercise both the "flag honoured" and the
    "module is not a universal bypass" directions.
    """
    env = _prod_env_overrides(
        DJANGO_SECRET_KEY=_DEV_DUMMY_SECRET,
        BOT_TOKEN=_DEV_DUMMY_SECRET,
        GOOGLE_TRANSLATE_API_KEY=_DEV_DUMMY_SECRET,
        EMAIL_HOST="",
        SITE_URL="",
        CSRF_TRUSTED_ORIGINS="",
    )
    env["DJANGO_SETTINGS_MODULE"] = _BOOTSTRAP_MODULE
    env.pop("DJANGO_ONESHOT", None)
    if oneshot_flag:
        env["DJANGO_ONESHOT"] = "1"
    return env


def test_oneshot_bypasses_secrets_for_oneshot_module() -> None:
    """DJANGO_ONESHOT=1 + config.settings.oneshot imports the dev-dummy profile.

    This is the positive bootstrap-path assertion VAL-001 requires: without it,
    "remove the bypass and let the dev stack break" would be a passing
    remediation. The inert-flag warning must be absent because the flag was
    honoured, not merely tolerated.
    """
    env = _bootstrap_env(oneshot_flag=True)
    result = _run_in_subprocess(env, "import django; django.setup()")
    assert result.returncode == 0, result.stderr
    assert "ImproperlyConfigured" not in result.stderr
    assert "ValueError" not in result.stderr
    assert "DJANGO_ONESHOT is set but ignored" not in result.stderr


def test_oneshot_module_still_requires_oneshot_flag() -> None:
    """The oneshot module without DJANGO_ONESHOT is refused.

    The mechanism is a pair, not a module name: this proves the new settings
    module is not itself a universal bypass. With the flag absent the SECRET_KEY
    guard fires, because the module star-imports prod's guards.
    """
    env = _bootstrap_env(oneshot_flag=False)
    result = _run_in_subprocess(env, "import django; django.setup()")
    assert result.returncode != 0, result.stderr
    assert "ImproperlyConfigured" in result.stderr
    assert "DJANGO_SECRET_KEY" in result.stderr


def test_django_build_flag_bypasses_all_prod_guards() -> None:
    """DJANGO_BUILD=1 + config.settings.prod imports the dev-dummy profile.

    BC-2's regression guard. The Docker image builder stage and Makefile's
    restore-test target run under config.settings.prod with no .env and must
    have every guard skipped at once, including REDIS_URL and the other secret
    guards. (EMAIL_HOST is not a guard since the Product Owner ruling of
    2026-10-03 — it only warns — but it is emptied here alongside them so the
    import profile is unchanged.)
    """
    env = _prod_env_overrides(
        DJANGO_SECRET_KEY=_DEV_DUMMY_SECRET,
        BOT_TOKEN=_DEV_DUMMY_SECRET,
        GOOGLE_TRANSLATE_API_KEY=_DEV_DUMMY_SECRET,
        EMAIL_HOST="",
        SITE_URL="",
        CSRF_TRUSTED_ORIGINS="",
        REDIS_URL="",
    )
    env["DJANGO_SETTINGS_MODULE"] = _PROD_MODULE
    env["DJANGO_BUILD"] = "1"
    result = _run_in_subprocess(env, "import django; django.setup()")
    assert result.returncode == 0, result.stderr
    assert "ImproperlyConfigured" not in result.stderr
    assert "ValueError" not in result.stderr


def test_oneshot_inherits_prod_logging() -> None:
    """The oneshot module carries prod's structured LOGGING (BC-7).

    A star-import means deleting the `from .prod import *` line would silently
    fall back to Django's plaintext DEFAULT_LOGGING with no shipped test on the
    oneshot module noticing. This pins the parity explicitly.
    """
    env = _bootstrap_env(oneshot_flag=True)
    code = (
        "import django; django.setup(); "
        "from django.conf import settings; "
        "fmt_class = settings.LOGGING['formatters']['json'].get('()', ''); "
        "handler_fmt = settings.LOGGING['handlers']['console'].get('formatter', ''); "
        "print(f'formatter_class={fmt_class}'); "
        "print(f'handler_formatter={handler_fmt}'); "
        "print(f'root_level={settings.LOGGING[\"root\"][\"level\"]}')"
    )
    result = _run_in_subprocess(env, code)
    assert result.returncode == 0, result.stderr
    assert _JSON_FORMATTER in result.stdout
    assert "handler_formatter=json" in result.stdout
    assert "root_level=WARNING" in result.stdout


def test_oneshot_pins_debug_and_smtp_transport() -> None:
    """The oneshot module does not inherit dev's DEBUG or console EMAIL_BACKEND.

    DEBUG is re-pinned to False so a bootstrap process never runs with DEBUG
    enabled even if a .env sets it. The module star-imports prod, not dev, so a
    bootstrap invocation with no EMAIL_BACKEND override resolves base.py's SMTP
    default rather than dev's console backend — CFG-004's harm class is kept
    out by construction. (The unconditional EMAIL_BACKEND re-pin in prod.py is
    CFG-004 / BLOCK 7, a separate block.)
    """
    env = _bootstrap_env(oneshot_flag=True)
    env["DEBUG"] = "True"
    code = (
        "import django; django.setup(); "
        "from django.conf import settings; "
        "print(f'debug={settings.DEBUG}'); "
        "print(f'email_backend={settings.EMAIL_BACKEND}')"
    )
    result = _run_in_subprocess(env, code)
    assert result.returncode == 0, result.stderr
    assert "debug=False" in result.stdout
    assert _SMTP_BACKEND in result.stdout
    assert "console.EmailBackend" not in result.stdout


def test_oneshot_shares_the_redis_cache() -> None:
    """The oneshot module keeps prod's Redis cache, not dev's LocMemCache.

    A LocMemCache here would silently unshare the rate-limit and
    stale-while-revalidate caches from web and bot while still looking healthy.
    """
    env = _bootstrap_env(oneshot_flag=True)
    code = (
        "import django; django.setup(); "
        "from django.conf import settings; "
        "print(settings.CACHES['default']['BACKEND'])"
    )
    result = _run_in_subprocess(env, code)
    assert result.returncode == 0, result.stderr
    assert _REDIS_CACHE in result.stdout
    assert "LocMemCache" not in result.stdout


def test_oneshot_flag_is_inert_under_a_valid_prod_environment() -> None:
    """A stale DJANGO_ONESHOT in a valid prod env warns and continues.

    Separates the warning from the raise. A stale DJANGO_ONESHOT=1 left in an
    operator's .env.prod must not make a correctly configured production boot
    fail — it must warn and continue.
    """
    env = _prod_env_overrides()  # fully valid production environment
    env["DJANGO_SETTINGS_MODULE"] = _PROD_MODULE
    env["DJANGO_ONESHOT"] = "1"
    result = _run_in_subprocess(env, "import django; django.setup()")
    assert result.returncode == 0, result.stderr
    assert "DJANGO_ONESHOT is set but ignored" in result.stderr
