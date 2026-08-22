#!/bin/bash
cd /app
export PYTHONPATH=/app/src:/app/src/backend
export VIRTUAL_ENV=/venv
export PATH=/venv/bin:$PATH
export DJANGO_SETTINGS_MODULE=config.settings.test

echo "=== CPU INFO ==="
nproc
echo ""

echo "=== PHASE 5: Non-Seed Suite with xdist ==="
START=$(date +%s)
/venv/bin/pytest --create-db -n auto --dist loadscope -m "not seed" -q --durations=20 2>&1 | tee /app/.cache/xdist_nonseed.txt | tail -40
END=$(date +%s)
ELAPSED=$((END - START))
echo ""
echo "=== XDIST NON-SEED SUITE ELAPSED: ${ELAPSED} seconds ==="
