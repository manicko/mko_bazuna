#!/usr/bin/env bash
# Scheduler container healthcheck: process liveness + readiness marker.
#
# Replaces the previous PID-only check (kill -0 1) with a two-stage test:
#   (a) PID 1 alive        — basic liveness
#   (b) Marker file exists — readiness (scheduler wrote the marker after cycle)
#   (c) Optional freshness — detects retry-loop / stuck scheduler
set -euo pipefail

# (a) Process liveness (PID 1 alive)
if ! kill -0 1 2>/dev/null; then
    echo "scheduler: PID 1 not alive"
    exit 1
fi

# (b) Readiness: the scheduler reached the hourly loop (wrote the marker)
marker="${SCHEDULER_LIVENESS_FILE:-/tmp/mko_bazuna_scheduler_alive}"
if [ ! -f "$marker" ]; then
    echo "scheduler: liveness marker missing (scheduler not ready)"
    exit 1
fi

# (c) Freshness (optional): detect retry-loop / stuck scheduler
stale="${SCHEDULER_HEALTH_STALE_SECONDS:-0}"
if [ "$stale" -gt 0 ] 2>/dev/null; then
    now="$(date +%s)"
    mtime="$(stat -c %Y "$marker" 2>/dev/null || stat -f %m "$marker" 2>/dev/null || echo 0)"
    if [ "$mtime" -eq 0 ] || [ $((now - mtime)) -gt "$stale" ]; then
        echo "scheduler: liveness marker stale (last update > ${stale}s ago)"
        exit 1
    fi
fi

echo "scheduler: healthy (process + marker OK)"
exit 0
