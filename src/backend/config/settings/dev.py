"""
Development settings for Mko Bazuna.
Imports base settings and overrides for local development.
"""

import re

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403, F401

# Matches values shipped as templates in .env.*.example files, e.g.
# <your-bot-token-from-botfather>. Copied from prod._SECRET_PLACEHOLDER_RE
# to avoid importing prod settings (which carry logging/Sentry config).
_BOT_TOKEN_PLACEHOLDER_RE = re.compile(r"^<[^>]+>$")

# Fail fast: reject truthy-but-placeholder BOT_TOKEN values. Empty tokens are
# allowed (the bot's `if not token: return` guard skips startup gracefully).
# This is dev-only — prod has its own guard (prod.py:140-145).
if BOT_TOKEN and _BOT_TOKEN_PLACEHOLDER_RE.match(BOT_TOKEN):  # noqa: F405
    raise ImproperlyConfigured(
        "BOT_TOKEN is a placeholder value from .env.dev.example. "
        "Replace it with a real token from @BotFather, or leave it empty "
        "(BOT_TOKEN=) to skip bot startup in development."
    )

DEBUG = True

# No SSL redirect for development (uses HTTP)
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Console logging for development
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}

# HSTS completely disabled in development (prevents browser caching issues)
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

# Proxy settings for nginx TLS termination in dev
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

# Development uses in-process cache (no Redis needed).
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}
