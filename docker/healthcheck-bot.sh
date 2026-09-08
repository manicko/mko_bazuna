#!/usr/bin/env bash
# Bot container healthcheck: process liveness + readiness marker.
#
# Replaces the previous PID-only check (kill -0 1) with a two-stage test:
#   (a) PID 1 alive        — basic liveness
#   (b) Marker file exists — readiness (bot reached the polling loop)
#   (c) Optional freshness — detects retry-loop / stuck polling
set -euo pipefail

# (a) Process liveness (PID 1 alive)
if ! kill -0 1 2>/dev/null; then
    echo "bot: PID 1 not alive"
    exit 1
fi

# (b) Readiness: the bot reached the polling loop (startup hook wrote the marker)
marker="${BOT_LIVENESS_FILE:-/tmp/mko_bazuna_bot_alive}"
if [ ! -f "$marker" ]; then
    echo "bot: liveness marker missing (bot not ready)"
    exit 1
fi

# (c) Freshness (optional): detect retry-loop / stuck polling
stale="${BOT_HEALTH_STALE_SECONDS:-0}"
if [ "$stale" -gt 0 ] 2>/dev/null; then
    now="$(date +%s)"
    mtime="$(stat -c %Y "$marker" 2>/dev/null || stat -f %m "$marker" 2>/dev/null || echo 0)"
    if [ "$mtime" -eq 0 ] || [ $((now - mtime)) -gt "$stale" ]; then
        echo "bot: liveness marker stale (last update > ${stale}s ago)"
        exit 1
    fi
fi

echo "bot: healthy (process + marker OK)"
exit 0
