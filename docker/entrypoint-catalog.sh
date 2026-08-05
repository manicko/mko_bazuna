#!/bin/bash
# Entrypoint script for load_catalog service
# Loads categories.yaml into the database after migrations complete

set -e

exec uv run python src/backend/manage.py load_catalog --no-rewrite
