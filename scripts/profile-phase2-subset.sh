#!/bin/bash
cd /app
export PYTHONPATH=/app/src:/app/src/backend
export VIRTUAL_ENV=/venv
export PATH=/venv/bin:$PATH
export DJANGO_SETTINGS_MODULE=config.settings.test

echo "=== Running small subset: unit tests only ==="
START=$(date +%s)
/venv/bin/pytest --create-db --durations=20 -m "unit and not seed" -q 2>&1 | tee /app/.cache/unit_tests_output.txt
END=$(date +%s)
echo "Unit tests elapsed: $((END - START)) seconds"
echo ""
echo "=== Summary lines ==="
grep -E "passed|failed|error|PASSED|FAILED|ERROR" /app/.cache/unit_tests_output.txt | tail -5
