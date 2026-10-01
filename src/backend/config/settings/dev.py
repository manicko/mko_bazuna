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
# proxy). Off => the cookie is named ``login_browser_id`` and is emitted without
# ``Secure`` (see login_token.py, which derives both from this one setting); a
# ``__Host-``-prefixed cookie without ``Secure`` is rejected by every conformant
# user agent, which would silently discard the cookie and turn every dev login
# into a 410. The prefix control is therefore absent on an HTTP-only origin by
# design. Kept in the transport tuple so dev/test parity is machine-checked.
LOGIN_BROWSER_ID_COOKIE_HOST_PREFIX = False

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

# No extra trusted proxy networks in dev: the default dev stack publishes Django
# directly on :8000, so the peer is loopback and the gate in
# apps/core/utils/client_ip.py is already open.
TRUSTED_PROXY_NETWORKS: tuple[str, ...] = ()

# Development uses in-process cache (no Redis needed).
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# Email: console backend so no SMTP server is needed in development.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
