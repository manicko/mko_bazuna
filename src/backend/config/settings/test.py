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

# Faster password hasher for tests
PASSWORD_HASHERS = [  # noqa: F405
    "django.contrib.auth.hashers.MD5PasswordHasher",
]