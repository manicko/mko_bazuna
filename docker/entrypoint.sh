#!/bin/bash
# Entrypoint script for Mko Bazuna containers
# Handles database wait, volume permissions, and command execution

set -e

# Fail fast if .env file is missing (container environment check)
# Note: Test environment sets variables directly via compose, no .env needed
check_env_file() {
    # Check both possible .env locations (depends on source layout)
    ENV_PATH="/app/src/.env"
    if [ ! -f "$ENV_PATH" ]; then
        ENV_PATH="/app/.env"
    fi
    if [ -z "$SKIP_ENV_CHECK" ] && [ ! -f "$ENV_PATH" ]; then
        if [ "$DJANGO_SETTINGS_MODULE" != "config.settings.test" ]; then
            echo "ERROR: .env file not found. Copy .env.example to .env and configure values." >&2
            exit 1
        fi
    fi
}

# Fix volume permissions for Windows/WSL2 bind mounts (dev mode)
fix_volume_permissions() {
    # Only needed in development with bind mounts
    if [ "$DEBUG" = "True" ] || [ "$FIX_PERMISSIONS" = "1" ]; then
        echo "Fixing media volume permissions..."
        chown -R 1000:1000 /app/media 2>/dev/null || true
    fi
}

# Wait for database to be ready
wait_for_db() {
    # Skip DB wait if no DATABASE_URL configured (e.g., for static-only builds)
    if [ -z "$DATABASE_URL" ]; then
        return 0
    fi

    echo "Waiting for PostgreSQL..."
    for i in {1..30}; do
        if /opt/venv/bin/python -c "import psycopg; psycopg.connect('$DATABASE_URL')" 2>/dev/null; then
            echo "Database ready"
            return 0
        fi
        sleep 1
    done
    echo "ERROR: Database unavailable after 30s" >&2
    exit 1
}

# Execute logic
check_env_file
fix_volume_permissions
wait_for_db

exec "$@"
