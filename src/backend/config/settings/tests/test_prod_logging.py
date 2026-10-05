"""Subprocess-based tests for prod.py logging and Sentry initialization.

Settings are evaluated at import time and Django caches them on first access,
so override_settings/monkeypatch cannot test import-time configuration.
These tests use subprocess isolation with controlled os.environ.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tomllib
from pathlib import Path
from types import ModuleType

import pytest

from config.settings.tests import TEST_SECRET_KEY

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
    env["DJANGO_SECRET_KEY"] = overrides.pop("DJANGO_SECRET_KEY", TEST_SECRET_KEY)
    env["BOT_TOKEN"] = overrides.pop("BOT_TOKEN", "test-bot-token-for-testing-only")
    # Must be explicit: without it the builder inherits whatever the ambient
    # environment supplies, which differs between the Docker test container
    # (.env.test) and the CI test job (no .env). See BLOCK 5 decision D1.
    env["BOT_USERNAME"] = overrides.pop("BOT_USERNAME", "test_bot_for_testing_only")
    # LOG_MASK_KEY is required by the prod.py fail-fast guard (06-PII-112). It
    # must be non-empty, non-placeholder and >= 32 bytes; this literal is all
    # three. It is not a real key.
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


@pytest.mark.slow
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


def test_sentry_malformed_dsn_degrades_without_crashing() -> None:
    """A malformed SENTRY_DSN leaves config.settings.prod importable and booting.

    sentry_sdk.init raises BadDsn for an unrecognised scheme, and that exception
    escaped the settings-module import, taking every process that imports
    config.settings.prod offline (12-OPS-013). The guard handles BadDsn
    explicitly so the process still boots with error tracking disabled. The live
    trigger is a malformed scheme — a trailing space or newline is handled by
    sentry-sdk 2.69.2 and would assert nothing.
    """
    env = _prod_env_overrides(SENTRY_DSN="not-a-valid-dsn")
    env["PYTHONPATH"] = os.pathsep.join(sys.path)
    import_code = (
        "import django; django.setup(); "
        "import sentry_sdk; "
        "client = sentry_sdk.get_client(); "
        "print('BOOTED'); "
        "print('DISABLED' if client.dsn is None else 'HAS_CLIENT')"
    )
    result = _run_in_subprocess(env, import_code)
    assert result.returncode == 0, result.stderr
    assert "BOOTED" in result.stdout
    assert "DISABLED" in result.stdout
    # The DSN value must never appear in the emitted output.
    assert "not-a-valid-dsn" not in result.stdout
    assert "not-a-valid-dsn" not in result.stderr


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


def test_prod_settings_email_accessible() -> None:
    """prod settings import successfully and expose EMAIL_* settings."""
    env = _prod_env_overrides()
    env["PYTHONPATH"] = os.pathsep.join(sys.path)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import django; django.setup(); "
                "from django.conf import settings; "
                "print(f'email_host={settings.EMAIL_HOST}'); "
                "print(f'email_port={settings.EMAIL_PORT}'); "
                "print(f'email_backend={settings.EMAIL_BACKEND}'); "
                "print(f'default_from_email={settings.DEFAULT_FROM_EMAIL}')"
            ),
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "email_host=smtp.example.com" in result.stdout
    assert "email_port=587" in result.stdout
    assert "email_backend=django.core.mail.backends.smtp.EmailBackend" in result.stdout
    assert "default_from_email=noreply@example.com" in result.stdout


# ---------------------------------------------------------------------------
# gunicorn log routing (12-OPS-012)
# ---------------------------------------------------------------------------
# Gunicorn emits its access/error records through its OWN handlers, which never
# pass through Django's `LOGGING` tree — so `RedactingJsonFormatter` never saw
# the highest-volume record type in production, and a query string carrying PII
# in a request path was logged in the clear. gunicorn.conf.py now supplies a
# `logconfig_dict` routing `gunicorn.access` and `gunicorn.error` through the
# existing formatter. These guards load the real config by file path (it is not
# importable as a package module) and assert a RENDERED record, not merely that
# the key is present.

_GUNICORN_CONF_PATH = _ROOT / "gunicorn.conf.py"


def _load_gunicorn_conf() -> ModuleType:
    """Load gunicorn.conf.py from the repository root by file path."""
    spec = importlib.util.spec_from_file_location("gunicorn_conf", _GUNICORN_CONF_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gunicorn_routes_logs_through_redacting_formatter() -> None:
    """gunicorn.access and gunicorn.error route through RedactingJsonFormatter.

    A `dictConfig` factory reference is resolved by class path, so the test
    instantiates the handler's formatter exactly as gunicorn's startup does and
    asserts its type (12-OPS-012).
    """
    conf = _load_gunicorn_conf()
    logconfig = conf.logconfig_dict
    formatter_path = logconfig["formatters"]["json"]["()"]
    assert formatter_path == (
        "apps.core.utils.json_logging.RedactingJsonFormatter"
    ), f"the json formatter must be the redacting formatter, got {formatter_path!r}"

    handler_formatters = {
        handler_name: handler["formatter"]
        for handler_name, handler in logconfig["handlers"].items()
    }
    for logger_name in ("gunicorn.access", "gunicorn.error"):
        logger_cfg = logconfig["loggers"][logger_name]
        for handler_name in logger_cfg["handlers"]:
            assert handler_formatters[handler_name] == "json", (
                f"{logger_name} must use the json (redacting) formatter via "
                f"handler {handler_name!r} (12-OPS-012)"
            )


def test_gunicorn_rendered_access_record_is_redacted() -> None:
    """A rendered gunicorn access record carrying PII comes back redacted.

    The record is built the way gunicorn builds it (the access format string
    with an atoms mapping) and rendered through the formatter the config
    installs. The assertions are on the OBSERVABLE output: it is JSON, the
    sensitive parameter is redacted, and the raw value is absent (12-OPS-012).
    """
    import json as json_module
    import logging
    import logging.config

    from apps.core.utils.json_logging import RedactingJsonFormatter

    conf = _load_gunicorn_conf()
    logging.config.dictConfig(conf.logconfig_dict)

    access_logger = logging.getLogger("gunicorn.access")
    formatter = None
    for handler in access_logger.handlers:
        if isinstance(handler.formatter, RedactingJsonFormatter):
            formatter = handler.formatter
            break
    assert formatter is not None, (
        "gunicorn.access must have a handler using RedactingJsonFormatter after "
        "dictConfig (12-OPS-012)"
    )

    record = logging.LogRecord(
        name="gunicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg=conf.access_log_format,
        args={
            "h": "127.0.0.1",
            "l": "-",
            "u": "-",
            "t": "[05/Oct/2026:00:43:16 +0000]",
            "r": "GET /search/?token=SUPERSECRET123&q=hello HTTP/1.1",
            "s": "200",
            "b": "2",
            "f": "-",
            "a": "curl/8.14.1",
            "L": "0.001180",
        },
        exc_info=None,
    )
    rendered = formatter.format(record)

    payload = json_module.loads(rendered)
    assert payload["logger"] == "gunicorn.access"
    assert "SUPERSECRET123" not in rendered, (
        "the rendered access record must not contain the raw sensitive value "
        "(12-OPS-012)"
    )
    assert "token=REDACTED" in payload["message"], (
        "a sensitive-looking query parameter must be redacted in the rendered "
        f"access record (12-OPS-012): {payload['message']!r}"
    )


def test_gunicorn_keeps_access_and_error_logs_set() -> None:
    """accesslog and errorlog must stay set — silence is a failure mode.

    A broken `logconfig_dict` should surface as a diagnostic plaintext line, not
    as silence (12-OPS-012).
    """
    conf = _load_gunicorn_conf()
    assert conf.accesslog == "-", "accesslog must stay set (12-OPS-012)"
    assert conf.errorlog == "-", "errorlog must stay set (12-OPS-012)"
