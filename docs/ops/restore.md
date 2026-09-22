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
- Environment variables `POSTGRES_USER`, `POSTGRES_DB` are configured in `.env.dev`

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

> ⚠️ **WARNING: This targets the LIVE production database.** It will overwrite the
> current contents of `bazuna_db` with the backup data. For non-production recovery
> exercises, testing backup integrity, or DR drills, use
> [Isolated Restore Target](#isolated-restore-target) and `make restore-test` instead.

### Option A: Manual Restore (Recommended for Production)

```bash
# Set environment variables for the restore
export POSTGRES_USER=$(grep POSTGRES_USER .env.dev | cut -d= -f2)
export POSTGRES_DB=$(grep POSTGRES_DB .env.dev | cut -d= -f2)

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

## Isolated Restore Target

For backup integrity validation, DR drills, or any non-production recovery exercise, restore
into a **fully isolated** PostgreSQL instance that never touches the live `postgres_data` volume
or the `bazuna_db` database. This uses `docker run` directly (not `docker compose`) so there
is zero risk of colliding with the production stack.

### Pattern

```bash
# 1. Create a throwaway named volume for data
docker volume create mko-bazuna-restore-data

# 2. Create a throwaway network
docker network create mko-bazuna-restore-net

# 3. Start postgres:18-alpine in detached mode with an isolated DB
docker run --rm -d \
    --name restore-db \
    --network mko-bazuna-restore-net \
    -v mko-bazuna-restore-data:/var/lib/postgresql \
    -v "$(pwd)/backups:/backups:ro" \
    -e POSTGRES_DB=bazuna_restore \
    -e POSTGRES_USER=restore_user \
    -e POSTGRES_PASSWORD=restore_pass \
    -e POSTGRES_HOST_AUTH_METHOD=trust \
    postgres:18-alpine

# 4. Wait for readiness, then restore
docker exec restore-db pg_isready -U restore_user -d bazuna_restore
docker exec restore-db pg_restore --clean --if-exists -U restore_user -d bazuna_restore -F c /backups/dump_FILE.dump

# 5. Smoke test
docker exec restore-db psql -U restore_user -d bazuna_restore -c "\dt"
docker exec restore-db psql -U restore_user -d bazuna_restore -c "SELECT COUNT(*) FROM ads_ad;"

# 6. Tear down
docker stop restore-db && docker rm -f restore-db
docker volume rm mko-bazuna-restore-data
docker network rm mko-bazuna-restore-net
```

### Key points

- **Never touches `postgres_data` or `bazuna_db`** — the isolated DB is `bazuna_restore`.
- **Volume path** — PG18 uses `/var/lib/postgresql` (not the legacy `/var/lib/postgresql/data`). Mount
  the restore volume at `/var/lib/postgresql`.
- **`POSTGRES_HOST_AUTH_METHOD=trust`** — allows passwordless local connections via `psql` inside
  the container, simplifying the smoke-test step. This is safe because the container is on an
  isolated network with no published ports.
- **No `--no-sync` on `pg_restore`** — `pg_restore` has no `--no-sync` flag. The `--no-sync` flag
  is only valid for `pg_dump` (where it is already used in `make backup` and the prod backup service).
- **The automated `make restore-test` target** wraps this pattern with cleanup-on-exit via a trap
  (see [Restore-Test Procedure](#restore-test-procedure) below).

## Recovery Point Objective (RPO)

- **RPO = 24 hours.** Backups are produced by a daily `pg_dump -F c` job in the production backup
  service (`docker-compose.prod.yml`, `--profile backup`). The service loops with `sleep 86400`,
  producing one dump per day at `./backups/dump_YYYYMMDD.dump`.
- **Retention = 7 days.** The backup service prunes files older than 7 days via:
  ```bash
  find /backups -name 'dump_*.dump' -mtime +7 -delete
  ```
  The Makefile `prune-backups` target runs the same retention logic for manual backups.
- **No WAL archiving / PITR.** There is no WAL archive, no `archive_command`, and no base-backup
  pipeline. Sub-24h RPO is **not** possible without adding WAL archiving and a recovery timeline
  mechanism. The `deploy.yml` workflow (B4) now includes a pre-deploy backup step that captures a
  timestamped dump before each deployment, providing a recovery point at the last deploy — but this
  is not a substitute for WAL archiving needed for sub-24h RPO.
- **Live data risk.** Any writes made within the last 24 hours before a failure are lost. Schedule
  the backup to run close to a low-traffic window if tighter RPO is desired.

## Recovery Time Objective (RTO)

- **Target RTO ≈ 4 hours.** This is a target, not an SLA. Actual time depends on backup size and
  host I/O throughput.
  - Backup retrieval / copy to restore host: ~30 min
  - `pg_restore --clean --if-exists` (multi-GB custom-format dump): ~60–90 min
  - `manage.py migrate --plan` (verify pending migrations): ~5 min
  - Smoke tests (connectivity, schema, data, schema list): ~10 min
- **DB-size dependent.** The restore target (`pg_restore`) is I/O bound. A 10 GB database may
  restore in ~60 min; a 100 GB database could take 4+ hours.
- **No automated failover.** There is no standby replica; restore is a manual process that
  requires an operator to run `make restore-test` or the full `make restore` procedure.
- **Quarterly review.** RTO targets should be exercised and recalibrated quarterly via the
  restore-test procedure.

## Restore-Test Procedure

Monthly validation of backup integrity using the isolated restore target.

### Cadence

Run on the first Monday of each month, or after any significant schema change.

### Procedure

```bash
# 1. Identify the most recent backup
ls -la ./backups/

# 2. Restore-test into an isolated DB (never touches production)
make restore-test BACKUP_FILE=./backups/dump_20250719_143022.dump
```

The `make restore-test` target:
1. Validates `BACKUP_FILE` is provided and exists
2. Creates an isolated named volume (`mko-bazuna-restore-<timestamp>`)
3. Creates an isolated network (`mko-bazuna-restore-net-<timestamp>`)
4. Starts `postgres:18-alpine` with `POSTGRES_HOST_AUTH_METHOD=trust` and an isolated DB
   (`bazuna_restore`, user: `restore_user`)
5. Waits up to 30 s for `pg_isready` (connectivity check)
6. Runs `pg_restore --clean --if-exists -F c` into the isolated DB
7. Runs four smoke checks:
   - **Connectivity:** `pg_isready`
   - **Schema (table count):** `SELECT count(*) FROM information_schema.tables WHERE table_schema='public'`
   - **Data (row count):** `SELECT count(*) FROM ads_ad`
   - **Schema list:** `\dn`
8. Tears down all isolated resources (container, volume, network) via an `EXIT` trap

### Known limitation

`manage.py migrate --plan` is **not** run inside the Makefile target — it requires the full
production app image and Django settings stack. This check is better suited for the deploy
workflow (`deploy.yml`) where the app container is available. The restore-test smoke tests
verify database-level integrity only; Django ORM-level migration compatibility must be verified
separately during a deployment dry-run.

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