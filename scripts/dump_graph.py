"""Script to dump migration graph before validation."""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

import django
django.setup()

from django.db.migrations.loader import MigrationLoader
from django.db import connection

loader = MigrationLoader(connection, ignore_no_migrations=True)

# Print all REAL nodes
print("=== REAL NODES ===")
for k in sorted(loader.graph.node_map.keys()):
    v = loader.graph.node_map[k]
    if not hasattr(v, "raise_error"):
        print(f"  REAL: {k}")

# Print all DUMMY nodes
print("=== DUMMY NODES ===")
for k in sorted(loader.graph.node_map.keys()):
    v = loader.graph.node_map[k]
    if hasattr(v, "raise_error"):
        print(f"  DUMMY: {k} -> {v.error_message}")

print("=== DONE ===")