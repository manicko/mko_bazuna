"""Check if users 0002 migration module loads correctly."""
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

import django
django.setup()

import importlib
import traceback

try:
    mod = importlib.import_module("apps.users.migrations.0002_user_chat_id")
    print(f"Module loaded: {mod}")
    print(f"Has Migration class: {hasattr(mod, 'Migration')}")
    if hasattr(mod, 'Migration'):
        m = mod.Migration
        print(f"dependencies: {m.dependencies}")
        print(f"operations count: {len(m.operations)}")
except Exception:
    traceback.print_exc()