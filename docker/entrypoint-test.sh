#!/bin/bash
# Test entrypoint for Mko Bazuna
# Runs pytest. The base ENTRYPOINT (entrypoint.sh) already waits for the DB,
# runs migrations, and compiles translations, so this script only syncs deps and
# launches the test suite.

set -e

# Enable dev dependencies (pytest, pytest-django, etc.) for testing.
# default-groups = [] in pyproject.toml keeps dev tools out of the production
# image. The --group dev flag overrides this for the test environment only.
# UV_NO_INSTALL_PROJECT=1 is set in the Dockerfile runtime stage, but it prevents
# uv sync from installing any packages. Unset it here; --no-install-project CLI
# flag still prevents the project package itself from being installed.
unset UV_NO_INSTALL_PROJECT
uv sync --frozen --no-install-project --group dev
# Install extracted DDL + seed data (idempotent). Runs on mko_bazuna;
# test_mko_bazuna is handled by the autouse fixture in conftest.py (T4e).
uv run python src/backend/manage.py load_exchange_rates || true
uv run python src/backend/manage.py setup_search_triggers || true
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
# xdist parallel execution: matches CI configuration (see .github/workflows/ci.yml:91).
# -n auto: use all available CPU cores; --dist loadgroup: distribute by xdist_group()
# markers so bot tests that share FSM state run on the same worker.
uv run pytest ${PYTEST_OPTS:- --reuse-db --tb=short --durations=10 -n auto --dist loadgroup} "${PYTEST_MARK_ARGS[@]}"
