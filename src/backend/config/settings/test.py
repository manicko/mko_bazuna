"""
Test settings for Mko Bazuna.
Imports base settings and applies test-specific configuration.
Uses real PostgreSQL (NOT SQLite) per spec.
"""

from .base import *  # noqa: F403, F401

DEBUG = True

# Disable SSL/TLS redirect and secure cookies for the test client, which issues
# plain HTTP requests. Without this, SecurityMiddleware 301-redirects every
# request to HTTPS and breaks all DB-backed view tests.
# Mirrors config/settings/dev.py (test settings must behave like dev, not prod).
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# pytest-django creates/destroys test database automatically
# Base database connection is for pytest to create test_<name> database
DATABASES["default"]["NAME"] = "mko_bazuna"  # noqa: F405

# Use a non-hashed, non-manifest static storage during tests.
# The production/dev storage (ThemeStaticFilesStorage) is a
# CompressedManifestStaticFilesStorage that requires a staticfiles.json
# manifest produced by ``collectstatic``. Tests never run ``collectstatic``,
# so the manifest does not exist and template ``{% static %}`` lookups raise
# ``ValueError: Missing staticfiles manifest entry``. Switching to
# StaticFilesStorage (which serves original, un-hashed paths) is the standard
# Django testing pattern and avoids any dependency on a build-time artifact.
# Production and dev settings remain unchanged.
STORAGES = {  # noqa: F405
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

# Faster password hasher for tests
PASSWORD_HASHERS = [  # noqa: F405
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Test uses in-process cache (no Redis needed for test suite).
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}