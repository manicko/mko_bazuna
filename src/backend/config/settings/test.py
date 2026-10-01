"""
Test settings for Mko Bazuna.
Imports base settings and applies test-specific configuration.
Uses real PostgreSQL (NOT SQLite) per spec.
"""

from .base import *  # noqa: F403, F401
from .base import _db_options

# English is the msgid source language — tests asserting on English UI strings
# (e.g. "Clear all filters", "Page navigation") pass without explicit language
# setup. Tests needing Russian must set ?lang=ru explicitly (see conftest.py
# autouse _reset_translation_state fixture and the i18n testing convention
# in docs/99-agent/rules.md).
LANGUAGE_CODE = "en"

DEBUG = True

# No extra trusted proxy networks in tests: Django's test client peers from
# loopback, so the gate in apps/core/utils/client_ip.py is already open.
TRUSTED_PROXY_NETWORKS: tuple[str, ...] = ()

# Disable SSL/TLS redirect and secure cookies for the test client, which issues
# plain HTTP requests. Without this, SecurityMiddleware 301-redirects every
# request to HTTPS and breaks all DB-backed view tests.
# Mirrors config/settings/dev.py (test settings must behave like dev, not prod):
# all seven transport settings are reset here, and
# test_settings_defaults.test_dev_and_test_share_the_transport_tuple asserts the
# two modules stay in agreement.
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
LOGIN_BROWSER_ID_COOKIE_HOST_PREFIX = False
# The HSTS triple is inherited from base.py (3600 / True / False) unless it is
# reset here. Left inherited, a browser — or any browser-driven tool — pointed at
# a test-mode server would cache `Strict-Transport-Security: max-age=3600;
# includeSubDomains` after one request and upgrade every subsequent http://
# request to HTTPS for an hour. dev.py zeroes the triple for exactly this reason;
# this module must not differ.
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

# pytest-django creates/destroys test database automatically
# Base database connection is for pytest to create test_<name> database
DATABASES["default"]["NAME"] = "mko_bazuna"  # noqa: F405

# Preserve the connection-level ``lock_timeout`` bound carried in base.py's
# ``OPTIONS["options"]``. base.py builds it via ``_db_options()`` for both
# DATABASES branches (03-DB-004/BLOCK 5); test settings must not drop it, or
# ``SHOW lock_timeout`` is 0 (unbounded) for the whole suite and the bounded-wait
# behaviour is never exercised under test. Reuse the same helper so the rendered
# ``-c lock_timeout=<N>s`` string stays a single source of truth; the inherited
# ``prepare_threshold`` key is untouched.
DATABASES["default"]["OPTIONS"] = {  # noqa: F405
    **DATABASES["default"].get("OPTIONS", {}),  # noqa: F405
    "options": _db_options()["options"],
}

# Use a non-hashed, non-manifest static storage during tests.
# base.py's STORAGES["staticfiles"] backend is ThemeStaticFilesStorage, a
# whitenoise CompressedManifestStaticFilesStorage that requires a
# staticfiles.json manifest produced by ``collectstatic``. Tests never run
# ``collectstatic``, so the manifest does not exist and template ``{% static %}``
# lookups raise ``ValueError: Missing staticfiles manifest entry``. Switching to
# StaticFilesStorage (which serves original, un-hashed paths) is the standard
# Django testing pattern and avoids any dependency on a build-time artifact.
# This is a deliberate test-only override; nothing in this module changes
# base.py's STORAGES (and prod.py has no static-files assignment of its own).
STORAGES = {  # noqa: F405
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

# Disable the bot liveness marker in tests so LivenessMiddleware and the
# startup/shutdown hooks become no-op pass-throughs (no real files written).
# Set BOT_LIVENESS_FILE="" so lifecycle._marker_path() returns None.
BOT_LIVENESS_FILE = ""  # noqa: F405

# Disable scheduler liveness marker in tests (no scheduler process runs in tests).
SCHEDULER_LIVENESS_FILE = ""  # noqa: F405

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

# Email: in-memory backend for tests (no SMTP, messages captured in mail.outbox).
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"


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
