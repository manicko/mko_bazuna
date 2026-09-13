"""
Migration-reproducibility test settings.

Inherits all test settings but re-enables migration file discovery
(MIGRATION_MODULES = {}) and uses a unique TEST database name so the
subprocess does not collide with pytest-django's test_mko_bazuna
during xdist parallel runs.

This module is loaded ONLY by subprocess-based tests in
apps/core/tests/test_migrations.py. It is never used by the main pytest
suite (which uses config.settings.test with DisableMigrations for speed).
"""

from .test import *  # noqa: F403, F401

# Re-enable migration file discovery for all apps.
# (test.py sets MIGRATION_MODULES = DisableMigrations() which hides migration files.)
MIGRATION_MODULES = {}

# Unique test DB name so the subprocess's setup_databases() doesn't
# collide with pytest-django's test_mko_bazuna during xdist parallel runs.
DATABASES["default"]["TEST"] = {  # noqa: F405
    "NAME": "test_migration_repro",
    "SERIALIZE": False,
}
