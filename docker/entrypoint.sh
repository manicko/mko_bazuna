#!/bin/bash
# Entrypoint script for Mko Bazuna containers
# Handles database wait, migrations, and command execution

set -e

# Wait for database to be ready
wait_for_db() {
    echo "Waiting for PostgreSQL..."
    for i in $(seq 1 30); do
        if uv run python -c "import os; import psycopg; psycopg.connect(os.environ['DATABASE_URL'])" 2>/dev/null; then
            echo "Database ready"
            return 0
        fi
        sleep 1
    done
    echo "ERROR: Database unavailable after 30s" >&2
    exit 1
}

# Run migrations once (with file lock for multi-container safety)
run_migrations() {
    MIGRATION_LOCK="/app/.migrations_done"

    if [ "$RUN_MIGRATIONS" != "false" ] && [ ! -f "$MIGRATION_LOCK" ]; then
        echo "Running database migrations..."
        uv run python src/backend/manage.py migrate --noinput

        # Create lock file after success
        touch "$MIGRATION_LOCK"
        echo "Migrations complete"
    else
        echo "Migrations skipped (lock exists or disabled)"
    fi
}

# Execute logic
wait_for_db
run_migrations
exec "$@"