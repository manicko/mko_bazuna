# Server Backup Implementation Plan

## Overview

This plan implements server-side backup for Mko Bazuna using **pg_dump + Restic + Backblaze B2** approach as recommended in the research.

## Implementation Stages

```
Research (Done) → Planning (Current) → Implementation → Validation
```

---

## Phase 1: Configuration Updates

### Task 1.1: Create .env.docker.example Template

**Priority:** High  
**Effort:** Trivial  
**File:** `.env.docker.example` (NEW FILE)

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

**Command:**
```bash
# Copy example to create .env.docker
cp .env.docker.example .env.docker
# Then edit .env.docker to add actual values
```

---

## Phase 2: Docker Compose Configuration

### Task 2.1: Update backup Service in docker-compose.prod.yml

**Priority:** High  
**Effort:** Medium  
**File:** `docker-compose.prod.yml`

Replace existing backup service with enhanced version:

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
    BACKUP_RETENTION_DAYS: ${BACKUP_RETENTION_DAYS:-7}
    BACKUP_RETENTION_WEEKS: ${BACKUP_RETENTION_WEEKS:-4}
    BACKUP_S3_ENDPOINT: ${BACKUP_S3_ENDPOINT}
    BACKUP_BUCKET: ${BACKUP_BUCKET}
  volumes:
    - ./backups:/backups
    - media_volume:/media:ro
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

### Task 2.2: Create Dockerfile.backup

**Priority:** High  
**Effort:** Small  
**File:** `docker/Dockerfile.backup`

Multi-stage Dockerfile with Restic:

```dockerfile
FROM alpine:3.20 AS base
RUN apk add --no-cache \
    postgresql-client=18.* \
    restic=0.18.* \
    curl=8.* \
    bash=5.* \
    coreutils=9.*

FROM base AS backup
COPY scripts/backup.sh /app/scripts/backup.sh
RUN chmod +x /app/scripts/backup.sh
ENTRYPOINT ["/app/scripts/backup.sh"]
```

### Task 2.3: Add Docker Secrets Configuration

**Priority:** Medium  
**Effort:** Small  
**File:** `docker-compose.yml` (root level)

Add secrets section:

```yaml
secrets:
  restic_pass:
    file: ./secrets/restic_pass.txt
```

### Task 2.4: Create secrets directory

**Priority:** Medium  
**Effort:** Trivial

```bash
mkdir -p secrets
# Create secrets/restic_pass.txt with the Restic password
chmod 600 secrets/restic_pass.txt
# Add secrets/ to .gitignore
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
MEDIA_DIR="/media"
DB_HOST="${POSTGRES_HOST:-db}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_NAME="${POSTGRES_DB:-postgres}"
DB_USER="${POSTGRES_USER:-postgres}"
B2_ACCESS_KEY="${B2_KEY_ID}"
B2_SECRET_KEY="${B2_APP_KEY}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"
RETENTION_WEEKS="${BACKUP_RETENTION_WEEKS:-4}"

# Cleanup old local backups (keep last 2 days for quick restore)
cleanup_local_backups() {
    find "${BACKUP_DIR}" -name 'db_*.dump' -mtime +2 -delete 2>/dev/null || true
    find "${BACKUP_DIR}" -name 'media_*.tar.gz' -mtime +2 -delete 2>/dev/null || true
}

# Verify PostgreSQL dump integrity
verify_db_dump() {
    local dump_file="$1"
    if pg_restore --list "${dump_file}" >/dev/null 2>&1; then
        echo "✓ Verified: ${dump_file}"
        return 0
    else
        echo "✗ CORRUPT: ${dump_file}"
        return 1
    fi
}

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

# Verify dump integrity
if ! verify_db_dump "${DB_DUMP}"; then
    echo "ERROR: Database dump verification failed"
    exit 1
fi

# Step 2: Media volume backup
MEDIA_BACKUP="${BACKUP_DIR}/media_${TIMESTAMP}.tar.gz"

if [ -d "${MEDIA_DIR}" ]; then
    tar -czf "${MEDIA_BACKUP}" -C "${MEDIA_DIR}" .
    echo "✓ Media backup: ${MEDIA_BACKUP}"
else
    echo "! Media volume not found at ${MEDIA_DIR}, skipping"
fi

# Step 3: Initialize and run Restic backup
export AWS_ACCESS_KEY_ID="${B2_ACCESS_KEY}"
export AWS_SECRET_ACCESS_KEY="${B2_SECRET_KEY}"
export RESTIC_PASSWORD_FILE="/run/secrets/restic_pass"

REPO="s3:${BACKUP_S3_ENDPOINT:-s3.us-west-004.backblazeb2.com}/${BACKUP_BUCKET:-mko-bazuna-backups}"

# Initialize repo if needed (non-fatal if exists)
restic init --repo "${REPO}" 2>/dev/null || true

# Run backup
restic backup /backups \
    --repo "${REPO}" \
    --quiet

echo "✓ Restic backup completed"

# Verify Restic backup
restic check --repo "${REPO}" || echo "Warning: repository check reported issues"

# Step 4: Prune old backups
restic forget --keep-daily "${RETENTION_DAYS}" --keep-weekly "${RETENTION_WEEKS}" --prune \
    --repo "${REPO}" \
    --quiet

echo "✓ Old backups pruned"

# Step 5: Cleanup local backups after successful sync
cleanup_local_backups
echo "✓ Local backup files cleaned"

# Step 6: Healthcheck ping
if [ -n "${HEALTHCHECK_UUID:-}" ]; then
    curl -fsS --retry 3 "https://hc-ping.com/${HEALTHCHECK_UUID}" || {
        echo "ERROR: Healthcheck ping failed"
        exit 1
    }
fi

echo "Backup completed successfully: ${TIMESTAMP}"

# Schedule next run (daily)
sleep 86400
```

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
DB_HOST="${POSTGRES_HOST:-db}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_NAME="${POSTGRES_DB:-postgres}"
DB_USER="${POSTGRES_USER:-postgres}"

