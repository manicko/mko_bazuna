#!/bin/bash
# Test entrypoint for Mko Bazuna
# Runs migrations then pytest in ephemeral PostgreSQL environment

set -e

# Wait for database to be ready
echo "Waiting for PostgreSQL..."
for i in $(seq 1 30); do
    if uv run python -c "import psycopg; psycopg.connect('$DATABASE_URL')" 2>/dev/null; then
        echo "Database ready"
        break
    fi
    sleep 1
done

if [ "$i" = "30" ]; then
    echo "ERROR: Database unavailable after 30s" >&2
    exit 1
fi

# Run migrations (idempotent via advisory lock)
echo "Running migrations..."
uv run python -c "from apps.core.utils.migrate_locked import main; import sys; sys.exit(main())"

# Run pytest with short traceback format
echo "Running tests..."
uv run pytest --tb=short