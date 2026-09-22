"""
Production settings for Mko Bazuna.
Imports base settings and applies production safety configuration.
"""

import logging
import os
import re

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403, F401

# Matches values shipped as templates in .env.*.example files, e.g.
# <generate-with-django-secret-key-generator>, <your-bot-token-from-botfather>
_SECRET_PLACEHOLDER_RE = re.compile(r"^<[^>]+>$")

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

    Rejects values that look like dev-only dummies, match shipped placeholder
    templates, or (for DJANGO_SECRET_KEY) are too short — all of which would
    leave the app signed with a publicly-knowable or forgeable key.

    Raises ImproperlyConfigured with a value-free message naming the env var
    and remediation guidance. Does NOT log the value itself.
    """
    if var_name == "DJANGO_SECRET_KEY" and "dev-only-dummy" in value:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY appears to use a dev-only dummy value. "
            "Provide a real key via the .env.prod runtime file."
        )
    if _SECRET_PLACEHOLDER_RE.match(value):
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


if not os.getenv("DJANGO_BUILD"):
    if not SECRET_KEY:  # noqa: F405
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY must be set and non-empty in production. "
            "Provide it via the .env.prod runtime file."
        )
    _validate_production_secret("DJANGO_SECRET_KEY", SECRET_KEY)  # noqa: F405

# Fail fast: BOT_TOKEN is required in production. The bot process cannot
# function without a valid token; an empty value indicates a deployment error.
# Skip during Docker build (DJANGO_BUILD=1) so collectstatic succeeds with
# placeholder values; the real token is provided at runtime via .env.prod.
# Truthiness-only guard: placeholder rejection is intentionally NOT extended
# here or to GOOGLE_TRANSLATE_API_KEY (see scoping decision in plan 30 §3.2.1)
# — dev one-shot services (migrate/load_cities/load_catalog) run with
# config.settings.prod and are fed placeholder tokens via docker-compose.
if not os.getenv("DJANGO_BUILD"):
    if not BOT_TOKEN:  # noqa: F405
        raise ImproperlyConfigured(
            "BOT_TOKEN must be set in production. "
            "Provide it via the .env.prod runtime file."
        )

# Fail fast: GOOGLE_TRANSLATE_API_KEY is required in production.
# Skip during Docker build (DJANGO_BUILD=1) so collectstatic succeeds.
if not os.getenv("DJANGO_BUILD"):
    if not GOOGLE_TRANSLATE_API_KEY:  # noqa: F405
        raise ImproperlyConfigured(
            "GOOGLE_TRANSLATE_API_KEY must be set in production. "
            "Provide it via the .env.prod runtime file."
        )

# SITE_URL is required in production so Telegram alert links are absolute and
# correct. A dev-only default must not silently leak into prod traffic.
if not os.getenv("SITE_URL") and not os.getenv("DJANGO_BUILD"):  # noqa: F405
    raise ImproperlyConfigured(
        "SITE_URL must be set in production. "
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
# allow-list. Skip during Docker build (DJANGO_BUILD=1) so collectstatic
# succeeds with placeholder values; the real origins are provided at runtime
# via .env.prod.
if not CSRF_TRUSTED_ORIGINS and not os.getenv("DJANGO_BUILD"):  # noqa: F405
    raise ValueError("CSRF_TRUSTED_ORIGINS must be set in production")
