#!/bin/bash

# ============================================================
# Step 3 Rerun Script - Verbose mode (no -q) for summary lines
# Reuses existing venv if present
# ============================================================

export PATH="/root/.local/bin:$PATH"
export UV_PROJECT_ENVIRONMENT=/opt/venv
export PYTHONPATH=/app/src:/app/src/backend
cd /app

# Check if venv already exists (from previous container run)
if [ -f /opt/venv/bin/python ]; then
    echo "Venv already exists, skipping uv sync"
else
    echo "Venv not found, installing uv and syncing..."
    apt-get update && apt-get install -y --no-install-recommends curl ca-certificates coreutils gettext && rm -rf /var/lib/apt/lists/*
    curl -LsSf https://astral.sh/uv/install.sh | sh
    uv sync --frozen --no-install-project --group dev
fi

set -e

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

if [ "$DB_READY" = "0" ]; then
    echo "ERROR: Database unavailable after 30s"
    exit 1
fi

# Run migrations
echo "Running migrations..."
uv run python -c "from apps.core.utils.migrate_locked import main; import sys; sys.exit(main())"

# Compile translations
echo "Compiling translations..."
uv run python src/backend/manage.py compilemessages

# ===== Measurement Phase (verbose, no -q) =====
set +e

cd /app/src/backend

# --- Measurement 1: Fast-gate (NO -q for summary line) ---
echo "=== MEASUREMENT 1: Fast-gate (verbose) ==="
uv run pytest -n auto --dist loadgroup --reuse-db -m "not seed" --tb=no --durations=20 -p no:warnings > /app/src/backend/_step3_fg.txt 2>&1
echo "EXIT=$?" >> /app/src/backend/_step3_fg.txt
echo "=== MEASUREMENT 1 DONE ==="

# --- Measurement 2: Seed (NO -q for summary line) ---
echo "=== MEASUREMENT 2: Seed (verbose) ==="
uv run pytest -m seed --reuse-db --tb=line --durations=20 > /app/src/backend/_step3_seed.txt 2>&1
echo "EXIT=$?" >> /app/src/backend/_step3_seed.txt
echo "=== MEASUREMENT 2 DONE ==="

# --- Measurement 3: Settings (already verbose) ---
echo "=== MEASUREMENT 3: Settings ==="
uv run pytest -m settings --reuse-db --tb=line -v > /app/src/backend/_step3_sett.txt 2>&1
echo "EXIT=$?" >> /app/src/backend/_step3_sett.txt
echo "=== MEASUREMENT 3 DONE ==="

# --- Measurement 4: Concurrent (NO -q for summary line) ---
echo "=== MEASUREMENT 4: Concurrent (verbose) ==="
uv run pytest -m concurrent --reuse-db --tb=line --durations=5 > /app/src/backend/_step3_conc.txt 2>&1
echo "EXIT=$?" >> /app/src/backend/_step3_conc.txt
echo "=== MEASUREMENT 4 DONE ==="

# --- Measurement 5: Unit serial (NO -q for summary line) ---
echo "=== MEASUREMENT 5: Unit serial (verbose) ==="
uv run pytest -m "unit and not seed" --reuse-db --tb=line --durations=10 > /app/src/backend/_step3_unit.txt 2>&1
echo "EXIT=$?" >> /app/src/backend/_step3_unit.txt
echo "=== MEASUREMENT 5 DONE ==="

echo "ALL_MEASUREMENTS_COMPLETE_V2" > /app/src/backend/_step3_done.txt
