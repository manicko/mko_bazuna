# Makefile for Mko Bazuna Docker workflow

.PHONY: help up down reset build restart test test-all test-db test-down test-logs test-recreate test-clean-db \
          lint format typecheck lock-check lint-templates shell makemigrations makemessages compilemessages migrate logs \
           backup restore prune-backups db-shell clean fullclean create-admin load-catalog seed restore-test load profile

# ====================== Settings ======================

ENV_FILE := --env-file .env.dev
COMPOSE_FILES := $(ENV_FILE) -f docker-compose.yml -f docker-compose.dev.override.yml
COMPOSE_TEST := --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml
ENV_PROD := --env-file .env.prod
COMPOSE_PROD := $(ENV_PROD) -f docker-compose.yml -f docker-compose.prod.yml

# App image reference (GHCR SHA-tagged) for the migrate --plan --check step in
# restore-test. Empty by default — manual restore-test runs skip the migrate
# check. CI provides the SHA-tagged image via APP_IMAGE.
APP_IMAGE ?=

# Isolated Compose project names so `make up` (dev) and `make test` can run
# simultaneously without colliding on service names, networks, or named volumes.
# Each project gets its own `postgres_data` and `uv_cache` volumes.
# Target-specific assignment (group syntax): the var is exported to the recipe shell.
up down reset build restart lint format typecheck lint-templates shell makemigrations create-admin \
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
	@echo "  build          Rebuild Docker images"
	@echo ""
	@echo "Test Environment:"
	@echo "  test           Run fast gate (skips nightly seed suite; reuses DB)"
	@echo "  test-all       Run complete suite (includes nightly seed suite; reuses DB)"
	@echo "  test-db        Start test PostgreSQL (long-running, enables reuse-db)"
	@echo "  test-down      Stop test environment (preserves DB; use 'down -v' to wipe)"
	@echo "  test-logs      Follow test environment logs"
	@echo "  test-clean-db  Drop stale test databases (test_mko_bazuna + gw* shards)"
	@echo "  test-recreate  Drop and rebuild test DB schema (--create-db)"
	@echo ""
	@echo "Code Quality:"
	@echo "  lint           Ruff"
	@echo "  format         Auto-fix lint issues (including import sorting)"
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
	@echo "Performance:"
	@echo "  load           Run locust load tests against dev server (make up first)"
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
	@echo "  restore-test   Restore backup into an isolated DB (make restore-test BACKUP_FILE=...)"
	@echo "  prune-backups  Delete old backups (7+ days)"
	@echo ""
	@echo "Cleanup:"
	@echo "  down           Stop and remove containers (preserves volumes/data)"
	@echo "  reset          Stop and remove containers AND named volumes (destroy seed data)"
	@echo "  clean          Nuclear: remove containers, volumes, and local DB backups"
	@echo "  fullclean      Full reset: stop dev+test, wipe volumes, prune images/networks/build cache"

up:
	docker compose $(COMPOSE_FILES) rm -sf migrate load_catalog create_admin seed
	docker compose $(COMPOSE_FILES) up -d

down:
	# Stop and remove containers (preserves named volumes: postgres_data, media_volume)
	docker compose $(COMPOSE_FILES) down

reset:
	# Stop and remove containers AND named volumes (destroys media_volume + postgres_data)
	docker compose $(COMPOSE_FILES) down -v --remove-orphans

build:
	docker compose $(COMPOSE_FILES) build

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

format:
	docker compose $(COMPOSE_FILES) run --rm web uv run ruff check --fix src/

typecheck:
	docker compose $(COMPOSE_FILES) run --rm web uv run basedpyright src/

lock-check: ## Check uv.lock is in sync with pyproject.toml
	uv lock --check

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
	# --maxprocesses=4 caps worker forks to prevent ENOMEM on memory-constrained
	# local Docker (see docs/99-agent for root cause analysis).
	docker compose $(COMPOSE_TEST) up -d db
	docker compose $(COMPOSE_TEST) run --rm --env PYTEST_OPTS="--create-db --tb=short -n auto --maxprocesses=4 --dist loadgroup" test

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
		--ignore=.mypy_cache --ignore=.ruff_cache --ignore=.pytest_cache --ignore=node_modules \
		--ignore=.tox --ignore=.nox --ignore=__pypackages__ --ignore=.uv --ignore=.cache \
		--ignore=.local --ignore=.playwright-mcp --ignore=.coverage --ignore=.hypothesis \
		--locale ru --locale bs --locale en

