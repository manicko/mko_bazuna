#!/bin/bash
cd /app
export PYTHONPATH=/app/src:/app/src/backend
export VIRTUAL_ENV=/venv
export PATH=/venv/bin:$PATH
export DJANGO_SETTINGS_MODULE=config.settings.test

echo "=== PHASE 2: Non-Seed Suite (serial, --create-db) ==="
START=$(date +%s)
/venv/bin/pytest --create-db --durations=20 -m "not seed" -q 2>&1 | tee /app/.cache/nonseed_full.txt
END=$(date +%s)
ELAPSED=$((END - START))
echo ""
echo "=== NON-SEED SUITE ELAPSED: ${ELAPSED} seconds ==="
