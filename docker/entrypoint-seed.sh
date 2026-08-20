#!/bin/bash
# Entrypoint script for seed service
# Populates database with demo data

set -e

exec uv run python src/backend/manage.py seed --force \
    --users "${SEED_USERS:-10}" \
    --ads "${SEED_ADS:-600}"