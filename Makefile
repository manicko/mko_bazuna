# Makefile for Mko Bazuna Docker workflow

.PHONY: help up down reset build restart test test-all test-db test-down test-logs test-recreate test-clean-db \
          lint typecheck lint-templates shell makemigrations makemessages compilemessages migrate logs \
          backup restore prune-backups db-shell clean create-admin load-catalog seed

# ====================== Settings ======================

ENV_FILE := --env-file .env.docker
COMPOSE_FILES := $(ENV_FILE) -f docker-compose.yml -f docker-compose.dev.override.yml
COMPOSE_TEST := -f docker-compose.yml -f docker-compose.test.yml

# Isolated Compose project names so `make up` (dev) and `make test` can run
# simultaneously without colliding on service names, networks, or named volumes.
# Each project gets its own `postgres_data` and `uv_cache` volumes.
# Target-specific assignment (group syntax): the var is exported to the recipe shell.
up down reset build restart lint typecheck lint-templates shell makemigrations create-admin \
    load-catalog seed logs backup restore prune-backups clean db-shell migrate: \
    export COMPOSE_PROJECT_NAME = mko-bazuna-dev

test test-all test-db test-down test-logs test-recreate test-clean-db: \
    export COMPOSE_PROJECT_NAME = mko-bazuna-test

# ====================== Main Commands ======================

help:
	@echo "Mko Bazuna - Development Commands"
	@echo ""
	@echo "Usage: make <target>"
	@echo ""
	@echo "Main:"
	@echo "  up             Start dev environment (hot-reload)"
	@echo "  down           Stop and remove containers (preserves volumes/data)"
	@echo "  reset          Stop and remove containers AND named volumes (destroy seed data)"
	@echo "  restart        Restart web service"
	@echo "  build          Rebuild images without cache"
	@echo ""
	@echo "Test Environment:"
	@echo "  test           Run fast gate (skips nightly seed suite; reuses DB)"
	@echo "  test-all       Run complete suite (includes nightly seed suite; reuses DB)"
	@echo "  test-db        Start test PostgreSQL (long-running, enables reuse-db)"
	@echo "  test-down      Stop test environment (preserves DB; use 'down -v' to wipe)"
	@echo "  test-logs      Follow test environment logs"
	@echo "  test-clean-db  Drop stale test databases (test_mko_bazuna + gw* shards)"
	@echo "  test-recreate  Drop and rebuild test DB schema (--no-reuse-db)"
	@echo ""
	@echo "Code Quality:"
	@echo "  lint           Ruff"
	@echo "  typecheck      Basedpyright"
	@echo "  lint-templates Djlint"
	@echo ""
	@echo "Django:"
	@echo "  migrate        Apply migrations"
	@echo "  makemigrations Create migrations"
	@echo "  makemessages     Extract translatable strings into .po files"
	@echo "  compilemessages  Compile .po files into .mo files"
	@echo "  create-admin   Create admin user manually"
	@echo "  load-catalog   Load categories.yaml into DB (one-shot)"
	@echo "  seed           Re-run seed manually (dev: also auto-runs on `make up`)"
	@echo ""
	@echo "Consolidation:"
	@echo "  consolidate        Consolidate migrations (threshold: \$$(CONSOLIDATE_THRESHOLD))"
	@echo "  consolidate-force  Consolidate all migrations unconditionally"
	@echo ""
	@echo "Utilities:"
	@echo "  shell          Bash in web container"
	@echo "  db-shell       psql in database"
	@echo "  logs           Follow logs"
	@echo "  backup         Create database backup"
	@echo "  restore        Restore database (make restore BACKUP_FILE=...)"
	@echo "  prune-backups  Delete old backups (7+ days)"
	@echo ""
	@echo "Cleanup:"
	@echo "  down           Stop and remove containers (preserves volumes/data)"
	@echo "  reset          Stop and remove containers AND named volumes (destroy seed data)"
	@echo "  clean          Nuclear: remove containers, volumes, and local DB backups"

