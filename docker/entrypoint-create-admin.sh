#!/bin/bash
# Entrypoint script for create_admin service
# Skips admin creation if ADMIN_PASSWORD is not set (empty string)

set -euo pipefail

# Source shared setup functions from entrypoint.sh (env check, volume perms, DB/Redis wait)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=entrypoint.sh
source "${SCRIPT_DIR}/entrypoint.sh"

check_env_file
fix_volume_permissions
wait_for_db
wait_for_redis

# Check if ADMIN_PASSWORD is set and non-empty
if [ -z "${ADMIN_PASSWORD}" ]; then
    echo "ADMIN_PASSWORD not set, skipping admin user creation"
    exit 0
fi

# Run the create_admin_user command. The admin password is read from
# ADMIN_PASSWORD in the environment by the command itself, so it is not placed on
# the command line. This does not change the credential's exposure: it is already
# in the container's environment via env_file, so `docker inspect` already shows
# it in cleartext (VAL-002).
exec /opt/venv/bin/python src/backend/manage.py create_admin_user \
    --username "${ADMIN_USERNAME:-admin}" \
    --telegram-id "${ADMIN_TELEGRAM_ID:--1}"

