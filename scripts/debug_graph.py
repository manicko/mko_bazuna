"""Check all migration dependencies for correct migration names."""
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

import django
django.setup()

from django.db.migrations import loader as migration_loader
from django.db.migrations.graph import DummyNode

# Patch to catch and print issues
original_build_graph = migration_loader.MigrationLoader.build_graph

def patched_build_graph(self):
    try:
        original_build_graph(self)
    except Exception:
        print("=== ALL DUMMY NODES (problematic dependencies) ===")
        for key in sorted(self.graph.node_map.keys()):
            node = self.graph.node_map[key]
            if isinstance(node, DummyNode):
                print(f"  DUMMY: {key} -> from {node.origin}")
        print("=== REAL NODES ===")
        for key in sorted(self.graph.node_map.keys()):
            node = self.graph.node_map[key]
            if not isinstance(node, DummyNode):
                print(f"  REAL: {key}")
        print("=== DONE ===")

migration_loader.MigrationLoader.build_graph = patched_build_graph

from django.db import connection
loader = migration_loader.MigrationLoader(connection, ignore_no_migrations=True)
print("SUCCESS")