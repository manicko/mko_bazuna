# Server Backup Implementation Plan (Updated)

## Overview

This plan implements server-side backup for Mko Bazuna using the **pg_dump + Restic + Backblaze B2** approach as recommended in the research ([research_updated.md](research_updated.md), §12).

**Critical context:** The original `plan.md` (552 lines) described an implementation that was **never built**. The current `backup` service in `docker-compose.prod.yml` (lines 65–97) is a bare `postgres:18-alpine` container running an inline `/bin/sh -c` loop that executes `pg_dump -F c` with 7-day local retention only — no Restic, no B2, no media backup, no encryption, no offsite storage, no verification, and no secrets management ([CA §5.1][AC §3.1]).

This updated plan treats the upgrade path as **new work against the actual current state**: it replaces the bare `postgres:18-alpine` backup service with a custom Restic-enabled image, adds the supporting scripts, env vars, Makefile targets, and documentation as new artifacts, and corrects every stale or incorrect claim from the old plan.

**Key decisions** (from [BP §1.2][BP §4.1][AC §3.3][AC §3.5][AC §3.6]):

| Concern | Old Plan | Updated Plan |
|---------|----------|-------------|
| Backup image | `docker/Dockerfile.backup` (never created) | Create `docker/Dockerfile.backup` — Alpine 3.20 + Restic v0.19.1 + postgresql-client 18 |
| Restic version | 0.18 | 0.19.1 ([BP §4.1]) |
| B2 backend | Native `b2:` scheme, `s3.us-west-004` | S3-compatible `s3:` gateway at `s3.us-west-002.backblazeb2.com` ([BP §3.3][AC §3.5]) |
| Secrets management | Docker Swarm `secrets:` (not applicable) | File-mounted `RESTIC_PASSWORD_FILE` + `env_file` ([BP §6][AC §3.1][AC §3.6]) |
| Media volume path | `/media` (wrong — file does not exist) | `/app/media` (matches `web`/`bot` mount; see [CA §2.1][CA §2.4][AC §3.1]) |
| pg_dump flags | `pg_dump -F c` (bare) | `--format=custom --jobs=4 --no-owner --no-privileges --if-exists --clean` ([BP §1.2][AC §3.5]) |
| Retention | `--keep-daily 7 --keep-weekly 4 --prune` | `--keep-daily 7 --keep-weekly 4 --keep-monthly 12 --keep-yearly 3 --prune` + weekly `restic check --read-data-subset=1/7` ([BP §4.1][AC §3.5]) |
| Encryption | Restic AES-256 only | Restic AES-256 + B2 SSE-S3 bucket encryption ([BP §8.2][AC §3.6]) |
| Monitoring | `hc.pfelya` (inconsistent) | Healthchecks.io via `hc-ping.com` UUID pings ([BP §7.1][AC §3.5]) |
| Compose project | No project-name scoping | `mko-bazuna-dev`/`mko-bazuna-test` isolation via Makefile target-specific exports ([CA §1.3][AC §3.7]) |
| Prod deploy | `docker-compose.yml` (root only) | `docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml` ([CA §1.4][AC §3.7]) |
| DB scope | 9 tables (research.md §2.1) | 31 tables ([CA §6.1][AC §3.3]) |
| GDPR sweeps | Not accounted for | 4 hourly scheduler sweeps with advisory locks; 30-day consent hard-delete, 120-day deleted-ad purge ([CA §3.3][CA §6.3][AC §3.3]) |

---

## Implementation Stages

```
Research (Done) → Planning (Current) → Implementation → Validation
```

Source documents: `[CA]` = current-architecture-report.md; `[BP]` = research-best-practices-report.md; `[AC]` = audit-conclusion.md.

---

## Phase 1: Configuration Updates

### Task 1.1: Add backup env vars to `.env.docker.example`

**Priority:** High  
**Effort:** Trivial  
**Files:** `.env.docker.example` (root, 73 lines, tracked in git — [CA §4.1])

The current `.env.docker.example` (73 lines, 23 variables — [CA §4.1]) contains **none** of the six backup-related variables that the old plan's 25-line stale template (`server_backup/.env.docker.example`, 25 lines) proposed. This task adds the full set of backup configuration variables as **recommended additions** to the root template.

**Variables to add** (appended after the existing `FIX_PERMISSIONS`/`SKIP_ENV_CHECK` block, lines 68–73):

```env
# ====================== Backup / Disaster Recovery ======================
# Backblaze B2 application key (create least-privilege key scoped to the backup bucket).
# See docs/ops/backup-operations.md §3 for bucket setup with SSE-S3.
B2_KEY_ID=
B2_APP_KEY=

# Restic repository password — stored on the host at /opt/mko-bazuna/secrets/restic_repo_key
# with chmod 600, bind-mounted into the backup container at this path.
# NOT a plaintext password in the env file — this is the in-container mount path only.
RESTIC_PASSWORD_FILE=/run/secrets/restic_repo_key

# B2 S3-compatible gateway endpoint (Restic v0.19.1 requires s3: scheme, not native b2: — BP §3.3)
BACKUP_S3_ENDPOINT=s3.us-west-002.backblazeb2.com

# B2 bucket name for Restic repository (must have SSE-S3 enabled — BP §8.2)
BACKUP_BUCKET=mko-bazuna-backups

# Restic retention policy (BP §4.1)
RESTIC_RETENTION_DAILY=7
RESTIC_RETENTION_WEEKLY=4
RESTIC_RETENTION_MONTHLY=12
RESTIC_RETENTION_YEARLY=3

# Healthchecks.io UUID for backup job monitoring (BP §7.1)
HEALTHCHECK_UUID=
```

**Rationale:** The old plan's 25-line template used `RESTIC_PASSWORD=` (plaintext, inline) and `B2_KEY_ID`/`B2_APP_KEY` directly — these are now superseded by the file-mounted `RESTIC_PASSWORD_FILE` approach ([AC §3.6], [BP §6]). The stale template at `.ai/plans/server_backup/.env.docker.example` is left unmodified per task constraints; this task integrates the corrected recommendations into the living root template.

