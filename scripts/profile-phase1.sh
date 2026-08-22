#!/bin/bash
cd /app
export PYTHONPATH=/app/src:/app/src/backend
export VIRTUAL_ENV=/venv
export PATH=/venv/bin:$PATH
export DJANGO_SETTINGS_MODULE=config.settings.test

echo "=== TOTAL COLLECTION ==="
/venv/bin/pytest --collect-only -q 2>&1 | tee /app/.cache/collect_total.txt | tail -3
TOTAL=$(grep -oP '^\S+.*: \K\d+' /app/.cache/collect_total.txt | awk '{s+=$1} END {print s}')
echo "Total tests (summed from file counts): $TOTAL"

echo ""
echo "=== MARKER COUNTS ==="
for marker in seed unit integration settings concurrent slow; do
    # Run collection for this marker, capture file:count lines, sum them
    /venv/bin/pytest --collect-only -q -m "$marker" 2>/dev/null | tee /app/.cache/collect_${marker}.txt > /dev/null
    # Count file:count format and sum
    cnt=$(grep -oP '^\S+.*: \K\d+' /app/.cache/collect_${marker}.txt 2>/dev/null | awk '{s+=$1} END {print s}')
    if [ -z "$cnt" ]; then
        cnt=0
    fi
    echo "  $marker: $cnt tests"
    # Also show the raw summary line if present
    grep -i "test.*collected" /app/.cache/collect_${marker}.txt 2>/dev/null || true
done
