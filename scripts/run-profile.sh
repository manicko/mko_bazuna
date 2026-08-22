#!/bin/bash
cd /app
export PYTHONPATH=/app/src:/app/src/backend
export VIRTUAL_ENV=/venv
export PATH=/venv/bin:$PATH

echo "=== TOTAL COLLECTION ==="
START=$(date +%s.%N)
/venv/bin/pytest --create-db --collect-only -q 2>&1 | tail -10
END=$(date +%s.%N)
echo "Collection time: $(echo "$END - $START" | bc) seconds"

echo ""
echo "=== MARKER COUNTS ==="
for marker in seed unit integration settings concurrent slow; do
    count=$(/venv/bin/pytest --collect-only -q -m "$marker" 2>/dev/null | grep -c "::")
    echo "  $marker: $count tests"
done

echo ""
echo "=== MARKER NAMES ==="
for marker in seed unit integration settings concurrent slow; do
    echo "--- $marker ---"
    /venv/bin/pytest --collect-only -q -m "$marker" 2>&1 | tail -3
done
