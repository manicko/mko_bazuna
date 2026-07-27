# Server Backup Implementation Plan

## Overview

This plan implements server-side backup for Mko Bazuna using **pg_dump + Restic + Backblaze B2** approach as recommended in the research.

## Implementation Stages

```
Research (Done) → Planning (Current) → Implementation → Validation
```

---

## Phase 1: Configuration Updates

### Task 1.1: Update .env.docker for Backup Credentials

**Priority:** High  
**Effort:** Trivial  
**File:** `.env.docker` (create from template)

Add backup-related environment variables:

```env
# Backup configuration
BACKUP_BUCKET=mko-bazuna-backups
BACKUP_REGION=us-west-004
BACKUP_S3_ENDPOINT=s3.us-west-004.backblazeb2.com
RESTIC_PASSWORD=
B2_KEY_ID=
B2_APP_KEY=
HEALTHCHECK_UUID=
BACKUP_RETENTION_DAYS=7
BACKUP_RETENTION_WEEKS=4
```

**Command:**
```bash
cp .env.docker.example .env.docker  # if template exists, or create new file
```

---

### Task 1.2: Create .env.docker.example Template

**Priority:** High  
**Effort:** Trivial  
**File:** `.env.docker.example`

Create template file without actual secrets:

```env
# Django
DJANGO_SECRET_KEY=
BOT_TOKEN=

# PostgreSQL
POSTGRES_DB=postgres
POSTGRES_USER=postgres
POSTGRES_PASSWORD=
POSTGRES_HOST=db

# Admin
ADMIN_USERNAME=admin
ADMIN_PASSWORD=
ADMIN_TELEGRAM_ID=-1

# TLS (optional)
TLS_CERT_PATH=/etc/nginx/certs

# Backup credentials (required for production backup profile)
B2_KEY_ID=
B2_APP_KEY=
RESTIC_PASSWORD=
HEALTHCHECK_UUID=
BACKUP_RETENTION_DAYS=7
BACKUP_RETENTION_WEEKS=4
```

---

## Phase 2: Docker Compose Configuration

### Task 2.1: Update backup Service in docker-compose.prod.yml

**Priority:** High  
**Effort:** Medium  
**File:** `docker-compose.prod.yml`

Replace existing backup service with enhanced version including media backup and Restic sync:

**Current (lines 47-79):**
```yaml
backup:
  image: postgres:18-alpine
  environment:
    POSTGRES_HOST: db
    POSTGRES_PORT: 5432
    POSTGRES_DB: ${POSTGRES_DB:-postgres}
    POSTGRES_USER: ${POSTGRES_USER:-postgres}
    PGPASSWORD: ${POSTGRES_PASSWORD:-postgres}
  volumes:
    - ./backups:/backups
  command:
    - /bin/sh
    - -c
    - |
      set -e;
      until pg_isready -h $$POSTGRES_HOST -p $$POSTGRES_PORT; do sleep 5; done;
      while true; do
        date=$$(date +%Y%m%d);
        pg_dump -h $$POSTGRES_HOST -p $$POSTGRES_PORT
          -U $$POSTGRES_USER -d $$POSTGRES_DB -F c
          -f /backups/dump_$$date.dump;
        echo "Backup completed: dump_$$date.dump";
        find /backups -name 'dump_*.dump' -mtime +7 -delete 2>/dev/null || true;
        sleep 86400;
      done
```

**Replace with:**
```yaml
backup:
  build:
    context: .
    dockerfile: docker/Dockerfile.backup
  environment:
    POSTGRES_HOST: db
    POSTGRES_PORT: 5432
    POSTGRES_DB: ${POSTGRES_DB:-postgres}
    POSTGRES_USER: ${POSTGRES_USER:-postgres}
    PGPASSWORD: ${POSTGRES_PASSWORD:-postgres}
    B2_KEY_ID: ${B2_KEY_ID}
    B2_APP_KEY: ${B2_APP_KEY}
    RESTIC_PASSWORD: ${RESTIC_PASSWORD}
    HEALTHCHECK_UUID: ${HEALTHCHECK_UUID}
    BACKUP_RETENTION_DAYS: ${BACKUP_RETENTION_DAYS:-7}
    BACKUP_RETENTION_WEEKS: ${BACKUP_RETENTION_WEEKS:-4}
    BACKUP_S3_ENDPOINT: ${BACKUP_S3_ENDPOINT}
    BACKUP_BUCKET: ${BACKUP_BUCKET}
  volumes:
    - ./backups:/backups
    - media_volume:/media:ro
    - /var/run/docker.sock:/var/run/docker.sock:ro
  secrets:
    - restic_pass
  command: /app/scripts/backup.sh
  depends_on:
    db:
      condition: service_healthy
  restart: unless-stopped
  profiles:
    - backup
```