**Verification:** `grep -c BACKUP_BUCKET .env.docker.example` returns 1 after the edit.

---

### Task 1.2: Create host-side restic password file and B2 bucket

**Priority:** High  
**Effort:** Small  
**Dependencies:** None

**Prerequisites:** This task requires an existing Backblaze B2 account.

**Steps:**

1. **Create the restic password file on the host:**
   ```bash
   mkdir -p /opt/mko-bazuna/secrets
   # Generate a strong 32-byte password:
   openssl rand -hex 32 > /opt/mko-bazuna/secrets/restic_repo_key
   chmod 600 /opt/mko-bazuna/secrets/restic_repo_key
   chown 1000:1000 /opt/mko-bazuna/secrets/restic_repo_key
   ```
   The password file is bind-mounted at `/run/secrets/restic_repo_key` inside the backup container ([BP §6.3], [AC §3.6]).

2. **Create the B2 bucket with SSE-S3:**
   ```bash
   # Install B2 CLI: pip install b2
   b2 create-bucket mko-bazuna-backups allPublic \
       --default-sse aws/sse \
       --sse-algorithm-aws-sse aws/sse
   ```
   SSE-S3 adds a server-side encryption layer on top of Restic's client-side AES-256 ([BP §8.2]).

3. **Create a least-privilege B2 application key:**
   ```bash
   b2 create-key --bucket mko-bazuna-backups \
       --capabilities listBuckets,writeFiles,readFiles,deleteFiles,hideFileBackups \
       mko-bazuna-restic
   ```
   This limits blast radius if the key is leaked ([BP §8.3]).

4. **Record the password file content independently** (e.g., in a password manager) — losing the restic password means data is unrecoverable ([BP §4.2]).

**Verification:** `restic init --repo s3:s3.us-west-002.backblazeb2.com/mko-bazuna-backups` succeeds using `RESTIC_PASSWORD_FILE=/opt/mko-bazuna/secrets/restic_repo_key` and the B2 application key via `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`.

---

## Phase 2: Docker Compose Configuration

### Task 2.1: Create `docker/Dockerfile.backup`

**Priority:** High  
**Effort:** Small  
**File:** `docker/Dockerfile.backup` (NEW — does not exist on filesystem, confirmed by audit [AC §3.1])

The current backup service uses `image: postgres:18-alpine` directly ([CA §5.1], `docker-compose.prod.yml` line 68). This task creates a dedicated multi-stage Dockerfile that produces a minimal Alpine image with Restic v0.19.1 and PostgreSQL client tools.

```dockerfile
# Multi-stage backup image: Alpine + Restic 0.19.1 + PostgreSQL client
FROM alpine:3.20 AS base

# Install: postgresql-client 18 (for pg_dump/pg_restore/pg_isready),
# restic 0.19.1 (downloaded binary — Alpine repos may lag),
# curl (for Healthchecks.io pings), bash (for scripts using [[ ]] extensions)
RUN apk add --no-cache --no-progress \
    postgresql-client~>18 \
    curl \
    bash \
    coreutils

# Download Restic v0.19.1 binary (pinned for reproducibility — BP §4.1)
ARG RESTIC_VERSION=0.19.1
RUN curl -fsSL "https://github.com/restic/restic/releases/download/v${RESTIC_VERSION}/restic_${RESTIC_VERSION}_linux_amd64.bz2" \
      -o /tmp/restic.bz2 \
    && bzip2 -d /tmp/restic.bz2 \
    && mv /tmp/restic_${RESTIC_VERSION}_linux_amd64 /usr/local/bin/restic \
    && chmod +x /usr/local/bin/restic \
    && rm -f /tmp/restic_${RESTIC_VERSION}_linux_amd64.bz2 \
    && restic version

# Healthchecks.io ping helper
ENV HC_PING_URL=""

FROM base AS backup
COPY scripts/backup.sh /app/scripts/backup.sh
COPY scripts/restore.sh /app/scripts/restore.sh
COPY scripts/verify-backup.sh /app/scripts/verify-backup.sh
RUN chmod +x /app/scripts/*.sh
ENTRYPOINT ["/app/scripts/backup.sh"]
```

**Key details:**
- Restic v0.19.1 binary downloaded from GitHub releases (not from `apk`) because Alpine's repos may ship an older version ([BP §4.1]).
- The image uses the same `postgresql-client` major version (18) as the `db` service ([CA §5.1], compose line 68).
- All three scripts are copied and made executable so `docker compose run --rm backup <script>` can execute any of them.

**Source references:** Alpine 3.20 ([CA §5.1]); postgres:18-alpine image tag ([CA §1.2] table, compose line 68); 3-stage Dockerfile pattern for the app image ([CA §1.5]).

---

### Task 2.2: Replace backup service in `docker-compose.prod.yml`

**Priority:** High  
**Effort:** Medium  
**File:** `docker-compose.prod.yml` (lines 65–97 — the current bare `postgres:18-alpine` service)  
**Dependencies:** Task 2.1 (Dockerfile.backup)

Replace the current backup service definition (lines 65–97) with a Restic-enabled version. The replacement preserves the `profiles: ["backup"]` gate ([CA §5.1]), the `depends_on: db: condition: service_healthy`, and `restart: unless-stopped`, but upgrades every other aspect.

