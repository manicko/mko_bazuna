"""
Production settings for Mko Bazuna.
Imports base settings and applies production safety configuration.
"""

import logging
import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403, F401
from .secret_validation import is_placeholder, validate_bot_username

DEBUG = False

# Structured JSON logging for production (JSONL to stdout for log aggregation).
# Sensitive field values are redacted by RedactingJsonFormatter.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "apps.core.utils.json_logging.RedactingJsonFormatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        "django.request": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.server": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "django": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "telegram_bot": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# Error tracking via Sentry (optional — only if SENTRY_DSN is configured).
# Guarded with try/except ImportError so a missing sentry-sdk dependency
# does not crash the application boot.
if SENTRY_DSN and not DEBUG:  # noqa: F405 (SENTRY_DSN from base via *)
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=SENTRY_DSN,  # noqa: F405
            send_default_pii=False,
            traces_sample_rate=0.1,
        )
        logging.getLogger(__name__).info("Sentry error tracking initialized")
    except ImportError:
        logging.getLogger(__name__).warning(
            "sentry-sdk not installed — error tracking disabled"
        )

# ---------------------------------------------------------------------------
# Secret-validation bypass
# ---------------------------------------------------------------------------
# The eight secret guards below must run for every production settings module.
# Two control flags can suppress them, each with a different scope:
#
#   DJANGO_BUILD=1   — set ONLY in the Docker image builder stage
#                     (collectstatic --noinput) and in Makefile's restore-test
#                     target. There is no .env file during a build
#                     (.dockerignore excludes **/.env*), so the build uses
#                     placeholder secrets and must be allowed to import.
#                     Honoured unconditionally; the build stage cannot be
#                     distinguished by a settings module.
#
#   DJANGO_ONESHOT=1 — a dev bootstrap flag. It is honoured ONLY while the
#                     process is loading a settings module whose name does not
#                     end in ".prod". The dev one-shot services (migrate,
#                     load_cities, load_catalog, create_admin, seed) select the
#                     bootstrap module via
#                     DJANGO_SETTINGS_MODULE=config.settings.oneshot in the
#                     deployment descriptor (Compose environment:), which is
#                     set before read_env() runs and which overwrite=False
#                     cannot overwrite. Under config.settings.prod the flag is
#                     inert — it can never suppress a guard here.
#
# Long-lived web and bot services never set either flag; full secret
# validation always runs for them.
# ---------------------------------------------------------------------------
_PROD_SETTINGS_MODULE_SUFFIX = ".prod"


def _is_production_settings_module() -> bool:
    """Return True when the process is loading a production settings module.

    DJANGO_SETTINGS_MODULE is set in the process environment before settings
    import (manage.py, wsgi.py and asgi.py all setdefault it, and Compose sets
    it per service). read_env() uses overwrite=False, so a value written into
    a .env file cannot move an already-set process onto a non-production
    module. That is the trust boundary this predicate relies on.
    """
    return os.getenv("DJANGO_SETTINGS_MODULE", "").endswith(
        _PROD_SETTINGS_MODULE_SUFFIX
    )


_ONESHOT_REQUESTED = bool(os.getenv("DJANGO_ONESHOT"))
_SKIP_SECRET_VALIDATION = bool(
    os.getenv("DJANGO_BUILD")
    or (_ONESHOT_REQUESTED and not _is_production_settings_module())
)
if _ONESHOT_REQUESTED and _is_production_settings_module():
    logging.getLogger(__name__).warning(
        "DJANGO_ONESHOT is set but ignored: this process loaded the production "
        "settings module (DJANGO_SETTINGS_MODULE=%s), which always validates "
        "secrets. Remove DJANGO_ONESHOT from the environment and from the .env "
        "file; dev bootstrap services use config.settings.oneshot instead.",
        os.getenv("DJANGO_SETTINGS_MODULE", ""),
    )


# Fail fast: SECRET_KEY is required in production and must pass strength checks.
# base.py's env("DJANGO_SECRET_KEY") (no default) returns "" for a
# present-but-empty value — django-environ only raises when the var is
# unset, so an empty key would boot Django until first access raises
# ImproperlyConfigured inside a request (web process 500s on first CSRF
# read; the bot runs silently with an empty signing key). Fail at import.
# Skip during Docker build (DJANGO_BUILD=1) so collectstatic succeeds with
# the build-placeholder value; the real key is provided at runtime via
# .env.prod.
def _validate_production_secret(var_name: str, value: str) -> None:
    """Fail-fast validation for production secrets.

    Rejects values that look like dev-only dummies or match shipped placeholder
    templates — the placeholder pattern lives in
    config/settings/secret_validation.py, the single home shared by every
    settings module — or (for DJANGO_SECRET_KEY) are too short.

    Raises ImproperlyConfigured with a value-free message naming the env var
    and remediation guidance. Does NOT log the value itself.
    """
    if "dev-only-dummy" in value:
        raise ImproperlyConfigured(
            f"{var_name} appears to use a dev-only dummy value. "
            "Provide a real value via the .env.prod runtime file."
        )
    if is_placeholder(value):
        raise ImproperlyConfigured(
            f"{var_name} appears to be a placeholder value from a .env template. "
            "Replace it with the real value in .env.prod."
        )
    if var_name == "DJANGO_SECRET_KEY" and len(value) < 50:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY must be at least 50 characters in production. "
            'Regenerate with: python -c "from django.core.management.utils '
            'import get_random_secret_key; print(get_random_secret_key())"'
        )


if not _SKIP_SECRET_VALIDATION:
    if not SECRET_KEY:  # noqa: F405
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY must be set and non-empty in production. "
            "Provide it via the .env.prod runtime file."
        )
    _validate_production_secret("DJANGO_SECRET_KEY", SECRET_KEY)  # noqa: F405

