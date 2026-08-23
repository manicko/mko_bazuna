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

# Compile translation files (.po -> .mo) so trans tags render during tests.
echo "Compiling translations..."
uv run python src/backend/manage.py compilemessages

# Run pytest with short traceback format and duration reporting for slowness visibility.
# PYTEST_OPTS lets callers (e.g. `make test-recreate`) override ALL pytest flags
# (single-token flags only; multi-token values like -m "not seed" are fragile here
# because this expansion is unquoted). For marker-based exclusion use
# PYTEST_SKIP_MARKERS instead (see below).
# PYTEST_SKIP_MARKERS="seed" appends -m "not (seed)" to pytest, excluding tests by
# marker. This is how the dev fast-gate (`make test`) skips the ~17-min nightly
# seed suite while `make test-all` runs everything. Complements PYTEST_OPTS.
# --reuse-db (default) skips test DB schema rebuild on subsequent runs; the DB
# container persists between runs via the named postgres_data volume. Use
# `make test-recreate` to force a fresh schema (--no-reuse-db --create-db), e.g.
# after migration changes or an interrupted (SIGKILL'd) run.
PYTEST_MARK_ARGS=()
if [ -n "${PYTEST_SKIP_MARKERS:-}" ]; then
    PYTEST_MARK_ARGS+=(-m "not (${PYTEST_SKIP_MARKERS})")
fi
echo "Running tests..."
uv run pytest ${PYTEST_OPTS:- --reuse-db --tb=short --durations=10} "${PYTEST_MARK_ARGS[@]}"