**Replace with:**
```yaml
  # Backup service: pg_dump + Restic → Backblaze B2 with media and DB backups.
  # Opt-in via --profile backup. Upgrades the bare postgres:18-alpine service
  # to a custom Restic-enabled image (docker/Dockerfile.backup).
  backup:
    build:
      context: .
      dockerfile: docker/Dockerfile.backup
    environment:
      - POSTGRES_HOST=db
      - POSTGRES_PORT=5432
      - POSTGRES_DB=${POSTGRES_DB:?POSTGRES_DB must be set}
      - POSTGRES_USER=${POSTGRES_USER:?POSTGRES_USER must be set}
      - PGPASSWORD=${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}
      - RESTIC_PASSWORD_FILE=/run/secrets/restic_repo_key
      - RESTIC_REPOSITORY=s3:${BACKUP_S3_ENDPOINT:-s3.us-west-002.backblazeb2.com}/${BACKUP_BUCKET:-mko-bazuna-backups}
      - AWS_ACCESS_KEY_ID=${B2_KEY_ID:?B2_KEY_ID must be set}
      - AWS_SECRET_ACCESS_KEY=${B2_APP_KEY:?B2_APP_KEY must be set}
      - HEALTHCHECK_UUID=${HEALTHCHECK_UUID:-}
      - POSTGRES_BACKUP_FLAGS=--format=custom --jobs=4 --no-owner --no-privileges --if-exists --clean
    env_file:
      - .env.docker
    volumes:
      - ./backups:/backups
      - media_volume:/app/media:ro
      - /opt/mko-bazuna/secrets/restic_repo_key:/run/secrets/restic_repo_key:ro
    depends_on:
      db:
        condition: service_healthy
    restart: unless-stopped
    profiles:
      - backup
```

**Changes from current service** ([CA §5.1], compose lines 65–97):

| Aspect | Current | Updated |
|--------|---------|---------|
| Image | `postgres:18-alpine` (line 68) | `build: context: . dockerfile: docker/Dockerfile.backup` |
| Command | Inline `/bin/sh -c` pg_dump loop (lines 77–91) | `scripts/backup.sh` (via Dockerfile ENTRYPOINT) |
| pg_dump flags | `-F c` only (line 86) | `--format=custom --jobs=4 --no-owner --no-privileges --if-exists --clean` ([BP §1.2]) |
| Media backup | Not mounted ([CA §5.1] §Gaps) | `media_volume:/app/media:ro` (correct path, [CA §2.1] lines 155–156) |
| Offsite | None | Restic S3 backend to B2 ([BP §3.3]) |
| Encryption | None | Restic AES-256 + B2 SSE-S3 ([BP §8.1][BP §8.2]) |
| Secrets | None | File-mounted `RESTIC_PASSWORD_FILE` (not Docker Swarm secrets — [BP §6][AC §3.1]) |
| Monitoring | None | Healthchecks.io UUID ping ([BP §7.1]) |
| Password source | N/A | `env_file: .env.docker` + bind-mounted password file |

**Source references:** Existing backup service definition (`docker-compose.prod.yml` lines 65–97); media volume mount paths (`docker-compose.yml` lines 160, 187, 133 for web/bot/seed; line 202 for nginx at `/media_volume:ro` — [CA §2.1]); env_file pattern from scheduler service (`docker-compose.prod.yml` lines 52–53); prod deploy invocation (`docs/ops/docker-deployment.md` lines 271–275, [CA §1.4]).

---

### Task 2.3: Mount `media_volume` at `/app/media:ro` in backup service

**Priority:** High  
**Effort:** Trivial  
**Dependencies:** Task 2.2

This task is the explicit mount declaration extracted from Task 2.2 for verification tracking. The media volume path **must** be `/app/media` — the old plan used `/media`, which does not exist in any current service ([AC §3.1], [CA §2.1] lines 155–156, [CA §2.4] lines 186–187).

The volume name `media_volume` is defined at the top level of `docker-compose.yml` (line 209) and is project-prefixed at runtime (`mko-bazuna-dev_media_volume` or `mko-bazuna-test_media_volume` — [CA §1.3] line 74). When using `docker-compose.prod.yml`, the default project name (directory name `mko_bazuna`) applies unless `--project-name` is set ([CA §1.3]).

**Verification:** `docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml --profile backup config | grep -A5 media_volume` shows the correct mount.

---

### Task 2.4: Mount restic password file at `/run/secrets/restic_repo_key:ro`

**Priority:** High  
**Effort:** Trivial  
**Dependencies:** Task 1.2 (host-side file creation), Task 2.2 (service definition)

This replaces the old plan's Docker Swarm `secrets:` pattern, which is **not applicable** to single-node Docker Compose ([BP §6.1], [AC §3.1]).

**Approach:** A bind mount from the host file `/opt/mko-bazuna/secrets/restic_repo_key` to the container path `/run/secrets/restic_repo_key` (read-only). The container's `RESTIC_PASSWORD_FILE` env var points to this path.

```yaml
volumes:
  - /opt/mko-bazuna/secrets/restic_repo_key:/run/secrets/restic_repo_key:ro
```

This follows the [BP §6.3] pattern exactly: env var `RESTIC_PASSWORD_FILE` in the env file pointing to a mounted file path, with the actual password stored on the host at `/opt/mko-bazuna/secrets/` (`chmod 600`).

**Source references:** [BP §6.3] recommendation (env_file + file-mounted RESTIC_PASSWORD_FILE); [AC §3.1] Docker Swarm secrets not applicable; [AC §3.6] file-mounted pattern required; `docs/ops/docker-deployment.md` §Environment files (lines 77–84) confirming `.env.docker` is the runtime env file.

---

## Phase 3: Script Implementation

### Task 3.1: Create `scripts/backup.sh`

**Priority:** High  
**Effort:** Medium  
**File:** `scripts/backup.sh` (NEW — does not exist, confirmed by audit [AC §3.4])  
**Dependencies:** Task 2.1 (Dockerfile.backup), Task 2.2 (service), Task 2.3 (media mount), Task 2.4 (password mount), Task 1.2 (B2 bucket)

