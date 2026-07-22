---
id: postgres-18-docker-volume-migration
domain: ops
tags:
  - postgresql
  - docker
  - migration
  - database
  - upgrade
related:
  - docker-deployment
  - restore
---

# PostgreSQL 18+ Docker Volume Configuration & Migration Guide

## Executive Summary

PostgreSQL 18+ introduced a **breaking change** in the official Docker image's data directory structure. The volume mount path changed from `/var/lib/postgresql/data` (PostgreSQL 17 and earlier) to `/var/lib/postgresql` (PostgreSQL 18+). This change was implemented to enable faster `pg_upgrade` operations in future major version upgrades.

**CRITICAL:** Simply changing the Docker image tag from `postgres:17` to `postgres:18` without adjusting the volume mount path will cause container startup failures with errors like:
```
error mounting ... to rootfs at /var/lib/postgresql/data: ... no such file or directory
```

---

## 1. Official PostgreSQL Docker Image Changes

### Source: Docker Hub Documentation

> **Important Change:** [the `PGDATA` environment variable of the image was changed to be version specific in PostgreSQL 18 and above](https://github.com/docker-library/postgres/pull/1259). For 18 it is `/var/lib/postgresql/18/docker`. Later versions will replace `18` with their respective major version (e.g., `/var/lib/postgresql/19/docker` for PostgreSQL `19.x`). The defined `VOLUME` was changed in 18 and above to `/var/lib/postgresql`.

### GitHub PR #1259 - The Official Change

The change was introduced in PR #1259 by maintainer @tianon:

**Key Changes:**
| Version | PGDATA Path | VOLUME Path |
|---------|-------------|-------------|
| ≤ 17 | `/var/lib/postgresql/data` | `/var/lib/postgresql/data` |
| ≥ 18 | `/var/lib/postgresql/18/docker` | `/var/lib/postgresql` |

**Rationale (from PR comments):**
> "This changes `PGDATA` to `/var/lib/postgresql/MAJOR/docker`, which matches the pre-existing convention/standard of the `pg_ctlcluster`/`postgresql-common` set of commands, and frankly is what we should've done to begin with."

### Why This Change Was Made

1. **Enable pg_upgrade --link**: The previous layout made it impossible to use PostgreSQL's fast `pg_upgrade --link` option, which requires both old and new data directories to be on the same mount point.

2. **Future-proof Upgrades**: With the new layout, upgrading from 18 to 19 (or any future major version) will be significantly simpler:
   - Start `postgres:18` container with volume at `/var/lib/postgresql` → creates data at `/var/lib/postgresql/18/docker`
   - Start `postgres:19` container with same volume → creates data at `/var/lib/postgresql/19/docker`
   - Run `pg_upgrade --link` between the two directories

3. **Align with Debian/Ubuntu convention**: The new path `/var/lib/postgresql/MAJOR/docker` matches how `pg_ctlcluster` manages multiple PostgreSQL versions.

---

## 2. Volume Path Comparison Table

| PostgreSQL Version | Volume Mount Path | Internal Data Path |
|-----------------|-------------------|-------------------|
| 16 and earlier | `/var/lib/postgresql/data` | `/var/lib/postgresql/data` |
| 17 | `/var/lib/postgresql/data` | `/var/lib/postgresql/data` |
| **18+** | **`/var/lib/postgresql`** | `/var/lib/postgresql/18/docker` |

**Note:** The `/var/lib/postgresql/data` directory is now a **symlink** to `.` (current directory) in PostgreSQL 18+, which breaks direct volume mounting at that path.

---

## 3. Recommended Migration Path (PostgreSQL 17 → 18)

### Option A: Dump and Restore (Recommended for Most Cases)

This is the safest approach for databases without special requirements:

```bash
# Step 1: Backup existing database
docker compose exec -T db pg_dump -U postgres -d postgres -F c > backup_17.dump

# Step 2: Stop services
docker compose stop web bot

# Step 3: Rename existing volume (optional, for safety)
docker volume rename mko_bazuna_postgres_data mko_bazuna_postgres_data_bak

# Step 4: Create new volume
docker volume create mko_bazuna_postgres_data
```

### Option B: Manual Folder Restructure (Advanced)

If using bind mounts and you want to preserve the exact data without dump/restore:

```bash
# On the host, restructure the directory:
mkdir -p /path/to/postgres_data/18
mv /path/to/postgres_data/data/* /path/to/postgres_data/18/docker/
# (Note: This requires careful handling and is NOT recommended for production)
```

---

## 4. Correct docker-compose.yml Configuration for PostgreSQL 18+

### Current Project Configuration (Needs Update)

**File:** `docker-compose.yml` (lines 6-19)

```yaml
services:
  db:
    image: postgres:18-alpine
    restart: always
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-postgres}
      POSTGRES_USER: ${POSTGRES_USER:-postgres}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}
    volumes:
      - postgres_data:/var/lib/postgresql/data  # ❌ WRONG for PG 18+
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-postgres} -d ${POSTGRES_DB:-postgres}"]
      interval: 5s
      timeout: 5s
      retries: 5
```

### Corrected Configuration

```yaml
services:
  db:
    image: postgres:18-alpine
    restart: always
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-postgres}
      POSTGRES_USER: ${POSTGRES_USER:-postgres}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}
    volumes:
      - postgres_data:/var/lib/postgresql  # ✅ CORRECT for PG 18+
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-postgres} -d ${POSTGRES_DB:-postgres}"]
      interval: 5s
      timeout: 5s
      retries: 5
```

### Alternative: Explicit PGDATA Configuration

If you need the old path for compatibility with tooling:

```yaml
services:
  db:
    image: postgres:18-alpine
    restart: always
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-postgres}
      POSTGRES_USER: ${POSTGRES_USER:-postgres}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}
      PGDATA: /var/lib/postgresql/data  # Override PGDATA to old path
    volumes:
      - postgres_data:/var/lib/postgresql  # Mount at parent, PGDATA set explicitly
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-postgres} -d ${POSTGRES_DB:-postgres}"]
      interval: 5s
      timeout: 5s
      retries: 5
```

---

## 5. Migration Procedure for Existing Data

### Scenario: You have PostgreSQL 17 data and need to upgrade to PostgreSQL 18

#### Prerequisites
- Backup of existing database (always recommended)
- Sufficient disk space for backup file
- Docker Compose environment access

#### Step-by-Step Migration

```bash
# 1. Create a backup of the existing database
docker compose exec -T db pg_dump -U postgres -d postgres -F c > backups/postgres_17_backup.dump

# 2. Stop all services to prevent write conflicts
docker compose stop web bot

# 3. Backup the existing volume (optional but recommended)
docker run --rm -v mko_bazuna_postgres_data:/source -v mko_bazuna_postgres_backup:/backup alpine ash -c "cp -a /source/. /backup/"

# 4. Update docker-compose.yml
#    Change volume mount from /var/lib/postgresql/data to /var/lib/postgresql

# 5. Remove the old volume (data will be restored from dump)
docker volume rm mko_bazuna_postgres_data

# 6. Create a fresh volume
docker volume create mko_bazuna_postgres_data

# 7. Start the new PostgreSQL 18 container
docker compose up -d db

# 8. Wait for container to be healthy
docker compose ps db

# 9. Copy backup file into container
docker cp backups/postgres_17_backup.dump mko_bazuna-db-1:/tmp/backup.dump

# 10. Restore the database
docker compose exec -T db pg_restore \
    --clean \
    --if-exists \
    -U postgres \
    -d postgres \
    /tmp/backup.dump

# 11. Run ANALYZE to rebuild query planner statistics
docker compose exec -T db psql -U postgres -d postgres -c "ANALYZE;"

# 12. Start other services
docker compose start web bot

# 13. Verify everything works
docker compose logs -f web | head -20
```

---

## 6. Error Messages and Troubleshooting

### Common Error: "no such file or directory"

```
error mounting "/host/path/pgdata" to rootfs at "/var/lib/postgresql/data": 
change mount propagation through procfd: open o_path procfd: 
open /docker/rootfs/var/lib/postgresql/data: no such file or directory: unknown
```

**Cause:** Mounting at `/var/lib/postgresql/data` when using PostgreSQL 18+ image.

**Solution:** Change volume mount to `/var/lib/postgresql`.

---

### Common Error: "database file is version 18, but this version of PostgreSQL is 17"

**Cause:** Starting PostgreSQL 18 data with PostgreSQL 17 binary (or vice versa).

**Solution:** Perform a dump/restore migration, or use `pg_upgrade` if both versions are available.

---

## 7. Key Files in This Project

| File | Current State | Required Change |
|------|--------------|-----------------|
| `docker-compose.yml` | Uses `/var/lib/postgresql/data` | Change to `/var/lib/postgresql` |
| `docker-compose.test.yml` | No persistent volume | No change needed |
| `docker-compose.dev.override.yml` | No DB volume override | No change needed |

**Current project configuration (docker-compose.yml, line 14):**
```yaml
volumes:
  - postgres_data:/var/lib/postgresql/data
```

**Should be:**
```yaml
volumes:
  - postgres_data:/var/lib/postgresql
```

---

## 8. Migration Checklist

- [ ] Create backup of existing PostgreSQL 17 data
- [ ] Stop all application services (web, bot)
- [ ] Update `docker-compose.yml` volume path
- [ ] Remove old volume or rename for safety
- [ ] Create new volume with correct path
- [ ] Start PostgreSQL 18 container
- [ ] Restore data from dump
- [ ] Run `ANALYZE` on restored database
- [ ] Verify migrations are applied
- [ ] Start application services
- [ ] Test application functionality
- [ ] Monitor logs for errors

---

## 9. References

### Primary Sources
1. **Docker Hub PostgreSQL Documentation**: https://hub.docker.com/_/postgres
2. **GitHub PR #1259**: https://github.com/docker-library/postgres/pull/1259
3. **GitHub Issue #1370**: https://github.com/docker-library/postgres/issues/1370

### Secondary Sources
1. **Metepros Blog**: "Upgrading to PostgreSQL 18 in Docker: A Crucial Change You Need To Be Aware Of"
2. **Redis Thoughts Blog**: "Upgrade PostgreSQL from 17 to 18 on Docker"
3. **BloodHound CE Upgrade Scripts**: Reference implementation for automated migration

### Related Documentation
- [Docker Deployment Guide](./docker-deployment.md)
- [Database Restore Runbook](./restore.md)

---

## 10. Confidence Assessment

| Item | Confidence Level | Source |
|------|-----------------|--------|
| Volume path change | HIGH | Official Docker Hub docs, PR #1259 |
| PGDATA path change | HIGH | PR #1259, Docker Hub docs |
| Migration procedure | HIGH | Multiple community guides, PR discussion |
| Error message causes | HIGH | GitHub issues, user reports |

---

*This document is based on official PostgreSQL Docker image documentation and community migration guides as of July 2026. PostgreSQL 18+ is currently in stable release, and these changes are permanent.*