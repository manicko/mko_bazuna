"""
Development settings for Mko Bazuna.
Imports base settings and overrides for local development.
"""

from .base import *  # noqa: F403, F401

DEBUG = True

# No SSL redirect for development (uses HTTP)
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
# The login-binding cookie is plain HTTP in the default dev stack
# (docker-compose.dev.override.yml publishes Django directly on :8000 with no
# proxy). It must therefore follow this module, not base.py, or a browser
# silently discards it. Kept in the transport tuple so dev/test parity is
# machine-checked.
LOGIN_BROWSER_ID_COOKIE_SECURE = False

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

# Email: console backend so no SMTP server is needed in development.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