create-admin:
	set -a; . .env.dev; set +a; \
	docker compose $(COMPOSE_FILES) run --rm web uv run python src/backend/manage.py create_admin_user \
		--username "$${ADMIN_USERNAME:-admin}" \
		--password "$${ADMIN_PASSWORD}" \
		--telegram-id "$${ADMIN_TELEGRAM_ID:--1}"

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
	set -a; . .env.dev; set +a; \
	docker compose $(COMPOSE_FILES) exec db psql -U "$${POSTGRES_USER}" -d "$${POSTGRES_DB}"

logs:
	docker compose $(COMPOSE_FILES) logs -f

# ====================== Backups ======================

BACKUPS_DIR := ./backups

backup:
	@mkdir -p $(BACKUPS_DIR)
	@set -a; . .env.dev; set +a; \
	TIMESTAMP=$$(date +%Y%m%d_%H%M%S) && \
		docker compose $(ENV_FILE) -f docker-compose.yml exec -T db \
			pg_dump --no-sync -U "$${POSTGRES_USER}" -d "$${POSTGRES_DB}" -F c \
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
	@set -a; . .env.dev; set +a; \
	docker compose $(ENV_FILE) -f docker-compose.yml exec -T db \
		pg_restore -U "$${POSTGRES_USER}" -d "$${POSTGRES_DB}" --clean --if-exists $(BACKUP_FILE)
	@echo "✓ Restore completed from $(BACKUP_FILE)"

# restore-test: Restore a backup into a fully isolated PostgreSQL instance (separate
# volume, separate network, separate DB) so the live production database is never
# touched. Uses `docker run` directly (not `docker compose`) for complete isolation.
restore-test:
	@if [ -z "$(BACKUP_FILE)" ]; then \
		echo "Error: BACKUP_FILE not specified"; \
		echo "Example: make restore-test BACKUP_FILE=./backups/dump_20250719_143022.dump"; \
		exit 1; \
	fi
	@if [ ! -f "$(BACKUP_FILE)" ]; then \
		echo "Error: file $(BACKUP_FILE) not found"; \
		exit 1; \
	fi
	@set -e; \
	RESTORE_TS=$$(date +%Y%m%d_%H%M%S) && \
	RESTORE_VOL="mko-bazuna-restore-$$RESTORE_TS" && \
	RESTORE_NET="mko-bazuna-restore-net-$$RESTORE_TS" && \
	BACKUP_NAME=$$(basename "$(BACKUP_FILE)") && \
	cleanup() { \
		echo "→ Tearing down isolated resources..."; \
		docker stop restore-db 2>/dev/null || true; \
		docker rm -f restore-db 2>/dev/null || true; \
		docker volume rm $$RESTORE_VOL 2>/dev/null || true; \
		docker network rm $$RESTORE_NET 2>/dev/null || true; \
		echo "✓ Isolated restore-test environment cleaned up"; \
	}; \
	trap cleanup EXIT; \
	echo "→ Creating isolated restore volume: $$RESTORE_VOL" && \
	docker volume create $$RESTORE_VOL && \
	echo "→ Creating isolated network: $$RESTORE_NET" && \
	docker network create $$RESTORE_NET && \
	echo "→ Starting isolated postgres:18-alpine (db=bazuna_restore, user=restore_user)" && \
	docker run --rm -d \
		--name restore-db \
		--network $$RESTORE_NET \
		-v $$RESTORE_VOL:/var/lib/postgresql \
		-v $(CURDIR)/backups:/backups:ro \
		-e POSTGRES_DB=bazuna_restore \
		-e POSTGRES_USER=restore_user \
		-e POSTGRES_PASSWORD=restore_pass \
		-e POSTGRES_HOST_AUTH_METHOD=trust \
		postgres:18-alpine && \
	echo "→ Waiting for postgres readiness..." && \
	_i=0; until docker exec restore-db pg_isready -U restore_user -d bazuna_restore; do \
		sleep 1; _i=$$((_i + 1)); \
		if [ $$_i -ge 30 ]; then echo "Error: postgres did not become ready in 30s"; exit 1; fi; \
	done && \
	echo "→ Restoring backup into isolated DB: $(BACKUP_FILE)" && \
	docker exec restore-db pg_restore --clean --if-exists -U restore_user -d bazuna_restore -F c /backups/$$BACKUP_NAME && \
	echo "→ Smoke test 1/4: pg_isready (connectivity)" && \
	docker exec restore-db pg_isready -U restore_user -d bazuna_restore && \
	echo "  ✓ Connectivity OK" && \
	echo "→ Smoke test 2/4: table count (schema present)" && \
	echo "  Tables: $$(docker exec restore-db psql -U restore_user -d bazuna_restore -t -A -c \
		"SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")" && \
	echo "→ Smoke test 3/4: row count in ads_ad (data present)" && \
	echo "  ads_ad rows: $$(docker exec restore-db psql -U restore_user -d bazuna_restore -t -A -c \
		"SELECT count(*) FROM ads_ad;")" && \
	echo "→ Smoke test 4/4: schema list" && \
	docker exec restore-db psql -U restore_user -d bazuna_restore -c "\dn" && \
	if [ -z "$(APP_IMAGE)" ]; then \
		echo "→ Skipping migrate --plan --check (APP_IMAGE not set)"; \
	else \
		echo "→ Running migrate --plan --check against restored DB" && \
		docker run --rm --network $$RESTORE_NET \
			-e DJANGO_SETTINGS_MODULE=config.settings.prod \
			-e DJANGO_BUILD=1 \
			-e DATABASE_URL=postgres://restore_user:restore_pass@restore-db:5432/bazuna_restore \
			-e ALLOWED_HOSTS='*' \
			-e SKIP_ENV_CHECK=1 \
			$(APP_IMAGE) \
			python src/backend/manage.py migrate --plan --check; \
	fi && \
	echo "✓ Restore-test completed successfully from $(BACKUP_FILE)"

