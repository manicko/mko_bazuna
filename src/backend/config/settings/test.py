"""
Test settings for Mko Bazuna.
Imports base settings and applies test-specific configuration.
Uses real PostgreSQL (NOT SQLite) per spec.
"""

from .base import *  # noqa: F403, F401

DEBUG = True

# pytest-django creates/destroys test database automatically
# Base database connection is for pytest to create test_<name> database
DATABASES["default"]["NAME"] = "mko_bazuna"  # noqa: F405

# Faster password hasher for tests
PASSWORD_HASHERS = [  # noqa: F405
    "django.contrib.auth.hashers.MD5PasswordHasher",
]