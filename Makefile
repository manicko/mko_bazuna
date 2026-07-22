# Makefile for Mko Bazuna Docker workflow

.PHONY: help up down build restart test lint typecheck shell migrate makemigrations logs \
        backup restore prune-backups db-shell clean create-admin

# ====================== Settings ======================

ENV_FILE := --env-file .env.docker
COMPOSE_FILES := $(ENV_FILE) -f docker-compose.yml -f docker-compose.dev.override.yml
COMPOSE_TEST := -f docker-compose.yml -f docker-compose.test.yml

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
	@echo "Code Quality:"
	@echo "  test           Run tests"
	@echo "  lint           Ruff"
	@echo "  typecheck      Basedpyright"
	@echo ""
	@echo "Django:"
	@echo "  migrate        Apply migrations"
	@echo "  makemigrations Create migrations"
	@echo "  create-admin   Create admin user manually"
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

test:
	docker compose $(COMPOSE_TEST) run --rm test

lint:
	docker compose $(COMPOSE_FILES) run --rm web uv run ruff check src/

typecheck:
	docker compose $(COMPOSE_FILES) run --rm web uv run basedpyright src/

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
