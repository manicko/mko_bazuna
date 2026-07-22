---
id: restore
domain: ops
tags:
  - backup
  - restore
  - database
  - operations
related:
  - docker-deployment
---

## Purpose

Database restore runbook for recovering from backups.

## Database Restore Runbook

This document describes the procedure for restoring the Mko Bazuna database from a backup.

## Prerequisites

- Backup file exists in `./backups/` directory
- Docker compose environment is running (or can be started)
- Environment variables `POSTGRES_USER`, `POSTGRES_DB` are configured in `.env`

## Automated Backup Service

When running in production with the backup profile enabled, backups run automatically daily:

```bash
# Start production with backup service
docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile backup up -d
```

The backup service uses the `postgres:18-alpine` image and connects directly to the `db` service. It:
- Runs `pg_dump -F c` (custom format)
- Stores backups to `./backups/dump_YYYYMMDD.dump`
- Prunes backups older than 7 days
- Runs every 24 hours in a loop

## Manual Backup

For on-demand backups, use the Makefile target:

```bash
make backup
```

This creates a timestamped backup in `./backups/` with format `dump_YYYYMMDD_HHMMSS.dump`.

## Identify Backup File

List available backups:

```bash
ls -la ./backups/
```

Manual backup files use: `dump_YYYYMMDD_HHMMSS.dump`
Automated backup files use: `dump_YYYYMMDD.dump`

## Prerequisites Check

Before restore, verify:

1. The backup file exists and is readable
2. The database service is healthy:

```bash
docker compose ps db
```

3. Stop web and bot services to prevent write conflicts:

```bash
docker compose stop web bot
```

## Restore Procedure

### Option A: Manual Restore (Recommended for Production)

```bash
# Set environment variables for the restore
export POSTGRES_USER=$(grep POSTGRES_USER .env | cut -d= -f2)
export POSTGRES_DB=$(grep POSTGRES_DB .env | cut -d= -f2)

# Perform the restore
docker compose exec -T db pg_restore \
    --clean \
    --if-exists \
    -U $POSTGRES_USER \
    -d $POSTGRES_DB \
    ./backups/<BACKUP_FILE_NAME>
```

Example with actual file:

```bash
docker compose exec -T db pg_restore \
    --clean \
    --if-exists \
    -U postgres \
    -d postgres \
    ./backups/dump_20250719_143022.dump
```

### Option B: Using Makefile Target

```bash
make restore BACKUP_FILE=./backups/dump_20250719_143022.dump
```

## Post-Restore Steps

1. Start services:

```bash
docker compose start web bot
```

2. Verify database connectivity:

```bash
docker compose exec web python -c "import django; django.setup(); from django.db import connection; print(connection.status)"
```

3. Check migrations are applied:

```bash
docker compose run --rm migrate
```

## Troubleshooting

### Restore Fails with "Role does not exist"

Ensure `POSTGRES_USER` matches the database role. The default is `postgres`.

### Restore Fails with "Database does not exist"

Ensure `POSTGRES_DB` matches the database name. The default is `postgres`.

### Permission Denied on Backup File

Ensure the backup file is accessible in the container context. The `./backups/` directory must be relative to the docker-compose project root.

### Disk Space Exhaustion

Monitor available space before restore:

```bash
df -h ./backups/
```

Backups use custom format (`-F c`) which is compressed but still requires space for decompression during restore.

## Backup Retention

Backups older than 7 days are automatically purged:
- By the Makefile `prune-backups` target (manual)
- By the backup service container (automatic, runs daily cleanup)

To manually clean old backups:

```bash
make prune-backups
```

## Related Documentation

- [Task Definition](../.ai/tasks/done/TASK_014_docker_backup_DONE.yaml)
- [Makefile Backup Target](../../Makefile) - Manual backup automation
- [PgBouncer Configuration](../docker-compose.prod.yml) - If using connection pooling, restore connects directly to db, bypassing PgBouncer
- [CI Pipeline](../../.github/workflows/ci.yml) - No backup testing in CI (ephemeral environment)