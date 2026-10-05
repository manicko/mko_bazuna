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
- Environment variables `POSTGRES_USER`, `POSTGRES_DB` are configured in `.env.prod`

> **Every production invocation below carries `--env-file .env.prod` and both
> `-f docker-compose.yml -f docker-compose.prod.yml`.** `docker-compose.yml`
> and `docker-compose.prod.yml` use mandatory interpolation
> (`${POSTGRES_USER:?…}`, `${DJANGO_SECRET_KEY:?…}`), so a `docker compose`
> invocation without `--env-file` aborts during config rendering — including
> read-only `ps`, `stop` and `exec`. Omitting `-f docker-compose.prod.yml`
> silently runs the **dev** configuration, which is quieter than the abort
> (12-OPS-006). Read `POSTGRES_USER` / `POSTGRES_DB` from `.env.prod`, never
> `.env.dev`: the dev values name the development database.

## Automated Backup Service

When running in production with the backup profile enabled, backups run automatically daily:

```bash
# Start production with backup service
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml --profile backup up -d
```

The backup service uses the `postgres:18.6-alpine` image and connects directly to the `db` service. It:
- Runs `pg_dump -F c` (custom format)
- Stores backups to `./backups/dump_YYYYMMDD_HHMMSS.dump`
- Prunes backups older than 7 days
- Runs every 24 hours in a loop

## Manual Backup

For on-demand backups, use the Makefile target:

```bash
make backup
```

This creates a timestamped backup in `./backups/` with format `dump_YYYYMMDD_HHMMSS.dump`.

> **`make backup` reads `.env.dev` and runs against the dev compose files**, so it
> backs up the **development** database. For the production backup, rely on the
> `backup` service (above) or run the `pg_dump` against `.env.prod`.

## Identify Backup File

List available backups:

```bash
ls -la ./backups/
```

Manual backup files use: `dump_YYYYMMDD_HHMMSS.dump`
Automated backup files use: `dump_YYYYMMDD_HHMMSS.dump`

## Prerequisites Check

Before restore, verify:

1. The backup file exists and is readable
2. The database service is healthy:

```bash
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml ps db
```

3. Stop web and bot services to prevent write conflicts:

```bash
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml stop web bot
```

## Restore Procedure