The script runs inside the `Dockerfile.backup` container in a daily loop (matching the current service's `sleep 86400` pattern — [CA §5.1] line 90). It performs:

1. **Healthchecks.io start ping** — signals job start ([BP §7.3], [AC §3.5])
2. **Wait for PostgreSQL** — `pg_isready` loop (same pattern as current service, [CA §5.1] line 82)
3. **pg_dump** — with upgraded flags: `--format=custom --jobs=4 --no-owner --no-privileges --if-exists --clean` ([BP §1.2], [AC §3.5]); output to `/backups/db_YYYYMMDD_HHMMSS.dump`
4. **Verify dump integrity** — `pg_restore --list` on the dump file ([CA §5.3] gap: current service has no verification)
5. **Restic backup (database)** — `restic backup /backups/db_*.dump` to the B2 S3 gateway ([BP §3.3], [BP §4.1])
6. **Restic backup (media)** — `restic backup /app/media` (filesystem mode, not tar) for per-file deduplication ([BP §4.3])
7. **Restic forget + prune** — `--keep-daily ${RESTIC_RETENTION_DAILY:-7} --keep-weekly ${RESTIC_RETENTION_WEEKLY:-4} --keep-monthly ${RESTIC_RETENTION_MONTHLY:-12} --keep-yearly ${RESTIC_RETENTION_YEARLY:-3} --prune` ([BP §4.1], [AC §3.5])
8. **Weekly deep check** — `restic check --read-data-subset=1/7` on Sundays ([BP §4.1])
9. **Cleanup local staging** — remove `db_*.dump` after successful restic backup (keep 2 days locally for quick restore, matching old plan's `cleanup_local_backups`)
10. **Healthchecks.io success/fail ping** — `curl -fsS --retry 3 https://hc-ping.com/${HEALTHCHECK_UUID}` ([BP §7.1], [AC §3.5])
11. **Sleep 86400** — daily cycle (same as current service, [CA §5.1] line 90)

**Security:** The script reads `RESTIC_PASSWORD_FILE` (not inline password), `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` from env ([BP §6.3], [AC §3.6]). All B2 credentials come from `.env.docker` via compose interpolation ([CA §4.1]).

**Source references:** Current backup service inline script (`docker-compose.prod.yml` lines 80–91); [BP §1.2] pg_dump flags; [BP §4.1] restic retention; [BP §4.3] media backup approach; [BP §7.3] healthcheck pattern; Restic password management ([BP §4.2]).

---

### Task 3.2: Create `scripts/restore.sh`

**Priority:** High  
**Effort:** Medium  
**File:** `scripts/restore.sh` (NEW — does not exist, confirmed by audit [AC §3.4])  
**Dependencies:** Task 2.1 (Dockerfile.backup), Task 2.2 (service)

The old plan's `restore.sh` (plan.md lines 286–349) had three critical bugs that this task fixes:

1. **`postgres`/`postgres` bug:** The old script and `docs/ops/restore.md` (line 104–105) hard-coded `POSTGRES_USER=postgres` and `POSTGRES_DB=postgres`, but the actual runtime uses `bazuna_user`/`bazuna_db` ([CA §4.1], [CA §4.3], [AC §3.4] D6). The updated script reads credentials from environment variables.
2. **Wrong compose files:** The old script used `docker-compose.yml` (root only), missing prod overrides. The updated script uses `docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml` ([CA §1.4], [AC §3.7] G2).
3. **Wrong media path:** The old script used `$MEDIA_DIR:-/media`. The updated script uses `/app/media` ([CA §2.1], [AC §3.1] A2).

**Script outline:**

```bash
#!/bin/bash
set -euo pipefail

# Safety: confirm restore intent
if [ "${CONFIRM_RESTORE:-}" != "yes" ]; then
    echo "ERROR: CONFIRM_RESTORE=yes required"
    echo "Example: make restore-prod BACKUP_FILE=restic://latest/db_20250901.dump"
    exit 1
fi

# Read credentials from environment (NOT hard-coded postgres/postgres)
DB_HOST="${POSTGRES_HOST:-db}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_NAME="${POSTGRES_DB:?POSTGRES_DB must be set}"
DB_USER="${POSTGRES_USER:?POSTGRES_USER must be set}"

# Step 1: List available Restic snapshots
restic snapshots --repo "${RESTIC_REPOSITORY}"

# Step 2: Prompt for snapshot ID to restore from
read -p "Enter snapshot ID to restore: " SNAPSHOT

# Step 3: Stop write services (web, bot) using correct prod compose files
docker compose --env-file .env.docker \
  -f docker-compose.yml -f docker-compose.prod.yml stop web bot

# Step 4: Restore DB from restic snapshot
restic restore "${SNAPSHOT}" \
  --repo "${RESTIC_REPOSITORY}" \
  --target /tmp/restore --include "backups/db_*.dump"

# Step 5: pg_restore with matching flags
pg_restore \
  --no-owner --no-privileges --if-exists --clean --verbose \
  -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" \
  /tmp/restore/backups/db_*.dump

# Step 6: Restore media volume from restic
restic restore "${SNAPSHOT}" \
  --repo "${RESTIC_REPOSITORY}" \
  --target /tmp/restore --include "media/"
# Copy restored files to /app/media (mounted media_volume)
cp -a /tmp/restore/media/. /app/media/
# Fix permissions for uid 1000 (non-root app user — Dockerfile line 149 [CA §1.6])
chown -R 1000:1000 /app/media

# Step 7: Run migrations
docker compose --env-file .env.docker \
  -f docker-compose.yml -f docker-compose.prod.yml run --rm migrate

# Step 8: Start services
docker compose --env-file .env.docker \
  -f docker-compose.yml -f docker-compose.prod.yml start web bot

echo "✓ Full restore completed (DB + media)"
```

**Source references:** Current restore procedure in `docs/ops/restore.md` (lines 80–133); [AC §3.4] D6 (postgres/postgres bug); [AC §3.7] G2 (compose file merge); [CA §2.1] (media path `/app/media`); [CA §1.6] (uid 1000 non-root user); [BP §1.2] (pg_dump flags); [CA §1.4] (prod deploy invocation).

---

### Task 3.3: Create `scripts/verify-backup.sh`

**Priority:** Medium  
**Effort:** Small  
**File:** `scripts/verify-backup.sh` (NEW — does not exist, confirmed by audit [AC §3.4])  
**Dependencies:** Task 2.1 (Dockerfile.backup)

**Script outline:**

```bash
#!/bin/bash
set -euo pipefail

# Verify database dump integrity
echo "=== Verifying database dump integrity ==="
for dump in /backups/db_*.dump; do
    if [ -f "$dump" ]; then
        echo "Checking: $dump"
        pg_restore --list "$dump" > /dev/null && echo "  ✓ Valid" || { echo "  ✗ CORRUPT"; exit 1; }
    fi
done

# Verify Restic repository integrity
echo "=== Verifying Restic repository ==="
restic check --repo "${RESTIC_REPOSITORY}" || { echo "✗ Repository check failed"; exit 1; }
echo "✓ Repository integrity verified"

# List snapshots for audit
echo "=== Available snapshots ==="
restic snapshots --repo "${RESTIC_REPOSITORY}"

echo "Verification complete."
```

**Source references:** [CA §5.3] gap: "NO verification — no pg_restore --list check after dump" ([AC §3.4] D3, D8); [BP §4.1] weekly `restic check` pattern; `docs/ops/restore.md` §Troubleshooting (lines 135–155) for existing verification approaches.

---

## Phase 4: Makefile Updates

### Task 4.1: Add production backup/restore/verify Makefile targets

**Priority:** High  
**Effort:** Small  
**File:** `Makefile` (lines 216–245 currently define `backup`, `restore`, `prune-backups`)  
**Dependencies:** Tasks 3.1–3.3 (scripts must exist)

The current Makefile has three backup targets ([CA §5.2]):
- `backup` (line 220): one-shot pg_dump via `docker compose exec -T db` — dev only, no restic
- `restore` (line 229): `pg_restore --clean --if-exists` via `docker compose exec -T db` — uses `docker-compose.yml` (root only)
- `prune-backups` (line 243): `find ./backups -name "dump_*.dump" -mtime +7 -delete`

The old plan proposed `backup-prod`, `restore-prod`, `verify-backups`, and `media-backup` targets ([AC §3.4] D1, D9) that were **never created**. This task adds them with corrected compose invocations.

**Add to Makefile** (after the existing `prune-backups` target, line 245):

```makefile
# ====================== Production Backups (Restic + B2) ======================

# Compose files for production (includes backup profile service)
PROD_COMPOSE := $(ENV_FILE) -f docker-compose.yml -f docker-compose.prod.yml

# Start the backup service (daily loop: pg_dump + restic + B2 sync + healthcheck)
backup-prod:
	@docker compose $(PROD_COMPOSE) --profile backup up -d --wait
	@echo "✓ Backup service started (profile: backup)"

# Stop the backup service
backup-stop:
	@docker compose $(PROD_COMPOSE) stop backup
	@echo "✓ Backup service stopped"

# Run on-demand backup (one-shot, not the daily loop)
backup-run:
	@CONFIRM_BACKUP=yes docker compose $(PROD_COMPOSE) run --rm backup
	@echo "✓ One-shot backup completed"

# Restore from Restic snapshot (DB + media)
restore-prod:
	@if [ -z "$(SNAPSHOT_ID)" ]; then \
		echo "Error: SNAPSHOT_ID not specified"; \
		echo "Example: make restore-prod SNAPSHOT_ID=latest"; \
		exit 1; \
	fi
	@CONFIRM_RESTORE=yes docker compose $(PROD_COMPOSE) run --rm backup \
		/app/scripts/restore.sh $(SNAPSHOT_ID)
	@echo "✓ Restore completed from snapshot $(SNAPSHOT_ID)"

# Verify backup integrity (local dumps + Restic repository)
verify-backups:
	@docker compose $(PROD_COMPOSE) run --rm backup /app/scripts/verify-backup.sh
	@echo "✓ Backup verification complete"

# One-shot media backup via Restic (no DB dump)
media-backup:
	@docker compose $(PROD_COMPOSE) run --rm backup \
		restic backup /app/media --repo "${RESTIC_REPOSITORY}"
	@echo "✓ Media snapshot created in Restic repository"

# Update prod .PHONY declaration (Makefile line 5)
# Add: backup-prod backup-stop backup-run restore-prod verify-backups media-backup
```

**Fixes from old plan** ([AC §3.4]):
- Old plan used `docker compose -f docker-compose.yml -f docker-compose.prod.yml` without `--env-file` (would fail compose interpolation). Updated: uses `$(PROD_COMPOSE)` which includes `$(ENV_FILE)`.
- Old plan's `media-backup` used `docker run --rm -v mko_bazuna_media_volume:/media` — wrong volume name (should be `media_volume`, project-prefixed) and wrong mount path (`/media` not `/app/media`). Updated: runs restic inside the backup service which already has `media_volume` mounted at `/app/media`.
- Old plan referenced `dump_*.dump` naming; current Makefile uses `dump_YYYYMMDD_HHMMSS.dump` ([CA §5.2] line 226). Scripts use `db_YYYYMMDD_HHMMSS.dump` naming.

**Source references:** Current Makefile backup targets (`Makefile` lines 216–245, [CA §5.2]); compose project name isolation (`Makefile` lines 17–22, `Makefile.ps1` lines 15–16 — [CA §1.3]); prod deploy invocation (`docs/ops/docker-deployment.md` lines 271–275, [CA §1.4]); env file model ([CA §4.4]).

---

### Task 4.2: Update `Makefile.ps1` with PowerShell equivalents

**Priority:** Medium  
**Effort:** Small  
**File:** `Makefile.ps1` (lines 222–289 currently define `Invoke-Backup`, `Invoke-Restore`, `Invoke-PruneBackups`)  
**Dependencies:** Task 4.1

The current `Makefile.ps1` has PowerShell equivalents for dev backup/restore ([CA §5.3]):
- `Invoke-Backup` (lines 222–249): one-shot pg_dump, no restic, prunes with `CreationTime`
- `Invoke-Restore` (lines 252–273): takes `[string]$BackupFile`, runs `pg_restore --clean --if-exists`
- `Invoke-PruneBackups` (lines 276–289): `Get-ChildItem | Where-Object | Remove-Item -Force`

This task adds production equivalents: `Invoke-BackupProd`, `Invoke-RestoreProd`, `Invoke-VerifyBackups`, `Invoke-MediaBackup`. Each mirrors the GNU Make target but uses `mko-bazuna-dev` as the project name (matching the Makefile's target-specific export — [CA §1.3]) and the prod compose file override.

**Add functions** (after `Invoke-PruneBackups`, line 289):

```powershell
# Start the backup service (daily Restic + B2 loop)
function Invoke-BackupProd {
    $env:COMPOSE_PROJECT_NAME = $DevProject
    docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml --profile backup up -d --wait
    Write-Host "Backup service started (profile: backup)" -ForegroundColor Green
}

# Restore from Restic snapshot (DB + media)
function Invoke-RestoreProd {
    param(
        [Parameter(Mandatory=$true)]
        [string]$SnapshotId
    )
    $env:COMPOSE_PROJECT_NAME = $DevProject
    $env:CONFIRM_RESTORE = "yes"
    docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml run --rm backup /app/scripts/restore.sh $SnapshotId
    Write-Host "Restore completed from snapshot $SnapshotId" -ForegroundColor Green
}

# Verify backup integrity
function Invoke-VerifyBackups {
    $env:COMPOSE_PROJECT_NAME = $DevProject
    docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml run --rm backup /app/scripts/verify-backup.sh
    Write-Host "Backup verification complete" -ForegroundColor Green
}

# One-shot media backup via Restic
function Invoke-MediaBackup {
    $env:COMPOSE_PROJECT_NAME = $DevProject
    $resticRepo = $env:RESTIC_REPOSITORY
    docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml run --rm backup restic backup /app/media --repo $resticRepo
    Write-Host "Media snapshot created" -ForegroundColor Green
}
```

**Add to switch statement** (after line 384 `"backup" { Invoke-Backup }`):
```powershell
    "backup-prod" { Invoke-BackupProd }
    "restore-prod" { Invoke-RestoreProd }
    "verify-backups" { Invoke-VerifyBackups }
    "media-backup" { Invoke-MediaBackup }
```

**Source references:** Current `Makefile.ps1` backup functions ([CA §5.3] lines 222–289); project name variables (`$DevProject = "mko-bazuna-dev"` — `Makefile.ps1` line 15, [CA §1.3]); prod deploy path (`docs/ops/docker-deployment.md` lines 271–275, [CA §1.4]).

---

## Phase 5: Documentation

### Task 5.1: Update `docs/ops/restore.md`

**Priority:** Medium  
**Effort:** Medium  
**File:** `docs/ops/restore.md` (176 lines — exists but incomplete, [CA §5.5])  
**Dependencies:** Tasks 3.2 (restore.sh), 4.1 (Makefile targets)

The current `docs/ops/restore.md` (176 lines) covers only database restore ([CA §5.5]). Three sections must be added, and one bug must be fixed:

**Bug to fix (line 104–105):** The manual restore example hard-codes `-U postgres -d postgres`, but the runtime uses `bazuna_user`/`bazuna_db`. Fix to use `${POSTGRES_USER}`/`${POSTGRES_DB}` env vars ([AC §3.4] D6).

**Sections to add:**

1. **Media Restore** — restore `media_volume` from a Restic snapshot:
   ```bash
   # Restore media files from the latest Restic snapshot
   restic restore latest --repo $RESTIC_REPOSITORY \
       --target /tmp/media_restore --include "media/"
   # Copy to mounted volume (uid 1000 — Dockerfile line 149 [CA §1.6])
   docker compose --env-file .env.docker \
       -f docker-compose.yml -f docker-compose.prod.yml run --rm web \
       bash -c "cp -a /tmp/media_restore/media/. /app/media/ && chown -R 1000:1000 /app/media"
   ```

2. **Restic Restore** — restore the full database from the Restic repository:
   ```bash
   # List B2-backed snapshots
   restic snapshots --repo $RESTIC_REPOSITORY
   # Restore specific snapshot to local staging
   restic restore <snapshot_id> --repo $RESTIC_REPOSITORY --target /tmp/restore
   # Restore DB
   docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml \
       exec -T db pg_restore --clean --if-exists -U $POSTGRES_USER -d $POSTGRES_DB /tmp/restore/backups/db_*.dump
   ```

3. **Offsite Recovery** — full DR procedure (new VPS, no local volume):
   - Provision new VPS with Docker Compose
   - Start `db` service, run `migrate` one-shot (advisory lock ID 100 — [CA §3.3])
   - `restic restore latest --target /tmp/restore --include "backups/" --include "media/"`
   - Restore DB via `pg_restore`, restore media via `cp`, run migrations again
   - Start `web`, `bot`, `nginx`, `scheduler`

**Fix compose invocations:** All examples must use `docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml` (not root `docker-compose.yml` only — [AC §3.7] G2).

**Source references:** Current `docs/ops/restore.md` (176 lines, [CA §5.5]); [AC §3.4] D4/D5/D6 (restore.md has no media/Restic/offsite sections, postgres/postgres bug); [CA §1.4] (prod deploy invocation); [CA §1.6] (uid 1000); [CA §3.3] (advisory locks); [BP §7.3] (healthcheck monitoring).

---

### Task 5.2: Create `docs/ops/backup-operations.md`

**Priority:** Medium  
**Effort:** Small  
**File:** `docs/ops/backup-operations.md` (NEW — does not exist, confirmed by audit [AC §3.4] D5)  
**Dependencies:** Task 4.1 (Makefile targets)

A new operational guide covering:

1. **Enabling the backup profile** — `docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml --profile backup up -d` ([CA §1.4], [CA §5.1] line 96 — profile gate)
2. **Manual triggers** — `make backup-prod`, `make media-backup`, `make restore-prod`, `make verify-backups`
3. **B2 bucket configuration** — SSE-S3 setup, least-privilege application key ([BP §8.2][BP §8.3])
4. **Restic password file** — `/opt/mko-bazuna/secrets/restic_repo_key` with `chmod 600` ([BP §6.3])
5. **Monitoring** — Healthchecks.io UUID setup, interpreting ping results ([BP §7.1])
6. **Retention policy** — 7 daily / 4 weekly / 12 monthly / 3 yearly with prune; weekly deep check ([BP §4.1])
7. **GDPR/retention sweep coordination** — how the scheduler's hourly sweeps ([CA §3.3]) interact with backup timing (backup should run after sweeps complete to capture the scrubbed state)
8. **31-table scope** — reference the full table list ([CA §6.1]) and PII-sensitive fields ([CA §6.2][CA §6.3])

**Source references:** [BP §6.3] (password file); [BP §7.1] (Healthchecks.io); [BP §8.2] (SSE-S3); [CA §3.3] (scheduler sweeps); [CA §6.1] (31 tables); [CA §6.2] (PII fields); [CA §6.3] (GDPR retention).

---

## Phase 6: Validation

### Task 6.1: Test database backup with new pg_dump flags

**Priority:** High  
**Effort:** Small  
**Dependencies:** Tasks 2.1, 2.2, 3.1

**Command:**
```bash
# Start backup service (daily loop starts immediately on `up`)
make backup-prod
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml logs -f backup
# Wait for first cycle to complete

# Verify local dump was created with correct flags
ls -la ./backups/db_*.dump
pg_restore --list ./backups/db_*.dump | head -30

# Verify dump was pushed to Restic
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml run --rm backup \
    restic snapshots --repo "${RESTIC_REPOSITORY}"
```

**Expected:** Dump file exists, `pg_restore --list` shows all 31 tables ([CA §6.1]), Restic snapshot exists with the dump.

---

### Task 6.2: Test media backup via Restic

**Priority:** High  
**Effort:** Small  
**Dependencies:** Tasks 2.3 (media mount), 3.1 (backup.sh)

**Command:**
```bash
make media-backup
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml run --rm backup \
    restic snapshots --repo "${RESTIC_REPOSITORY}"
```

**Expected:** Restic snapshot includes `/app/media` contents (UUID-named JPEG files + thumbnails — [CA §2.4] lines 189–220). No PII in filenames ([CA §2.4] line 192).

---

### Task 6.3: Test restore procedure (DB + media)

**Priority:** High  
**Effort:** Medium  
**Dependencies:** Tasks 3.2 (restore.sh), 4.1 (Makefile targets)

**Command:**
```bash
# List available snapshots
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml run --rm backup \
    restic snapshots --repo "${RESTIC_REPOSITORY}"

# Restore from specific snapshot
make restore-prod SNAPSHOT_ID=<snapshot-id-from-above>
```

**Validation criteria:**
1. `web` and `bot` services stopped during restore (no write conflicts)
2. All 31 tables restored with correct schema ([CA §6.1])
3. Media files restored to `/app/media` with uid 1000 ownership ([CA §1.6] line 149)
4. `migrate` one-shot runs successfully (advisory lock ID 100 — [CA §3.3])
5. `web` and `bot` services start cleanly
6. Healthcheck passes (`curl -f http://localhost:8000/health/` — [CA §1.7] line 119)

---

## Task Summary

| Task ID | Description | Priority | Effort | Dependencies |
|---------|-------------|----------|--------|--------------|
| 1.1 | Add backup env vars to `.env.docker.example` | High | Trivial | None |
| 1.2 | Create host-side restic password file + B2 bucket (SSE-S3) | High | Small | None |
| 2.1 | Create `docker/Dockerfile.backup` (Alpine + Restic 0.19.1) | High | Small | None |
| 2.2 | Replace backup service in `docker-compose.prod.yml` | High | Medium | 2.1 |
| 2.3 | Mount `media_volume` at `/app/media:ro` | High | Trivial | 2.2 |
| 2.4 | Mount restic password file at `/run/secrets/restic_repo_key:ro` | High | Trivial | 1.2, 2.2 |
| 3.1 | Create `scripts/backup.sh` (pg_dump + restic + healthcheck) | High | Medium | 2.1, 2.2, 2.3, 2.4, 1.2 |
| 3.2 | Create `scripts/restore.sh` (DB + media, fixes postgres bug) | High | Medium | 2.1, 2.2 |
| 3.3 | Create `scripts/verify-backup.sh` | Medium | Small | 2.1 |
| 4.1 | Add prod Makefile targets (`backup-prod`, `restore-prod`, etc.) | High | Small | 3.1–3.3 |
| 4.2 | Add prod PowerShell equivalents in `Makefile.ps1` | Medium | Small | 4.1 |
| 5.1 | Update `docs/ops/restore.md` (fix bug, add media/Restic/offsite) | Medium | Medium | 3.2, 4.1 |
| 5.2 | Create `docs/ops/backup-operations.md` | Medium | Small | 4.1 |
| 6.1 | Test database backup with new pg_dump flags | High | Small | 2.1, 2.2, 3.1 |
| 6.2 | Test media backup via Restic | High | Small | 2.3, 3.1 |
| 6.3 | Test restore procedure (DB + media) | High | Medium | 3.2, 4.1 |

---

## Execution Order

```
Phase 1: Configuration
  1.1 ──→ 1.2

Phase 2: Docker Compose
  2.1 ──→ 2.2 ──→ 2.3
               └─→ 2.4 (requires 1.2)

Phase 3: Scripts (parallel after Phase 2)
  3.1 (requires 2.1, 2.2, 2.3, 2.4, 1.2)
  3.2 (requires 2.1, 2.2)
  3.3 (requires 2.1)

Phase 4: Makefile (after 3.x)
  4.1 (requires 3.1–3.3) ──→ 4.2

Phase 5: Documentation (after 4.x)
  5.1 (requires 3.2, 4.1) ──→ 5.2 (requires 4.1)

Phase 6: Validation (after 3.x, 4.x)
  6.1 ──→ 6.2 ──→ 6.3
```

**Parallelization opportunities:**
- Tasks 1.1 and 1.2 are independent → parallel
- Tasks 2.1 and 1.1/1.2 are independent → can start once env vars decided
- Tasks 3.2 and 3.3 are independent of 3.1 → parallel after 2.x
- Tasks 4.1, 4.2, 5.1, 5.2, 6.1 can partially overlap with script finalization

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **Restic repository corruption** | Low | Critical (unrecoverable) | Weekly `restic check --read-data-subset=1/7` ([BP §4.1]); verify snapshots after each backup; keep 2-day local staging on `./backups/` (gitignored — `.gitignore` line 239, [CA §5.4]) |
| **Restic password loss** | Low | Critical (data unrecoverable) | Store password in password manager *and* the file at `/opt/mko-bazuna/secrets/restic_repo_key` with `chmod 600` ([BP §4.2], [BP §6.3]). Document key rotation via `restic key passwd` |
| **B2 credentials leakage** | Low | High (offsite data at risk) | Use least-privilege B2 application key scoped to backup bucket only ([BP §8.3]); never commit `B2_KEY_ID`/`B2_APP_KEY` to git (`.env.docker` is gitignored — `.gitignore` line 148, [CA §4.3]) |
| **Media volume path mismatch** | Low | High (media silently skipped) | Strict requirement: mount at `/app/media`, NOT `/media` — old plan's `/media` path is a known bug ([AC §3.1] A2, [CA §2.1]) |
| **Docker secrets pattern mismatch** | Low | Medium (deployment failure) | Do NOT use Docker Swarm `secrets:` — use file-mounted `RESTIC_PASSWORD_FILE` bind mount ([BP §6.1], [AC §3.1], [AC §3.6]) |
| **Restore credential mismatch** | Medium | High (restore fails) | Use `${POSTGRES_USER}`/`${POSTGRES_DB}` from `.env.docker`, NOT hard-coded `postgres`/`postgres` — this bug exists in current `docs/ops/restore.md` line 104 ([AC §3.4] D6) |
| **Compose project name mismatch** | Medium | High (wrong volume targeted) | Always use `--env-file .env.docker` and explicit `--project-name` or Makefile targets ([CA §1.3], [AC §3.7] G1). Avoid bare `docker compose up` (uses directory-name default `mko_bazuna` — [CA §1.3]) |
| **B2 region/endpoint mismatch** | Low | Medium (backup fails) | Use `s3.us-west-002.backblazeb2.com` (B2 S3 gateway), NOT old plan's `s3.us-west-004` ([BP §3.3], [AC §3.5] E1) |
| **B2 SSE-S3 not enabled** | Low | Medium (no server-side encryption) | Enable SSE-S3 on the B2 bucket during setup (Task 1.2) ([BP §8.2]) |
| **Backup window exceeds 24h for large media** | Low | Medium (overlapping backups) | Restic deduplication handles incremental media; daily cycle at 86400s is acceptable for sub-200 GB media volume ([CA §2.4], `[CA §2.4]` media 50–200 GB) |
| **GDPR sweep timing vs. backup** | Low | Low (inconsistent retention state) | Schedule backup to run after scheduler sweeps complete (scheduler runs hourly, backup daily — coordinate via Healthchecks.io window) ([CA §3.3]) |

---

## Estimated Timeline

| Phase | Tasks | Estimated Effort |
|-------|-------|-----------------|
| Phase 1: Configuration | 1.1, 1.2 | 30–45 min (B2 bucket + key setup is the variable) |
| Phase 2: Docker Compose | 2.1, 2.2, 2.3, 2.4 | 1–2 hours (Dockerfile + compose edits + image build/test) |
| Phase 3: Scripts | 3.1, 3.2, 3.3 | 2–3 hours (script authoring + logic + error handling) |
| Phase 4: Makefile | 4.1, 4.2 | 1 hour (GNU Make + PowerShell mirroring) |
| Phase 5: Documentation | 5.1, 5.2 | 1–2 hours (restore.md fixes + new operations guide) |
| Phase 6: Validation | 6.1, 6.2, 6.3 | 2–3 hours (test DB backup, test media backup, test restore) |

**Total effort (parallelized):** 6–9 hours

---

## Advisory Recommendations

1. **B2 region selection** — `s3.us-west-002.backblazeb2.com` is the correct S3 gateway endpoint for B2 ([BP §3.3]); the old plan's `us-west-004` is stale. Bucket location should match the configured region in the B2 web console.

2. **Restic version pinning** — Download the v0.19.1 binary directly in `Dockerfile.backup` rather than relying on Alpine's `apk` repo, which may ship an older version ([BP §4.1]).

3. **Local staging retention** — Keep `db_*.dump` files for 2 days locally (the `backup.sh` `cleanup_local_backups` function removes files older than 2 days), enabling fast DB-only restores without hitting B2 ([CA §5.1] current service keeps 7 days locally; Restic handles offsite).

4. **Backup window alignment** — The scheduler's hourly GDPR sweeps ([CA §3.3]) hard-delete PII after 30 days and purge deleted ads after 120 days. Schedule the daily backup to start **after** the 08:00 UTC `send_alerts` daily sweep completes, so the backup captures the post-sweep (GDPR-compliant) state.

5. **`pg_dumpall --globals-only` monthly job** — The current architecture uses role/user definitions in PostgreSQL that are not captured by per-database `pg_dump` ([BP §1.3]). Add a monthly cron that runs `pg_dumpall --globals-only` and stores the output as a separate Restic-tagged snapshot.

6. **Healthchecks.io free-tier sufficiency** — The free tier supports 20 cron checks and 1000 pings/month ([BP §7.1]). The daily backup + weekly check = 15 pings/month, well within limits. Add a separate check UUID for the weekly `restic check`.

7. **Media file deduplication** — Restic's default 60 MB chunking means most JPEG photos (1–3 MB, [CA §2.4]) will be stored as individual chunks with full deduplication ([BP §4.3]). No pre-compression or tar packaging is needed.

8. **Test DB vs prod DB** — `make backup` targets the dev project (`mko-bazuna-dev`) via `docker compose exec -T db`. Production backups use the `backup` service in `docker-compose.prod.yml` with the `backup` profile. Do not mix dev and prod backup operations.

9. **`Makefile.ps1` parity** — Windows developers use `.\Makefile.ps1 backup-prod` / `restore-prod` / `verify-backups` / `media-backup`. Ensure these functions pass `--env-file .env.docker` explicitly (PowerShell does not inherit GNU Make's target-specific exports) ([CA §1.3], `Makefile.ps1` lines 15–16).

10. **`backups/` gitignore** — The `./backups/` directory is gitignored at `.gitignore` line 239 (comment: "may contain PII from `make backup`") ([CA §5.4]). This is correct — never commit backup dumps. The Restic repository lives in B2, not on disk, so only ephemeral staging files are local.
