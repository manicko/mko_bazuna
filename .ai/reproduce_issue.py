"""Reproduce the issue: check if create_test_db creates exchange_rates table."""
import os
os.environ.setdefault("PYTHONPATH", "src;src/backend")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")
os.environ.setdefault("DATABASE_URL", "postgres://postgres:postgres@localhost:5433/mko_bazuna")
os.environ.setdefault("POSTGRES_PASSWORD", "postgres")
os.environ.setdefault("DJANGO_SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault("SKIP_ENV_CHECK", "1")

import django
django.setup()

from django.db import connection
from django.test.utils import setup_databases, teardown_databases

# Drop any existing test DB
with connection.cursor() as cur:
    cur.execute("DROP DATABASE IF EXISTS test_mko_bazuna WITH (FORCE)")
print("Dropped test DB if existed")

# Create test DB
old_config = setup_databases(
    verbosity=2,
    interactive=False,
    aliases={"default"},
    serialized_aliases=None,
    keepdb=False,
)
print("Test DB created successfully")

# Check if exchange_rates table exists
with connection.cursor() as cur:
    cur.execute("SELECT tablename FROM pg_tables WHERE tablename = 'exchange_rates'")
    result = cur.fetchone()
    print("exchange_rates table exists:", result is not None)

# Also check all currency-related tables
with connection.cursor() as cur:
    cur.execute("SELECT tablename FROM pg_tables WHERE tablename LIKE 'exchange%' OR tablename LIKE 'currenc%'")
    tables = cur.fetchall()
    print("Currency-related tables:", tables)

# Try load_exchange_rates
from django.core.management import call_command
try:
    call_command("load_exchange_rates")
    print("load_exchange_rates succeeded")
except Exception as e:
    print(f"load_exchange_rates FAILED: {type(e).__name__}: {e}")

# Cleanup
teardown_databases(old_config, verbosity=0)
