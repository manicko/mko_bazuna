#!/bin/bash
# Entrypoint script for load_catalog service
# Loads categories.yaml into the database after migrations complete

set -euo pipefail

# Source shared setup functions from entrypoint.sh (env check, volume perms, DB/Redis wait)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=entrypoint.sh
source "${SCRIPT_DIR}/entrypoint.sh"

check_env_file
fix_volume_permissions
wait_for_db
wait_for_redis

exec uv run python src/backend/manage.py load_catalog --no-rewrite
