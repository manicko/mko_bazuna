#!/bin/bash
# Scheduler entrypoint - runs management commands in hourly loop

set -e

# Fail fast if .env file is missing
check_env_file() {
    if [ -z "$SKIP_ENV_CHECK" ] && [ ! -f "/app/src/.env" ]; then
        if [ "$DJANGO_SETTINGS_MODULE" != "config.settings.test" ]; then
            echo "ERROR: /app/src/.env file not found. Copy .env.dev.example to .env.dev and configure values." >&2
            exit 1
        fi
    fi
}

# Execute logic
check_env_file

echo "Scheduler starting (hourly + daily loop)..."

exec /opt/venv/bin/python -m apps.core.utils.scheduler
