#!/bin/bash
# Entrypoint script for seed service
# Populates database with demo data

set -euo pipefail

# Source shared setup functions from entrypoint.sh (env check, volume perms, DB/Redis wait)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=entrypoint.sh
source "${SCRIPT_DIR}/entrypoint.sh"

check_env_file
fix_volume_permissions
wait_for_db
wait_for_redis

# Verify fixture JPEGs exist before running seed (Git ignores *.jpg fixtures)
FIXTURES_IMAGES_DIR=$(/opt/venv/bin/python -c "from apps.seed.paths import FIXTURES_IMAGES_DIR; print(FIXTURES_IMAGES_DIR)" 2>/dev/null || echo "")
if [ -z "$FIXTURES_IMAGES_DIR" ]; then
    echo "ERROR: Cannot resolve FIXTURES_IMAGES_DIR — ensure Django app paths are importable" >&2
    exit 1
fi
JPEG_COUNT=$(find "$FIXTURES_IMAGES_DIR" -maxdepth 1 -name '*.jpg' -o -name '*.jpeg' -o -name '*.png' | wc -l)
if [ "$JPEG_COUNT" -eq 0 ]; then
    echo "ERROR: No fixture JPEGs found in $FIXTURES_IMAGES_DIR" >&2
    echo "Recovery: run 'uv run python scripts/download_seed_photos.py --all' on the host," >&2
    echo "          rebuild the image, then re-run the seed service." >&2
    exit 1
fi
echo "Found $JPEG_COUNT fixture image(s) in $FIXTURES_IMAGES_DIR — proceeding with seed" >&2

exec /opt/venv/bin/python src/backend/manage.py seed --force \
    --users "${SEED_USERS:-10}" \
    --ads "${SEED_ADS:-600}"