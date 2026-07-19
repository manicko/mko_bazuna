#!/bin/bash
# Entrypoint script for Mko Bazuna containers
# Handles database wait and command execution

set -e

# Wait for database to be ready
wait_for_db() {
    # Skip DB wait if no DATABASE_URL configured
    if [ -z "$DATABASE_URL" ]; then
        return 0
    fi

    echo "Waiting for PostgreSQL..."
    for i in $(seq 1 30); do
        if uv run python -c "import psycopg; psycopg.connect('$DATABASE_URL')" 2>/dev/null; then
            echo "Database ready"
            return 0
        fi
        sleep 1
    done
    echo "ERROR: Database unavailable after 30s" >&2
    exit 1
}

# Execute logic
wait_for_db

exec "$@"