> ⚠️ **WARNING: This targets the LIVE production database.** It will overwrite the
> current contents of `bazuna_db` with the backup data. For non-production recovery
> exercises, testing backup integrity, or DR drills, use
> [Isolated Restore Target](#isolated-restore-target) and `make restore-test` instead.

### Option A: Manual Restore (Recommended for Production)

```bash
# Set environment variables for the restore from the PRODUCTION env file.
# Reading .env.dev here yields the development database's credentials.
export POSTGRES_USER=$(grep '^POSTGRES_USER=' .env.prod | cut -d= -f2)
export POSTGRES_DB=$(grep '^POSTGRES_DB=' .env.prod | cut -d= -f2)

# Perform the restore. The dump lives on the HOST, and the `db` service mounts
# only `postgres_data` — no `./backups` — so the file is streamed in on stdin.
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml \
    exec -T db pg_restore \
    --clean \
    --if-exists \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" \
    < ./backups/<BACKUP_FILE_NAME>
```

Example with actual file:

```bash
export POSTGRES_USER=$(grep '^POSTGRES_USER=' .env.prod | cut -d= -f2)
export POSTGRES_DB=$(grep '^POSTGRES_DB=' .env.prod | cut -d= -f2)

docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml \
    exec -T db pg_restore \
    --clean \
    --if-exists \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" \
    < ./backups/dump_20250719_143022.dump
```

### Option B: Using the Makefile Target

`make restore` is a **dev-stack** target: it sources `.env.dev` and runs against
the dev compose files (`COMPOSE_FILES`), so it restores the **development**
database. It must not be used to restore production.

```bash
# DEV ONLY — restores the development database
make restore BACKUP_FILE=./backups/dump_20250719_143022.dump
```

For a **production** restore there is no Makefile target; use Option A above,
which names `.env.prod` and both production compose files explicitly.

## Post-Restore Steps

1. Start services:

```bash
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml start web bot
```

2. Verify database connectivity:

```bash
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml exec web python -c "import django; django.setup(); from django.db import connection; print(connection.status)"
```

3. Check migrations are applied:

```bash
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml run --rm migrate
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

# 3. Start postgres:18.6-alpine in detached mode with an isolated DB
docker run --rm -d \
    --name restore-db \
    --network mko-bazuna-restore-net \
    -v mko-bazuna-restore-data:/var/lib/postgresql \
    -v "$(pwd)/backups:/backups:ro" \
    -e POSTGRES_DB=bazuna_restore \
    -e POSTGRES_USER=restore_user \
    -e POSTGRES_PASSWORD=restore_pass \
    -e POSTGRES_HOST_AUTH_METHOD=trust \
    postgres:18.6-alpine

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

> **Conditional.** The figures below assume three preconditions that are **not
> all met today** (12-OPS-006): (1) the daily backup job is actually running,
> (2) an off-host copy of the newest dump exists, and (3) a real-artifact
> restore drill has passed. Until all three hold, this is a **target**, not a
> guarantee — see [Restore-Test Procedure](#restore-test-procedure).

- **RPO = 24 hours.** Backups are produced by a daily `pg_dump -F c` job in the production backup
  service (`docker-compose.prod.yml`, `--profile backup`). The service loops with `sleep 86400`,
  producing one dump per day at `./backups/dump_YYYYMMDD_HHMMSS.dump`.
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

> **Conditional**, for the same three preconditions as the RPO above: the
> figures assume the newest dump is on-host and restore-tested (12-OPS-006).

- **Target RTO ≈ 4 hours.** This is a target, not an SLA. Actual time depends on backup size and
  host I/O throughput.
  - Backup retrieval / copy to restore host: ~30 min
  - `pg_restore --clean --if-exists` (multi-GB custom-format dump): ~60–90 min
  - `manage.py migrate --plan` (verify pending migrations): ~5 min
  - Smoke tests (connectivity, schema, data, schema list): ~10 min
- **DB-size dependent.** The restore target (`pg_restore`) is I/O bound. A 10 GB database may
  restore in ~60 min; a 100 GB database could take 4+ hours.
- **No automated failover.** There is no standby replica; restore is a manual process that
  requires an operator to run `make restore-test` (validation) or the production restore
  procedure in [Option A](#option-a-manual-restore-recommended-for-production). **`make
  restore` is dev-only and must not be used for production.**
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
4. Starts the `restore-test` target's postgres image with `POSTGRES_HOST_AUTH_METHOD=trust` and an isolated DB
   (`bazuna_restore`, user: `restore_user`)
5. Waits up to 30 s for `pg_isready` (connectivity check)
6. Runs `pg_restore --clean --if-exists -F c` into the isolated DB
7. Runs five smoke checks that **assert**, not merely print (an empty or partial
   restore fails the target with a non-zero exit):
   - **Connectivity:** `pg_isready`
   - **Schema (table count):** `SELECT count(*) FROM information_schema.tables WHERE table_schema='public'` — must be `> 0`
   - **Migrations:** `SELECT count(*) FROM django_migrations` — the table must exist and be non-empty, proving the dump is a migrated database rather than a bare restore
   - **Data (row count):** `SELECT count(*) FROM ads_ad` — must be `> 0`
   - **Schema list:** `\dn`
8. Optionally runs `migrate --plan --check` against the restored DB using the
   production app image (when `APP_IMAGE` is provided) — verifies Django ORM-level
   migration compatibility against the restored schema
9. Tears down all isolated resources (container, volume, network) via an `EXIT` trap

### What the drill proves, and what it does NOT (12-OPS-004)

The drill now proves something about a **real restore**: it fails on an empty or
partial restore, asserts `django_migrations` is present, and asserts `ads_ad` has
rows. In CI the dump it restores is still generated from the CI database three
steps earlier, so it is labelled an **additional** smoke test, not a production
artifact.

**OPEN NAMED TASK — off-host real-artifact acquisition.** Restoring the newest
**off-host production** dump is **not implemented**, because it is not
implementable from this repository: the `backup` container is
`postgres:18.6-alpine` with `cap_drop: [ALL]` and `read_only: true` and tmpfs on
`/tmp` only, so it has **no object-storage client binary**; no storage SDK is in
`pyproject.toml`; and any new credential must land in `ALLOWED_ENV_VARS` plus all
four `.env.*.example` files in one commit. This was re-opened with the
implementability finding on 2026-10-04 and is tracked as the named infrastructure
task *"Configure an off-host push from the `backup` service (credentials +
retention policy + stated restore path) and make the drill restore the newest
production artifact."* Until it lands, the RPO/RTO preconditions below remain
unmet.

### Migrate --plan --check (optional)

`manage.py migrate --plan --check` is run when `APP_IMAGE` is provided (via the
`APP_IMAGE` Makefile variable). The step launches a one-shot container from the
production app image on the isolated network (hostname `restore-db`), connecting
to the restored DB with `DJANGO_BUILD=1` and `DJANGO_SETTINGS_MODULE=config.settings.prod`
to bypass secret-validation guards. The `--check` flag causes a non-zero exit if
pending migrations exist — the CI backup is generated from a fully-migrated DB
(after `bootstrap_reference_data`), so the plan is empty and the step succeeds.
CI provides a **recorded known-good** image automatically (the concrete
`RESTORE_APP_IMAGE_TAG` pinned in `.github/workflows/restore-test.yml`, not a
moving `github.sha`); manual runs skip this step unless `APP_IMAGE` is set
explicitly.

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
- [CI Pipeline](../../.github/workflows/ci.yml) - CI workflow
- [Restore Test Workflow](../../.github/workflows/restore-test.yml) - Monthly automated restore-test validation (first Monday of each month)