up:
	docker compose $(COMPOSE_FILES) rm -sf migrate load_catalog create_admin seed
	docker compose $(COMPOSE_FILES) up -d --wait

down:
	# Stop and remove containers (preserves named volumes: postgres_data, media_volume)
	docker compose $(COMPOSE_FILES) down

reset:
	# Stop and remove containers AND named volumes (destroys media_volume + postgres_data)
	docker compose $(COMPOSE_FILES) down -v --remove-orphans

build:
	docker compose $(COMPOSE_FILES) build --no-cache

restart:
	docker compose $(COMPOSE_FILES) restart web

# ====================== Code Quality ======================

# `test` runs the fast gate: excludes the nightly `seed` suite (~17-min bulk)
# via the entrypoint PYTEST_SKIP_MARKERS=seed env var. DB persists via --reuse-db.
test:
	docker compose $(COMPOSE_TEST) up -d db
	docker compose $(COMPOSE_TEST) run --rm --env PYTEST_SKIP_MARKERS=seed test

# Run the complete suite INCLUDING the nightly `seed` suite (~35min).
test-all:
	docker compose $(COMPOSE_TEST) up -d db
	docker compose $(COMPOSE_TEST) run --rm test

lint:
	docker compose $(COMPOSE_FILES) run --rm web uv run ruff check src/

typecheck:
	docker compose $(COMPOSE_FILES) run --rm web uv run basedpyright src/

lint-templates:
	docker compose $(COMPOSE_FILES) run --rm web uv run djlint src/backend/templates/

# ====================== Test Environment ======================

# Start only the long-running test PostgreSQL (port 5433). Idempotent.
test-db:
	docker compose $(COMPOSE_TEST) up -d db

# Stop and remove test containers/networks. Named volumes are preserved so the
# cached schema (--reuse-db) survives between sessions. Use `make test-down`
# followed by `docker compose $(COMPOSE_TEST) down -v` to wipe volumes.
test-down:
	docker compose $(COMPOSE_TEST) down

# Stream logs from the test project (db container + one-shot test runs).
test-logs:
	docker compose $(COMPOSE_TEST) logs -f

# Drop stale test databases (test_mko_bazuna + test_mko_bazuna_gw*) from the
# persistent test PostgreSQL volume. Run before test-recreate to handle stuck
# connections from crashed xdist workers. Uses psql \gexec — DROP DATABASE
# cannot run inside a DO $$ block on PostgreSQL 13+ (PG restriction:
# "DROP DATABASE cannot be executed from a function or procedure").
# Empirically verified: drops all 16 stale gw* databases, exit 0.
test-clean-db:
	docker compose $(COMPOSE_TEST) up -d db
	docker compose $(COMPOSE_TEST) exec -T db psql -U postgres -d postgres -c \
		"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname LIKE 'test_mko_bazuna%' AND pid <> pg_backend_pid();"
	docker compose $(COMPOSE_TEST) exec -T db psql -U postgres -d postgres -t -A -c \
		"SELECT format('DROP DATABASE IF EXISTS %I WITH (FORCE);', datname) FROM pg_database WHERE datname LIKE 'test_mko_bazuna%'" \
	| while IFS= read -r stmt; do docker compose $(COMPOSE_TEST) exec -T db psql -U postgres -d postgres -c "$$stmt"; done
	@echo "Stale test databases dropped."

# Force a fresh test DB schema by ignoring the --reuse-db cache. The entrypoint
# (entrypoint-test.sh) still runs uv sync + wait_for_db + migrate beforehand;
# only pytest's DB-caching flags are overridden via PYTEST_OPTS.
# Pre-start the DB (same as `make test`) so this target is self-contained.
test-recreate: test-clean-db
	# test-clean-db (pre-flight) drops stale test_mko_bazuna* + gw* databases,
	# handling stuck connections from crashed xdist workers before pytest runs.
	docker compose $(COMPOSE_TEST) up -d db
	docker compose $(COMPOSE_TEST) run --rm --env PYTEST_OPTS="--no-reuse-db --create-db --tb=short -n auto --dist loadgroup" test

