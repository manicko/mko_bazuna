#!/bin/bash
# Scheduler entrypoint - runs management commands in hourly loop

set -e

# Fail fast if .env file is missing
check_env_file() {
    if [ -z "$SKIP_ENV_CHECK" ] && [ ! -f "/app/src/.env" ]; then
        if [ "$DJANGO_SETTINGS_MODULE" != "config.settings.test" ]; then
            echo "ERROR: /app/src/.env file not found. Copy .env.docker.example to .env.docker and configure values." >&2
            exit 1
        fi
    fi
}

# Execute logic
check_env_file

echo "Scheduler starting (hourly + daily loop)..."

exec /opt/venv/bin/python -c "
import time
import subprocess
import sys
import datetime

# Phase 4 hourly sweeps + Phase 2 purges (run every hour)
hourly_commands = [
    'archive_sweep',
    'delete_sweep',
    'consent_hard_delete',
    'sweep_drafts',
    'cleanup_login_tokens',
    'purge_failed_ads',
    'purge_rejected_ads',
    'purge_deleted_ads',
]
# Daily at 08:00 UTC (phase-02 spec: docs/97-plans/phase-02-detailed-plan-1.md:317).
# add future daily jobs here, e.g. 'rollup_daily_metrics'
daily_commands = ['send_alerts']
daily_hour_utc = 8
last_daily = None

while True:
    try:
        # Note: jobs are gated by advisory locks in their implementations
        for cmd in hourly_commands:
            subprocess.run([sys.executable, 'src/backend/manage.py', cmd], check=False)
    except Exception:
        pass

    # Daily jobs: once per calendar day, at the first hourly tick >= 08:00 UTC.
    # The advisory lock inside each command guarantees idempotency across
    # container restarts (pg_advisory_xact_lock prevents concurrent runs).
    now = datetime.datetime.now(datetime.timezone.utc)
    if last_daily is None or now.date() != last_daily:
        if now.hour >= daily_hour_utc:
            try:
                for cmd in daily_commands:
                    subprocess.run([sys.executable, 'src/backend/manage.py', cmd], check=False)
            except Exception:
                pass
            last_daily = now.date()

    time.sleep(3600)
"
