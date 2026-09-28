#!/bin/bash
# Test entrypoint for Mko Bazuna.
#
# Runs as the `test` service `command` (docker-compose.test.yml), so the base
# image ENTRYPOINT (docker/entrypoint.sh) runs first and execs this script. Its
# steps are: check_env_file -> fix_volume_permissions -> wait_for_db ->
# wait_for_redis -> compile_messages -> deploy_check -> exec "$@".
# It runs no migrations and loads no reference data. This script therefore only
# installs dev dependencies and then launches pytest.
#
# Test-database setup is NOT done here. config/settings/test.py hard-pins
# DATABASES["default"]["NAME"] = "mko_bazuna", so any manage.py command run from
# this script would build the whole schema by syncdb into the non-test database,
# which nothing reads. pytest-django provisions test_mko_bazuna instead, and the
# session-autouse fixture _restore_test_schema_post_db_setup in
# src/backend/conftest.py runs `migrate --run-syncdb`, `load_exchange_rates` and
# `setup_search_triggers` in-process against it, under
# AdvisoryLockId.TEST_SCHEMA_SETUP (111). Do not reintroduce
# bootstrap_reference_data here: its migrate_locked subprocesses connect to
# mko_bazuna, and its `|| true` masked every real DDL failure.

set -e

# Enable dev dependencies (pytest, pytest-django, etc.) for testing.
# default-groups = [] in pyproject.toml keeps dev tools out of the production
# image. The --group dev flag overrides this for the test environment only.
# UV_NO_INSTALL_PROJECT=1 is set in the Dockerfile runtime stage, but it prevents
# uv sync from installing any packages. Unset it here; --no-install-project CLI
# flag still prevents the project package itself from being installed.
unset UV_NO_INSTALL_PROJECT
uv sync --frozen --no-install-project --group dev
# Run pytest with short traceback format and duration reporting for slowness
# visibility. The test database and its reference data (search triggers,
# exchange rates) come from pytest-django plus the session-autouse
# _restore_test_schema_post_db_setup fixture in src/backend/conftest.py; this
# script performs no database setup of its own. That fixture calls
# `setup_search_triggers` without `--backfill`, whereas migrate_locked passes
# it: intentional, because the trigger fires on every insert and a test database
# has no pre-existing rows whose search vectors would need backfilling.
# PYTEST_OPTS lets callers (e.g. `make test-recreate`) override ALL pytest flags
# (single-token flags only; multi-token values like -m "not seed" are fragile here
# because this expansion is unquoted). For marker-based exclusion use
# PYTEST_SKIP_MARKERS instead (see below).
# PYTEST_SKIP_MARKERS="seed" appends -m "not (seed)" to pytest, excluding tests by
# marker. This is how the dev fast-gate (`make test`) skips the ~17-min nightly
# seed suite while `make test-all` runs everything. Complements PYTEST_OPTS.
# --reuse-db (default) skips test DB schema rebuild on subsequent runs; the DB
# container persists between runs via the named postgres_data volume. Use
# `make test-recreate` to force a fresh schema (--create-db), e.g. after
# migration changes or an interrupted (SIGKILL'd) run.
PYTEST_MARK_ARGS=()
if [ -n "${PYTEST_SKIP_MARKERS:-}" ]; then
    PYTEST_MARK_ARGS+=(-m "not (${PYTEST_SKIP_MARKERS})")
fi
echo "Running tests..."
# xdist parallel execution: matches CI configuration (see .github/workflows/ci.yml:91).
# -n auto: use all available CPU cores; --dist loadgroup: distribute by xdist_group()
# markers so bot tests that share FSM state run on the same worker.
uv run pytest ${PYTEST_OPTS:- --reuse-db --tb=short --durations=10 -n auto --maxprocesses=4 --dist loadgroup} "${PYTEST_MARK_ARGS[@]}"