# Safety check: confirm production
if [ "${CONFIRM_RESTORE:-}" != "yes" ]; then
    echo "ERROR: CONFIRM_RESTORE=yes required for safety"
    echo "Example: CONFIRM_RESTORE=yes docker compose run --rm backup /app/scripts/restore.sh"
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
if ! pg_restore -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" \
    --clean --if-exists "${LATEST_DB_DUMP}"; then
    echo "ERROR: Database restore failed"
    echo "Restore halted - media files will NOT be restored to prevent inconsistency"
    exit 1
fi

echo "✓ Database restored"

# Step 5: Restore media if available
if [ -n "${LATEST_MEDIA_TAR:-}" ]; then
    echo "Restoring media files..."
    if ! tar -xzf "${LATEST_MEDIA_TAR}" -C "${MEDIA_DIR:-/media}" 2>/dev/null; then
        echo "ERROR: Media restore failed"
        exit 1
    fi
    echo "✓ Media restored"
fi

echo "Restore completed. Remember to run migrations if needed."
```

### Task 3.3: Create verify-backup.sh Script

**Priority:** Medium  
**Effort:** Small  
**File:** `scripts/verify-backup.sh`

Backup integrity verification:

```bash
#!/bin/bash
set -euo pipefail

BACKUP_DIR="${1:-./backups}"

echo "Verifying backup integrity..."

# Check database dumps
for dump in "${BACKUP_DIR}"/db_*.dump; do
    if [ -f "$dump" ]; then
        echo "Checking: $dump"
        pg_restore --list "$dump" > /dev/null && echo "  ✓ Valid" || echo "  ✗ CORRUPT"
    fi
done

# Verify Restic repository
export export RESTIC_PASSWORD_FILE="/run/secrets/restic_pass"
export AWS_ACCESS_KEY_ID="${B2_KEY_ID}"
export AWS_SECRET_ACCESS_KEY="${B2_APP_KEY}"

REPO="s3:${BACKUP_S3_ENDPOINT:-s3.us-west-004.backblazeb2.com}/${BACKUP_BUCKET:-mko-bazuna-backups}"

echo "Checking Restic repository..."
restic check --repo "${REPO}" || echo "Warning: repository check failed"

echo "Verification complete"
```

---

## Phase 4: Makefile Updates

### Task 4.1: Update Makefile Backup Targets

**Priority:** High  
**Effort:** Small  
**File:** `Makefile`

Add new targets:

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
	-v $(PWD)/backups:/backups alpine tar -czf /backups/media_$${TIMESTAMP}.tar.gz -C /media . && \
	echo "✓ Media backup created: backups/media_$${TIMESTAMP}.tar.gz"
```

---

## Phase 5: Documentation

### Task 5.1: Update docs/ops/restore.md

**Priority:** Medium  
**Effort:** Medium  
**File:** `docs/ops/restore.md`

Add sections for media restore, Restic-based restore, offsite recovery.

### Task 5.2: Create Backup Operations Guide

**Priority:** Medium  
**Effort:** Small  
**File:** `docs/ops/backup-operations.md`

Guide covering enabling backup profile, monitoring, manual triggers.

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

### Task 6.2: Test Media Backup

**Priority:** High  
**Effort:** Small  
**Command:**
```bash
make media-backup
ls -la ./backups/media_*.tar.gz
tar -tzf ./backups/media_*.tar.gz | head -5
```

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
| 1.1 | Create .env.docker.example template | High | Trivial | None |
| 2.1 | Update backup service in docker-compose.prod.yml | High | Medium | None |
| 2.2 | Create Dockerfile.backup | High | Small | None |
| 2.3 | Add secrets configuration to docker-compose.yml | Medium | Small | None |
| 2.4 | Create secrets directory with example | Medium | Trivial | 2.3 |
| 3.1 | Create backup.sh with verification | High | Medium | 2.1, 2.2, 2.3 |
| 3.2 | Create restore.sh with error handling | High | Medium | 2.1, 2.2 |
| 3.3 | Create verify-backup.sh | Medium | Small | None |
| 4.1 | Update Makefile targets | High | Small | 3.x |
| 5.1 | Update docs/ops/restore.md | Medium | Medium | 3.x |
| 5.2 | Create docs/ops/backup-operations.md | Medium | Small | 4.1 |
| 6.1 | Test database backup | High | Small | 1.1, 3.1 |
| 6.2 | Test media backup | High | Small | 3.1 |
| 6.3 | Test backup service | High | Medium | 2.1, 3.1 |

---

## Execution Order

```
1. Configuration (Task 1.1)
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
| Media volume path may differ on some systems | Volume mount to /media eliminates path issues |
| Restic repository corruption | Run weekly verification checks |
| Secret exposure in container | Use Docker secrets, never commit to repo |
| docker.sock security risk | Removed - using volume mounts instead |

---

## Estimated Timeline

- **Phase 1:** 30 minutes
- **Phase 2:** 1-2 hours
- **Phase 3:** 2-3 hours
- **Phase 4-5:** 1 hour
- **Phase 6:** 1-2 hours (testing)

**Total effort:** 5-8 hours
