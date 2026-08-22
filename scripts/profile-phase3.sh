#!/bin/bash
cd /app
export PYTHONPATH=/app/src:/app/src/backend
export VIRTUAL_ENV=/venv
export PATH=/venv/bin:$PATH
export DJANGO_SETTINGS_MODULE=config.settings.test

echo "=== PHASE 3: Seed Suite (--create-db --durations=20 -m seed) ==="
START=$(date +%s)
/venv/bin/pytest --create-db --durations=20 -m seed -q 2>&1 | tee /app/.cache/seed_full.txt
END=$(date +%s)
ELAPSED=$((END - START))
echo ""
echo "=== SEED SUITE ELAPSED: ${ELAPSED} seconds ==="
