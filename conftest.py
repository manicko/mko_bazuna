"""Pytest configuration for Mko Bazuna tests."""

import os
from pathlib import Path

# Set Django settings module before Django loads
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")

# Set required env vars if not present (for local testing)
if "DJANGO_SECRET_KEY" not in os.environ:
    os.environ["DJANGO_SECRET_KEY"] = "test-secret-key-for-validation-only"

import django

django.setup()