prune-backups:
	@find $(BACKUPS_DIR) -name "dump_*.dump" -mtime +7 -delete -print
	@echo "✓ Old backups (older than 7 days) pruned"

# ====================== Cleanup ======================

# Nuclear: remove containers, volumes (incl. postgres_data, media_volume), and local DB backups
clean:
	docker compose $(COMPOSE_FILES) down -v --remove-orphans
	rm -rf $(BACKUPS_DIR)/*.dump

fullclean:
	# Nuclear: stop both dev + test projects (wiping volumes),
	# then prune ALL unused images, volumes, and build cache system-wide.
	# Equivalent to: .\\Makefile.ps1 fullclean
	docker compose $(COMPOSE_FILES) down -v --remove-orphans
	COMPOSE_PROJECT_NAME=mko-bazuna-test docker compose $(COMPOSE_TEST) down -v --remove-orphans
	docker system prune -f --volumes
	docker image prune -a -f
	docker builder prune -a -f
	@echo "Full clean completed. Run 'make build' and 'make up' to restart."

# ====================== Performance (PERF-002) ======================
# Run locust load tests against the running dev server.
# Assumes `make up` has started the dev environment (web server on :8000).
# Override defaults via environment: LOCUST_USERS=100 LOCUST_SPAWN_RATE=5 make load

LOCUST_HOST ?= http://localhost:8000
LOCUST_USERS ?= 50
LOCUST_SPAWN_RATE ?= 10
LOCUST_RUN_TIME ?= 60s

load:
	docker compose $(COMPOSE_FILES) exec web uv run locust -f src/benchmark/locustfile.py \
		--headless --host $(LOCUST_HOST) \
		--users $(LOCUST_USERS) --spawn-rate $(LOCUST_SPAWN_RATE) \
		--run-time $(LOCUST_RUN_TIME) -L info

# Run the cProfile-based search-endpoint profiling harness.
# Assumes `make up` has started the dev environment.
# Override defaults: ITERATIONS=200 make profile
# Sort key: SORT=cumulative|time|calls|filename (default: cumulative)
profile:
	ITERATIONS=$(or $(ITERATIONS),50) \
	TOP=$(or $(TOP),30) \
	SORT=$(or $(SORT),cumulative) \
	docker compose $(COMPOSE_FILES) exec -T web uv run python scripts/profile_search.py \
		--iterations $${ITERATIONS} --top $${TOP} --sort $${SORT}
