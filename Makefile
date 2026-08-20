# Makefile for Mko Bazuna Docker workflow

.PHONY: help up down build restart test test-db test-down test-logs test-recreate \
        lint typecheck shell migrate makemigrations logs \
        backup restore prune-backups db-shell clean create-admin load-catalog seed

# ====================== Settings ======================

ENV_FILE := --env-file .env.docker
COMPOSE_FILES := $(ENV_FILE) -f docker-compose.yml -f docker-compose.dev.override.yml
COMPOSE_TEST := -f docker-compose.yml -f docker-compose.test.yml

# Isolated Compose project names so `make up` (dev) and `make test` can run
# simultaneously without colliding on service names, networks, or named volumes.
# Each project gets its own `postgres_data` and `uv_cache` volumes.
# Target-specific assignment (group syntax): the var is exported to the recipe shell.
up down build restart lint typecheck shell makemigrations create-admin \
    load-catalog seed logs backup restore prune-backups clean db-shell migrate: \
    export COMPOSE_PROJECT_NAME = mko-bazuna-dev

test test-db test-down test-logs test-recreate: \
    export COMPOSE_PROJECT_NAME = mko-bazuna-test

# ====================== Main Commands ======================

help:
	@echo "Mko Bazuna - Development Commands"
	@echo ""
	@echo "Usage: make <target>"
	@echo ""
	@echo "Main:"
	@echo "  up             Start dev environment (hot-reload)"
	@echo "  down           Stop and remove containers"
	@echo "  restart        Restart web service"
	@echo "  build          Rebuild images without cache"
	@echo ""
	@echo "Test Environment:"
	@echo "  test           Run tests (auto-starts test DB on :5433, reuses DB via --reuse-db)"
	@echo "  test-db        Start test PostgreSQL (long-running, enables reuse-db)"
	@echo "  test-down      Stop test environment (preserves DB; use 'down -v' to wipe)"
	@echo "  test-logs      Follow test environment logs"
	@echo "  test-recreate  Drop and rebuild test DB schema (--no-reuse-db)"
	@echo ""
	@echo "Code Quality:"
	@echo "  lint           Ruff"
	@echo "  typecheck      Basedpyright"
	@echo ""
	@echo "Django:"
	@echo "  migrate        Apply migrations"
	@echo "  makemigrations Create migrations"
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

up:
	docker compose $(COMPOSE_FILES) up -d

down:
	docker compose $(COMPOSE_FILES) down

build:
	docker compose $(COMPOSE_FILES) build --no-cache

restart:
	docker compose $(COMPOSE_FILES) restart web

# ====================== Code Quality ======================

# `test` ensures the long-running test DB is up (idempotent) before the one-shot
# test container runs; the DB persists so --reuse-db survives across runs.
test:
	docker compose $(COMPOSE_TEST) up -d db
	docker compose $(COMPOSE_TEST) run --rm test

lint:
	docker compose $(COMPOSE_FILES) run --rm web uv run ruff check src/

typecheck:
	docker compose $(COMPOSE_FILES) run --rm web uv run basedpyright src/

# ====================== Test Environment ======================

# Start only the long-running test PostgreSQL (port 5433). Idempotent.
test-db:
	docker compose $(COMPOSE_TEST) up -d db

# Stop and remove test containers/networks. Named volumes are preserved so the
# cached schema (--reuse-db) survives between sessions. Use `make test-purge`
# style `down -v` to wipe: docker compose $(COMPOSE_TEST) down -v
test-down:
	docker compose $(COMPOSE_TEST) down

# Stream logs from the test project (db container + one-shot test runs).
test-logs:
	docker compose $(COMPOSE_TEST) logs -f

# Force a fresh test DB schema by ignoring the --reuse-db cache. The entrypoint
# (entrypoint-test.sh) still runs uv sync + wait_for_db + migrate beforehand;
# only pytest's DB-caching flags are overridden via PYTEST_OPTS.
test-recreate:
	docker compose $(COMPOSE_TEST) run --rm --env PYTEST_OPTS="--no-reuse-db --create-db --tb=short" test

# ====================== Django ======================

migrate:
	docker compose $(ENV_FILE) run --rm migrate

makemigrations:
	docker compose $(COMPOSE_FILES) run --rm web uv run python src/backend/manage.py makemigrations

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

clean:
	docker compose $(COMPOSE_FILES) down -v --remove-orphans
	rm -rf $(BACKUPS_DIR)/*.dump
