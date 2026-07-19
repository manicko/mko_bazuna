"""
Test settings for Mko Bazuna.
Imports base settings and applies test-specific configuration.
Uses real PostgreSQL (NOT SQLite) per spec.
"""

from .base import *  # noqa: F403, F401

DEBUG = True

# Use real PostgreSQL for testing (per spec zone C5)
# The base settings already configure PostgreSQL, but we ensure test DB is used
DATABASES["default"]["NAME"] = "mko_bazuna_test"  # noqa: F405

# Faster password hasher for tests
PASSWORD_HASHERS = [  # noqa: F405
    "django.contrib.auth.hashers.MD5PasswordHasher",
]