# Fail fast: BOT_TOKEN is required in production. The bot process cannot
# function without a valid token; an empty value indicates a deployment error.
# Skipped during the Docker image build (DJANGO_BUILD=1) so collectstatic
# succeeds with the build placeholder. Dev bootstrap one-shots run
# config.settings.oneshot, not this module. The real token is provided at
# runtime via .env.prod, and web/bot services always enforce it here.
if not _SKIP_SECRET_VALIDATION:
    if not BOT_TOKEN:  # noqa: F405
        raise ImproperlyConfigured(
            "BOT_TOKEN must be set in production. "
            "Provide it via the .env.prod runtime file."
        )
    _validate_production_secret("BOT_TOKEN", BOT_TOKEN)  # noqa: F405

# Fail fast: GOOGLE_TRANSLATE_API_KEY is required in production.
# Skipped during the Docker image build (DJANGO_BUILD=1) so collectstatic
# succeeds with the build placeholder. Dev bootstrap one-shots run
# config.settings.oneshot, not this module. The real key is provided at
# runtime via .env.prod.
if not _SKIP_SECRET_VALIDATION:
    if not GOOGLE_TRANSLATE_API_KEY:  # noqa: F405
        raise ImproperlyConfigured(
            "GOOGLE_TRANSLATE_API_KEY must be set in production. "
            "Provide it via the .env.prod runtime file."
        )
    _validate_production_secret(
        "GOOGLE_TRANSLATE_API_KEY", GOOGLE_TRANSLATE_API_KEY  # noqa: F405
    )

# SITE_URL is required in production so Telegram alert links are absolute and
# correct. A dev-only default must not silently leak into prod traffic.
if not os.getenv("SITE_URL") and not _SKIP_SECRET_VALIDATION:  # noqa: F405
    raise ImproperlyConfigured(
        "SITE_URL must be set in production. "
        "Provide it via the .env.prod runtime file."
    )

# Fail fast: EMAIL_HOST is required in production so transactional emails
# (password resets, alert notifications, seller confirmations) are deliverable.
# Skipped during the Docker image build (DJANGO_BUILD=1) so collectstatic
# succeeds. Dev bootstrap one-shots run config.settings.oneshot, not this
# module. The real SMTP config is provided at runtime via .env.prod.
if not _SKIP_SECRET_VALIDATION:
    if not EMAIL_HOST:  # noqa: F405
        raise ImproperlyConfigured(
            "EMAIL_HOST must be set in production. "
            "Provide it via the .env.prod runtime file."
        )

# TLS-ready settings
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

# Secure cookies
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# HSTS: one-year duration for production (defense-in-depth alongside nginx)
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Static files via whitenoise (with input.css excluded from post-processing)
STATICFILES_STORAGE = "theme.storage.ThemeStaticFilesStorage"

# Allow hosts from environment (required)
if not ALLOWED_HOSTS:  # noqa: F405
    raise ValueError("ALLOWED_HOSTS must be set in production")

# Fail fast: CSRF_TRUSTED_ORIGINS is required in production behind a
# TLS-terminating proxy. Without it, Django rejects all POST requests with a
# valid CSRF token (HTTP 403) because the Origin/Referer header is not in the
# allow-list. Skipped during the Docker image build (DJANGO_BUILD=1) so
# collectstatic succeeds with the build placeholder. Dev bootstrap one-shots
# run config.settings.oneshot, not this module. The real origins are provided
# at runtime via .env.prod.
if not CSRF_TRUSTED_ORIGINS and not _SKIP_SECRET_VALIDATION:  # noqa: F405
    raise ValueError("CSRF_TRUSTED_ORIGINS must be set in production")

# Fail fast: REDIS_URL is required in production for shared caching and bot FSM.
# base.py's env("REDIS_URL", default="") returns "" for a present-but-empty value,
# so without this guard a deployment missing REDIS_URL would silently fall back to
# MemoryStorage for the bot FSM (ephemeral state) and an empty cache location.
# Skipped during the Docker image build (DJANGO_BUILD=1). Dev bootstrap one-shots
# run config.settings.oneshot, not this module. The real URL is provided at
# runtime via .env.prod.
if not _SKIP_SECRET_VALIDATION:
    if not REDIS_URL:  # noqa: F405
        raise ImproperlyConfigured(
            "REDIS_URL must be set in production. "
            "Provide it via the .env.prod runtime file."
        )

# Fail fast: BOT_USERNAME is required in production. It is a public Telegram
# handle rather than a secret, but it is persisted into SiteConfig.bot_username
# by migration 0003 and read back from the database, so a template or malformed
# value produces dead t.me/ deep links site-wide — invisibly, because the
# telegram_deep_link template tag base64-encodes it behind href="#".
#
# It lives inside the secret-validation block because that block is the
# project's single "this variable must be real when we serve traffic"
# mechanism. Widening the block to cover a non-secret value is a deliberate
# choice, made here; it is not justified by confidentiality.
#
# Skipped during the Docker image build (DJANGO_BUILD=1), which runs
# collectstatic under this module with no .env at all, and under
# config.settings.oneshot, which is what the dev bootstrap one-shots load. In
# that bootstrap path the guard cannot help: migration 0003's full_clean() is
# what stops a bad value reaching the database there.
#
# A correct value in .env.prod does NOT repair a row already seeded with a
# placeholder — the database is the source of truth after 0003. Run
# `manage.py repair_bot_username`, or edit SiteConfig in the Django admin.
if not _SKIP_SECRET_VALIDATION:
    validate_bot_username("BOT_USERNAME", BOT_USERNAME)  # noqa: F405
