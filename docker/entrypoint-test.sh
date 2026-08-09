#!/bin/bash
# Test entrypoint for Mko Bazuna
# Runs migrations then pytest in ephemeral PostgreSQL environment

set -e

# Enable dev dependencies (pytest, pytest-django, etc.) for testing.
# default-groups = [] in pyproject.toml keeps dev tools out of the production
# image. The --group dev flag overrides this for the test environment only.
# UV_NO_INSTALL_PROJECT=1 is set in the Dockerfile runtime stage, but it prevents
# uv sync from installing any packages. Unset it here; --no-install-project CLI
# flag still prevents the project package itself from being installed.
unset UV_NO_INSTALL_PROJECT
uv sync --frozen --no-install-project --group dev

# Wait for database to be ready
echo "Waiting for PostgreSQL..."
for i in $(seq 1 30); do
    if uv run python -c "import psycopg; psycopg.connect('$DATABASE_URL')" 2>/dev/null; then
        echo "Database ready"
        break
    fi
    sleep 1
done

if [ "$i" = "30" ]; then
    echo "ERROR: Database unavailable after 30s" >&2
    exit 1
fi

# Run migrations (idempotent via advisory lock)
echo "Running migrations..."
uv run python -c "from apps.core.utils.migrate_locked import main; import sys; sys.exit(main())"

# Run pytest with short traceback format.
# --reuse-db caches the test_mko_bazuna schema between runs for fast iteration;
# --create-db makes Django recreate the schema when it diverges from migrations.
# PYTEST_OPTS lets callers (e.g. `make test-recreate`) override the flags.
echo "Running tests..."
uv run pytest ${PYTEST_OPTS:---reuse-db --create-db --tb=short}