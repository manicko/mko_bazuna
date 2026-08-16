"""Pytest configuration for Mko Bazuna tests."""

import os
from pathlib import Path

# Set Django settings module before Django loads
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")

# Set required env vars if not present (for local testing)
if "DJANGO_SECRET_KEY" not in os.environ:
    os.environ["DJANGO_SECRET_KEY"] = "test-secret-key-for-validation-only"

# BOT_TOKEN is required by base.py - set a placeholder for local testing
if "BOT_TOKEN" not in os.environ:
    os.environ["BOT_TOKEN"] = "test-bot-token-for-local-testing"

# Local PostgreSQL connection for host-side `uv run pytest`.
# `uv run` does NOT auto-load .env files, so the DB config from src/backend/.env
# is not picked up automatically. Load it explicitly if present, then guarantee a
# working DATABASE_URL. Use 127.0.0.1 (not `localhost`) to avoid the Windows IPv6
# (::1) connection timeout when Postgres is Docker-published on IPv4 only.
# Override with a real DATABASE_URL env var if your database lives elsewhere.
# Set a working DATABASE_URL before loading .env so that local host testing
# (port 5433) works even when .env points at the Docker-internal hostname 'db'.
# Users can override by setting DATABASE_URL explicitly in their shell.
os.environ.setdefault(
    "DATABASE_URL",
    "postgres://postgres:postgres@127.0.0.1:5433/mko_bazuna",
)

_local_env = Path(__file__).resolve().parent / "src" / "backend" / ".env"
if _local_env.is_file():
    import environ

    environ.Env.read_env(str(_local_env), override=False)

import django  # noqa: E402

django.setup()  # noqa: E402