# ====================== Django ======================

migrate:
	docker compose $(ENV_FILE) run --rm migrate

makemigrations:
	docker compose $(COMPOSE_FILES) run --rm web uv run python src/backend/manage.py makemigrations

makemessages:
	docker compose $(COMPOSE_FILES) run --rm web uv run python src/backend/manage.py makemessages -l ru -l bs -l en --no-location

compilemessages:
	docker compose $(COMPOSE_FILES) run --rm web uv run python src/backend/manage.py compilemessages \
		--ignore=.venv --ignore=.git --ignore=.kilo --ignore=__pycache__ --ignore='*.pyc' \
		--locale ru --locale bs --locale en

create-admin:
	docker compose $(COMPOSE_FILES) run --rm web uv run python src/backend/manage.py create_admin_user \
		--username "${ADMIN_USERNAME:-admin}" \
		--password "${ADMIN_PASSWORD}" \
		--telegram-id "${ADMIN_TELEGRAM_ID:--1}"

load-catalog:
	docker compose $(COMPOSE_FILES) run --rm load_catalog

# Run seed manually (dev: seed auto-runs on `make up`; this is for re-seeding)
seed:
	docker compose $(COMPOSE_FILES) run --rm seed

# ====================== Consolidation ======================

CONSOLIDATE_THRESHOLD ?= 8

consolidate:
	uv run python scripts/consolidate_migrations.py --threshold $(CONSOLIDATE_THRESHOLD)
	$(MAKE) makemigrations
	$(MAKE) migrate

consolidate-force:
	uv run python scripts/consolidate_migrations.py --force
	$(MAKE) makemigrations
	$(MAKE) migrate

# ====================== Utilities ======================

shell:
	docker compose $(COMPOSE_FILES) run --rm web /bin/bash

db-shell:
	docker compose $(COMPOSE_FILES) exec db psql -U $${POSTGRES_USER} -d $${POSTGRES_DB}

logs:
	docker compose $(COMPOSE_FILES) logs -f

# ====================== Backups ======================

BACKUPS_DIR := ./backups

backup:
	@mkdir -p $(BACKUPS_DIR)
	@TIMESTAMP=$$(date +%Y%m%d_%H%M%S) && \
		docker compose $(ENV_FILE) -f docker-compose.yml exec -T db \
			pg_dump -U $${POSTGRES_USER} -d $${POSTGRES_DB} -F c \
			> $(BACKUPS_DIR)/dump_$${TIMESTAMP}.dump && \
		echo "✓ Backup created: $(BACKUPS_DIR)/dump_$${TIMESTAMP}.dump"
	@$(MAKE) prune-backups

restore:
	@if [ -z "$(BACKUP_FILE)" ]; then \
		echo "Error: BACKUP_FILE not specified"; \
		echo "Example: make restore BACKUP_FILE=./backups/dump_20250719_143022.dump"; \
		exit 1; \
	fi
	@if [ ! -f "$(BACKUP_FILE)" ]; then \
		echo "Error: file $(BACKUP_FILE) not found"; \
		exit 1; \
	fi
	docker compose $(ENV_FILE) -f docker-compose.yml exec -T db \
		pg_restore -U $${POSTGRES_USER} -d $${POSTGRES_DB} --clean --if-exists $(BACKUP_FILE)
	@echo "✓ Restore completed from $(BACKUP_FILE)"

prune-backups:
	@find $(BACKUPS_DIR) -name "dump_*.dump" -mtime +7 -delete -print
	@echo "✓ Old backups (older than 7 days) pruned"

# ====================== Cleanup ======================

# Nuclear: remove containers, volumes (incl. postgres_data, media_volume), and local DB backups
clean:
	docker compose $(COMPOSE_FILES) down -v --remove-orphans
	rm -rf $(BACKUPS_DIR)/*.dump
