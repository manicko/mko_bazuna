import os
import sys

os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.test"
os.environ["DJANGO_SECRET_KEY"] = "test-secret-key-for-testing-only"
os.environ["BOT_TOKEN"] = "test-bot-token-for-testing"
os.environ["DATABASE_URL"] = "postgres://postgres:postgres@localhost:5433/mko_bazuna"
sys.path.insert(0, "src")
sys.path.insert(0, "src/backend")

import django
django.setup()

from django.db import connection

renames = [
    ("ads", "0002_initial", "0002_add_fks_and_search_triggers"),
    ("analytics", "0002_initial", "0002_add_user_fks_and_metrics"),
    ("moderation", "0002_initial", "0002_add_fks_and_priority_indexes"),
    ("search", "0002_initial", "0002_add_fks_indexes_constraints"),
    ("trust", "0002_initial", "0002_add_user_fks"),
]

with connection.cursor() as cursor:
    for app, old_name, new_name in renames:
        cursor.execute(
            "UPDATE django_migrations SET name = %s WHERE app = %s AND name = %s",
            [new_name, app, old_name],
        )
        print(f"Renamed {app}.{old_name} -> {app}.{new_name} ({cursor.rowcount} row(s) affected)")

connection.commit()
print("\nDone. Updated migration history:")
with connection.cursor() as cursor:
    cursor.execute(
        'SELECT app, name FROM django_migrations '
        'WHERE app IN (%s, %s, %s, %s, %s) '
        'ORDER BY app, name',
        ["ads", "analytics", "trust", "moderation", "search"],
    )
    for row in cursor.fetchall():
        print(row)
