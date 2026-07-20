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