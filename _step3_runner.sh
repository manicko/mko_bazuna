#!/bin/bash
set -e

# ============================================================
# Step 3: Startup Overhead Measurement
# ============================================================

# Install curl for downloading uv
apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
export UV_PROJECT_ENVIRONMENT=/opt/venv
export PYTHONPATH=/app/src:/app/src/backend
cd /app

# Time uv sync
SYNC_START=$(date +%s.%N)
uv sync --frozen --no-install-project --group dev
SYNC_END=$(date +%s.%N)
UV_SYNC_ELAPSED=$(awk "BEGIN {printf \"%.2f\", $SYNC_END - $SYNC_START}")
echo "UV_SYNC_ELAPSED=$UV_SYNC_ELAPSED" > /app/src/backend/_step3_overhead.txt

# Time DB connection wait
DB_START=$(date +%s.%N)
echo "Waiting for PostgreSQL..."
DB_READY=0
for i in $(seq 1 30); do
    if /opt/venv/bin/python -c "import psycopg; psycopg.connect('$DATABASE_URL')" 2>/dev/null; then
        echo "Database ready"
        DB_READY=1
        break
    fi
    sleep 1
done
DB_END=$(date +%s.%N)
DB_ELAPSED=$(awk "BEGIN {printf \"%.2f\", $DB_END - $DB_START}")
echo "DB_WAIT_ELAPSED=$DB_ELAPSED" >> /app/src/backend/_step3_overhead.txt

if [ "$DB_READY" = "0" ]; then
    echo "ERROR: Database unavailable after 30s" >> /app/src/backend/_step3_overhead.txt
    exit 1
fi

# Time migrations
MIG_START=$(date +%s.%N)
echo "Running migrations..."
uv run python -c "from apps.core.utils.migrate_locked import main; import sys; sys.exit(main())"
MIG_END=$(date +%s.%N)
MIG_ELAPSED=$(awk "BEGIN {printf \"%.2f\", $MIG_END - $MIG_START}")
echo "MIGRATION_ELAPSED=$MIG_ELAPSED" >> /app/src/backend/_step3_overhead.txt

# Compile translations
echo "Compiling translations..."
uv run python src/backend/manage.py compilemessages

# Mark startup as complete
echo "STARTUP_COMPLETE at $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> /app/src/backend/_step3_overhead.txt

# Keep container alive for exec-based measurements
echo "Container ready, sleeping for exec..."
sleep 3600
