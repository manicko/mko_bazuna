# Makefile for Mko Bazuna Docker workflow
# Provides ergonomic developer commands for container-based workflow

.PHONY: help up down test lint typecheck shell migrate makemigrations logs backup restore prune-backups

# Default target: show help
help:
	@echo "Mko Bazuna - Development Commands"
	@echo ""
	@echo "Usage: make <target>"
	@echo ""
	@echo "Targets:"
	@echo "  up             Start development environment (web on :8000, hot-reload)"
	@echo "  down           Stop and remove containers"
	@echo "  test           Run pytest in test container (ephemeral PostgreSQL)"
	@echo "  lint           Run ruff linter inside web container"
	@echo "  typecheck      Run basedpyright type checker inside web container"
	@echo "  shell          Open bash shell in web container"
	@echo "  migrate        Run database migrations (one-shot, advisory-locked)"
	@echo "  makemigrations Create Django migrations from model changes"
	@echo "  logs           Follow logs from all services"
	@echo "  backup         Create PostgreSQL backup with 7-day rotation"
	@echo "  restore        Restore database from backup file"
	@echo "  prune-backups  Manually prune backups older than 7 days"

# Start development environment
up:
	docker compose -f docker-compose.yml -f docker-compose.dev.override.yml up -d

# Stop and remove containers
down:
	docker compose -f docker-compose.yml -f docker-compose.dev.override.yml down

# Run tests in test container (ephemeral PostgreSQL)
test:
	docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm test

# Run linter inside web container
lint:
	docker compose -f docker-compose.yml -f docker-compose.dev.override.yml run --rm web uv run ruff check src/

# Run type checker inside web container
typecheck:
	docker compose -f docker-compose.yml -f docker-compose.dev.override.yml run --rm web uv run basedpyright src/

# Open shell in web container
shell:
	docker compose -f docker-compose.yml -f docker-compose.dev.override.yml run --rm web /bin/bash

# Run migrations (one-shot service)
migrate:
	docker compose run --rm migrate

# Create migrations from model changes
makemigrations:
	docker compose -f docker-compose.yml -f docker-compose.dev.override.yml run --rm web uv run python src/backend/manage.py makemigrations

# Follow logs from all services
logs:
	docker compose -f docker-compose.yml -f docker-compose.dev.override.yml logs -f

# Create database backup with timestamp and 7-day rotation
backup:
	@mkdir -p ./backups
	@TIMESTAMP=$$(date +%Y%m%d_%H%M%S) && \
	docker compose exec -T db pg_dump -U $$(POSTGRES_USER) -d $$(POSTGRES_DB) -F c > ./backups/dump_$${TIMESTAMP}.dump && \
	echo "Backup created: ./backups/dump_$${TIMESTAMP}.dump"
	@find ./backups -name "dump_*.dump" -mtime +7 -delete -print
	@echo "Old backups (7+ days) pruned"

# Restore database from backup file
restore:
	@if [ -z "$(BACKUP_FILE)" ]; then \
		echo "Error: BACKUP_FILE not set. Usage: make restore BACKUP_FILE=./backups/filename.dump"; \
		exit 1; \
	fi
	docker compose exec -T db pg_restore -U $(POSTGRES_USER) -d $(POSTGRES_DB) --clean --if-exists $(BACKUP_FILE)

# Manual prune of old backups
prune-backups:
	find ./backups -name "dump_*.dump" -mtime +7 -delete -print
	@echo "Old backups (7+ days) pruned"