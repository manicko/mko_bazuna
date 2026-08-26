#!/bin/bash
set -e

# === Phase 1: Measure uv sync time ===
SYNC_START=$(date +%s.%N)
uv sync --frozen --no-install-project --group dev
SYNC_END=$(date +%s.%N)
echo "UV_SYNC_ELAPSED=$(echo "$SYNC_END - $SYNC_START" | bc)"

# === Phase 2: Measure DB connection wait ===
DB_START=$(date +%s.%N)
echo "Waiting for PostgreSQL..."
DB_READY=0
for i in $(seq 1 30); do
    if uv run python -c "import psycopg; psycopg.connect('$DATABASE_URL')" 2>/dev/null; then
        echo "Database ready"
        DB_READY=1
        break
    fi
    sleep 1
done
DB_END=$(date +%s.%N)
echo "DB_WAIT_ELAPSED=$(echo "$DB_END - $DB_START" | bc)"

if [ "$DB_READY" = "0" ]; then
    echo "ERROR: Database unavailable after 30s" >&2
    exit 1
fi

# === Phase 3: Measure migration time ===
MIG_START=$(date +%s.%N)
echo "Running migrations..."
uv run python -c "from apps.core.utils.migrate_locked import main; import sys; sys.exit(main())"
MIG_END=$(date +%s.%N)
echo "MIGRATION_ELAPSED=$(echo "$MIG_END - $MIG_START" | bc)"

# Compile translations
echo "Compiling translations..."
uv run python src/backend/manage.py compilemessages

echo "STARTUP_COMPLETE"
# Keep container alive for exec
sleep 3600