---

### Task 2.2: Create Dockerfile.backup

**Priority:** High  
**Effort:** Small  
**File:** `docker/Dockerfile.backup`

Multi-stage Dockerfile with Restic and rclone:

```dockerfile
FROM alpine:3.20 AS base
RUN apk add --no-cache \
    postgresql-client=18.* \
    restic=0.18.* \
    rclone=1.67.* \
    curl=8.* \
    bash=5.* \
    docker-cli=26.*

FROM base AS backup
COPY scripts/backup.sh /app/scripts/backup.sh
RUN chmod +x /app/scripts/backup.sh
ENTRYPOINT ["/app/scripts/backup.sh"]
```

---

### Task 2.3: Add Docker Secrets Configuration

**Priority:** Medium  
**Effort:** Small  
**File:** `docker-compose.yml`

Add secrets section to root level:

```yaml
secrets:
  restic_pass:
    file: ./secrets/restic_pass.txt
```

---

### Task 2.4: Create backup-secrets Example

**Priority:** Medium  
**Effort:** Trivial  
**File:** `scripts/secrets/restic_pass.example`

```
# Copy to secrets/restic_pass.txt and set actual password
# chmod 600 secrets/restic_pass.txt
your-restic-password-here
```

---

## Phase 3: Backup Script Implementation

### Task 3.1: Create backup.sh Script

**Priority:** High  
**Effort:** Medium  
**File:** `scripts/backup.sh`

Main backup orchestration script:

```bash
#!/bin/bash
set -euo pipefail

# Configuration
BACKUP_DIR="/backups"
DB_HOST="${POSTGRES_HOST:-db}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_NAME="${POSTGRES_DB:-postgres}"
DB_USER="${POSTGRES_USER:-postgres}"
B2_ACCESS_KEY="${B2_KEY_ID}"
B2_SECRET_KEY="${B2_APP_KEY}"
RESTIC_PASS="${RESTIC_PASSWORD}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"
RETENTION_WEEKS="${BACKUP_RETENTION_WEEKS:-4}"

# Ensure backup directory exists
mkdir -p "${BACKUP_DIR}"

# Step 1: PostgreSQL dump
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DB_DUMP="${BACKUP_DIR}/db_${TIMESTAMP}.dump"

echo "Starting backup: ${TIMESTAMP}"

# Wait for database to be ready
until pg_isready -h "${DB_HOST}" -p "${DB_PORT}"; do
    echo "Waiting for database..."
    sleep 5
done

pg_dump -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" -F c -f "${DB_DUMP}"
echo "✓ Database backup: ${DB_DUMP}"

# Step 2: Media volume backup
MEDIA_BACKUP="${BACKUP_DIR}/media_${TIMESTAMP}.tar.gz"

# Get media volume data directory
MEDIA_VOLUME_PATH="/var/lib/docker/volumes/mko_bazuna_media_volume/_data"
if [ -d "${MEDIA_VOLUME_PATH}" ]; then
    tar -czf "${MEDIA_BACKUP}" -C "${MEDIA_VOLUME_PATH}" .
    echo "✓ Media backup: ${MEDIA_BACKUP}"
else
    echo "! Media volume not found at ${MEDIA_VOLUME_PATH}"
fi

# Step 3: Initialize and run Restic backup
export AWS_ACCESS_KEY_ID="${B2_ACCESS_KEY}"
export AWS_SECRET_ACCESS_KEY="${B2_SECRET_KEY}"
export RESTIC_PASSWORD="${RESTIC_PASS}"

REPO="s3:${BACKUP_S3_ENDPOINT:-s3.us-west-004.backblazeb2.com}/${BACKUP_BUCKET:-mko-bazuna-backups}"

# Initialize repo if needed (non-fatal if exists)
restic init --repo "${REPO}" --password-file <(echo "${RESTIC_PASS}") 2>/dev/null || true

# Run backup
restic backup /backups \
    --repo "${REPO}" \
    --password-file <(echo "${RESTIC_PASS}") \
    --tag "${TIMESTAMP}" \
    --quiet

echo "✓ Restic backup completed"

# Step 4: Prune old backups
restic forget --keep-daily "${RETENTION_DAYS}" --keep-weekly "${RETENTION_WEEKS}" --prune \
    --repo "${REPO}" \
    --password-file <(echo "${RESTIC_PASS}") \
    --quiet

echo "✓ Old backups pruned"

# Step 5: Healthcheck ping
if [ -n "${HEALTHCHECK_UUID:-}" ]; then
    curl -fsS --retry 3 "https://hc-ping.com/${HEALTHCHECK_UUID}" || echo "Warning: healthcheck ping failed"
fi

echo "Backup completed successfully: ${TIMESTAMP}"

# Schedule next run (daily)
sleep 86400
```

