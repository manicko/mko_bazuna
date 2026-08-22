#!/bin/bash
cd /app
export PYTHONPATH=/app/src:/app/src/backend
export VIRTUAL_ENV=/venv
export PATH=/venv/bin:$PATH
export DJANGO_SETTINGS_MODULE=config.settings.test

echo "=== CONCURRENT (BOT) TESTS PROFILE ==="
START=$(date +%s)
/venv/bin/pytest --create-db --durations=20 -m "concurrent" -q 2>&1 | tee /app/.cache/concurrent_tests.txt | tail -30
END=$(date +%s)
echo ""
echo "=== CONCURRENT TESTS ELAPSED: $((END - START)) seconds ==="
