#!/bin/bash
cd /app
export PYTHONPATH=/app/src:/app/src/backend
export VIRTUAL_ENV=/venv
export PATH=/venv/bin:$PATH
export DJANGO_SETTINGS_MODULE=config.settings.test

for marker in unit integration settings concurrent slow; do
    echo "=== MARKER: $marker ==="
    START=$(date +%s)
    /venv/bin/pytest --collect-only -q -m "$marker" 2>&1 | tee "/app/.cache/collect_${marker}.txt" > /dev/null
    END=$(date +%s)
    ELAPSED=$((END - START))
    cnt=$(grep -oP '^\S+.*: \K\d+' "/app/.cache/collect_${marker}.txt" 2>/dev/null | awk '{s+=$1} END {print s}')
    if [ -z "$cnt" ]; then
        cnt=0
    fi
    echo "  $marker: $cnt tests in ${ELAPSED}s"
    echo ""
done

echo "=== DONE ==="