---

### Task 3.2: Create restore.sh Script

**Priority:** High  
**Effort:** Medium  
**File:** `scripts/restore.sh`

Database and media restore script:

```bash
#!/bin/bash
set -euo pipefail

# Configuration
BACKUP_DIR="/backups"
RESTORE_DIR="/restore"
DB_HOST="${POSTGRES_HOST:-db}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_NAME="${POSTGRES_DB:-postgres}"
DB_USER="${POSTGRES_USER:-postgres}"
RESTIC_PASS="${RESTIC_PASSWORD}"

# Safety check: confirm production
if [ "${CONFIRM_RESTORE:-}" != "yes" ]; then
    echo "ERROR: CONFIRM_RESTORE=yes required for safety"
    echo "Example: CONFIRM_RESTORE=yes ./restore.sh"
    exit 1
fi

echo "Starting restore procedure..."

# Step 1: Stop write services
echo "Stopping web and bot services..."
docker compose -f /app/docker-compose.yml stop web bot 2>/dev/null || true

# Step 2: Wait for database
until pg_isready -h "${DB_HOST}" -p "${DB_PORT}"; do
    echo "Waiting for database..."
    sleep 5
done

# Step 3: Find latest backup
LATEST_DB_DUMP=$(ls -t "${BACKUP_DIR}"/db_*.dump 2>/dev/null | head -1)
LATEST_MEDIA_TAR=$(ls -t "${BACKUP_DIR}"/media_*.tar.gz 2>/dev/null | head -1)

if [ -z "${LATEST_DB_DUMP:-}" ]; then
    echo "ERROR: No database backup found in ${BACKUP_DIR}"
    exit 1
fi

echo "Latest backup: ${LATEST_DB_DUMP}"

# Step 4: Restore database
echo "Restoring database..."
pg_restore -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" \
    --clean --if-exists "${LATEST_DB_DUMP}"

echo "✓ Database restored"

# Step 5: Restore media if available
if [ -n "${LATEST_MEDIA_TAR:-}" ]; then
    echo "Restoring media files..."
    docker run --rm \
        -v mko_bazuna_media_volume:/media \
        -v "${BACKUP_DIR}:/backups" \
        alpine sh -c "cd /media && tar -xzf ${LATEST_MEDIA_TAR}"
    echo "✓ Media restored"
fi

echo "Restore completed. Remember to run migrations if needed."
```

---

### Task 3.3: Create verify-backup.sh Script

**Priority:** Medium  
**Effort:** Small  
**File:** `scripts/verify-backup.sh`

Backup integrity verification:

```bash
#!/bin/bash
set -euo pipefail

BACKUP_DIR="${1:-./backups}"
RESTIC_PASS="${RESTIC_PASSWORD}"

echo "Verifying backup integrity..."

# Check database dumps
for dump in "${BACKUP_DIR}"/db_*.dump; do
    if [ -f "$dump" ]; then
        echo "Checking: $dump"
        pg_restore --list "$dump" > /dev/null && echo "  ✓ Valid"
    fi
done

# Verify Restic repository
export RESTIC_PASSWORD="${RESTIC_PASS}"
export AWS_ACCESS_KEY_ID="${B2_KEY_ID}"
export AWS_SECRET_ACCESS_KEY="${B2_APP_KEY}"

REPO="s3:${BACKUP_S3_ENDPOINT:-s3.us-west-004.backblazeb2.com}/${BACKUP_BUCKET:-mko-bazuna-backups}"

echo "Checking Restic repository..."
restic check --repo "${REPO}" --password-file <(echo "${RESTIC_PASS}") || echo "Warning: repository check failed"

echo "Verification complete"
```

---

## Phase 4: Makefile Updates

### Task 4.1: Update Makefile Backup Targets

**Priority:** High  
**Effort:** Small  
**File:** `Makefile`

Add new targets after existing backup section (after line 120):

