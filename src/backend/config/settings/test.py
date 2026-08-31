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


# Skip migration replay during test DB creation for faster --create-db.
# pytest-django uses create_test_db() (model introspection) instead of
# replaying migration files. The autouse fixture in conftest.py restores
# the 4 trigger DDL objects + 3 currency seed rows that
# MIGRATION_MODULES=None cannot regenerate.
#
# NOTE: We disable migrations for ALL apps (including Django built-ins like
# auth, contenttypes, admin, sessions) using the DisableMigrations class below.
# This is required because the custom apps have a densely connected cross-app
# FK dependency graph rooted at auth (via users). If only SOME custom apps
# are set to None, syncdb (which runs before migrations) will try to create
# FK constraints from syncdb apps to migrated apps before those tables exist,
# causing "relation <table> does not exist" errors.
# Disabling all migrations puts everything in syncdb mode — Django creates
# all tables first, then applies deferred FK constraints, so all tables
# exist before any constraint is created. The DisableMigrations class is the
# standard Django pattern for this (see Django docs on testing with models).
class DisableMigrations:
    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None


MIGRATION_MODULES = DisableMigrations()
