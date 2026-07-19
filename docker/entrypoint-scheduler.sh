#!/bin/bash
# Scheduler entrypoint - runs management commands in hourly loop

set -e

# Fail fast if .env file is missing
check_env_file() {
    if [ -z "$SKIP_ENV_CHECK" ] && [ ! -f "/app/.env" ]; then
        if [ "$DJANGO_SETTINGS_MODULE" != "config.settings.test" ]; then
            echo "ERROR: /app/.env file not found. Copy .env.example to .env and configure values." >&2
            exit 1
        fi
    fi
}

# Execute logic
check_env_file

echo "Scheduler starting (hourly loop)..."

exec uv run python -c "
import time
import subprocess
import sys

while True:
    try:
        # Phase 4 jobs: archive, delete, consent hard-delete, sweep drafts, cleanup tokens
        # Phase 2 jobs: purge failed, purge rejected
        # Note: jobs are gated by advisory lock in their implementations
        subprocess.run([sys.executable, 'src/backend/manage.py', 'archive_sweep'], check=False)
        subprocess.run([sys.executable, 'src/backend/manage.py', 'delete_sweep'], check=False)
        subprocess.run([sys.executable, 'src/backend/manage.py', 'consent_hard_delete'], check=False)
        subprocess.run([sys.executable, 'src/backend/manage.py', 'sweep_drafts'], check=False)
        subprocess.run([sys.executable, 'src/backend/manage.py', 'cleanup_login_tokens'], check=False)
        subprocess.run([sys.executable, 'src/backend/manage.py', 'purge_failed_ads'], check=False)
        subprocess.run([sys.executable, 'src/backend/manage.py', 'purge_rejected_ads'], check=False)
    except Exception:
        pass
    time.sleep(3600)
"