```makefile
# ====================== Enhanced Backups ======================

backup-prod:
	@docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile backup up -d
	@echo "✓ Backup service started"

backup-stop:
	@docker compose -f docker-compose.yml -f docker-compose.prod.yml stop backup
	@echo "✓ Backup service stopped"

restore-prod:
	@CONFIRM_RESTORE=yes docker compose -f docker-compose.yml -f docker-compose.prod.yml \
		run --rm backup /app/scripts/restore.sh
	@echo "✓ Restore procedure initiated"

verify-backups:
	@docker compose -f docker-compose.yml -f docker-compose.prod.yml \
		run --rm backup /app/scripts/verify-backup.sh /backups
	@echo "✓ Backup verification complete"

media-backup:
	@TIMESTAMP=$$(date +%Y%m%d_%H%M%S) && \
	docker run --rm -v mko_bazuna_media_volume:/media \
	-v $(BACKUPS_DIR):/backups alpine tar -czf /backups/media_$${TIMESTAMP}.tar.gz -C /media . && \
	echo "✓ Media backup created: $(BACKUPS_DIR)/media_$${TIMESTAMP}.tar.gz"
```

---

## Phase 5: Documentation

### Task 5.1: Update docs/ops/restore.md

**Priority:** Medium  
**Effort:** Medium  
**File:** `docs/ops/restore.md`

Add sections for:
- Media restore procedure
- Restic-based restore
- Offsite recovery
- Backup verification

---

### Task 5.2: Create Backup Operations Guide

**Priority:** Medium  
**Effort:** Small  
**File:** `docs/ops/backup-operations.md`

Create comprehensive guide covering:
- Enabling backup profile
- Monitoring backup status
- Manual backup triggers
- Backup storage locations

---

## Phase 6: Validation

### Task 6.1: Test Database Backup

**Priority:** High  
**Effort:** Small  
**Command:**
```bash
make backup
ls -la ./backups/
pg_restore --list ./backups/db_*.dump | head -20
```

---

### Task 6.2: Test Media Backup

**Priority:** High  
**Effort:** Small  
**Command:**
```bash
make media-backup
ls -la ./backups/media_*.tar.gz
tar -tzf ./backups/media_*.tar.gz | head -5
```

---

### Task 6.3: Test Backup Service

**Priority:** High  
**Effort:** Medium  
**Command:**
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile backup up -d
docker compose ps backup
docker compose logs -f backup
```

---

## Task Summary

| Task ID | Description | Priority | Effort | Dependencies |
|---------|-------------|----------|--------|--------------|
| 1.1 | Create .env.docker.example | High | Trivial | None |
| 1.2 | Documentation only | Medium | Trivial | None |
| 2.1 | Update backup service config | High | Medium | None |
| 2.2 | Create Dockerfile.backup | High | Small | None |
| 2.3 | Add secrets configuration | Medium | Small | None |
| 2.4 | Create secrets example | Medium | Trivial | 2.3 |
| 3.1 | Create backup.sh script | High | Medium | 2.1, 2.2 |
| 3.2 | Create restore.sh script | High | Medium | 3.1 |
| 3.3 | Create verify-backup.sh | Medium | Small | None |
| 4.1 | Update Makefile targets | High | Small | 3.x |
| 5.1 | Update restore documentation | Medium | Medium | 3.x |
| 5.2 | Create backup operations guide | Medium | Small | 4.1 |
| 6.1 | Test database backup | High | Small | 1.1, 3.1 |
| 6.2 | Test media backup | High | Small | 3.1 |
| 6.3 | Test backup service | High | Medium | 2.1, 3.1 |

---

## Execution Order

```
1. Configuration (1.1 → 1.2, parallel)
2. Docker Setup (2.1 → 2.2 → 2.3 → 2.4)
3. Scripts (3.1 → 3.2 → 3.3, parallel after 3.1)
4. Makefile (4.1, after 3.x)
5. Documentation (5.1 → 5.2, after 4.1)
6. Validation (6.1 → 6.2 → 6.3, sequential)
```

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Large backup files may exhaust disk | Monitor with healthchecks, implement alerts |
| Media volume path may differ on some systems | Check at runtime with docker volume inspect |
| Restic repository corruption | Run weekly verification checks |
| Secret exposure in container | Use Docker secrets, never commit to repo |

---

## Estimated Timeline

- **Phase 1-2:** 1-2 hours
- **Phase 3:** 2-3 hours
- **Phase 4-5:** 1 hour
- **Phase 6:** 1-2 hours (testing)

**Total effort:** 5-8 hours