---
id: rollback
domain: ops
tags:
  - rollback
  - deployment
  - disaster-recovery
  - operations
  - image-tag
  - schema
related:
  - docker-deployment
  - restore
  - migration-workflow
  - seed-workflow
---

## Purpose

Runbook for rolling back a production deployment of the Mko Bazuna platform when a
deployed image, configuration change, or schema migration causes a regression.
The rollback process is manual (deployment is currently manual — B4 is creating
a formal deploy workflow referenced in finding
[12-OPS-005](../../.ai/audit/12-production-ops/findings.md)). This
document covers the six rollback dimensions: image-tag rollback, config rollback,
schema rollback, health-check-gated validation, rollback-test cadence, and
failure escalation.

## Main Concepts

- **Two long-lived processes, one DB:** The `web` (gunicorn) and `bot` (aiogram)
  containers share a single Django project and PostgreSQL database. Rolling back
  the image must restart **both** services atomically so they never run against
  mismatched schema or code.
- **Image tag drives both processes:** `docker-compose.prod.yml` resolves the image
  for `web`, `bot`, `migrate`, `create_admin`, `seed`, `load_cities`, and
  `load_catalog` from a single env var: `${IMAGE_TAG:-latest}`. Changing that one
  variable and re-running `docker compose up -d` rolls back **all** services
  simultaneously — no per-service tagging drift.
- **Config is bind-mounted read-only:** `.env.prod` is mounted as
  `/app/src/.env:ro` into every container. Config changes take effect only on
  container restart (`up -d` recreates the affected containers). A config
  rollback therefore means reverting the file on disk and redeploying.
- **Migrations are forward-only by default:** Django migrations append rows to
  `django_migrations` and apply schema changes. Reversing a migration is possible
  but risky — it drops columns/indexes and can destroy data. Schema rollback is
  the most dangerous dimension and should be a last resort (see
  [Schema Rollback Considerations](#schema-rollback-considerations)).
- **Health-check gating:** The Docker `HEALTHCHECK` (in `docker/Dockerfile` and
  `docker-compose.yml`) probes `/health/live/` — a dependency-free liveness endpoint
  returning `{"status": "alive"}`. The application-level readiness endpoint
  `/health/ready/` is the gated validation target: it returns `200` with
  `{"version": 1, "status": "ready", "checks": {"database": "ok", "cache": "ok", "bot": "ok"|"stale"|"disabled"}}`
  when PostgreSQL, Redis cache, and the bot liveness marker are all healthy; `503` otherwise.
  The bot container's healthcheck (`docker/healthcheck-bot.sh`) verifies PID liveness,
  a readiness marker file, and optional freshness via `BOT_HEALTH_STALE_SECONDS`.
  Additionally, the bot process writes a Redis-based `bot:liveness` marker (epoch
  timestamp) on startup and on every inbound update via `LivenessMiddleware` in
  `telegram_bot/lifecycle.py` (OPS-003). The web readiness probe reads this Redis
  key (gated by `BOT_HEALTH_CHECK_ENABLED`, default `True`) to verify the bot is alive
  and fresh. Validation must confirm both before declaring a rollback successful.

> **Note on health endpoints:** Finding 12-OPS-002 has been completed — the
> container-level `HEALTHCHECK` now uses `/health/live/` (dependency-free liveness).
> The application-level readiness check (`/health/ready/`) remains the gated
> validation target used by the deploy workflow and rollback validation. See
> [Health-Check-Gated Validation](#health-check-gated-validation)
> for both endpoints.

| Aspect | Rollback mechanism | Risk level |
|--------|-------------------|------------|
| Image tag | Change `IMAGE_TAG` in `.env.prod`, re-deploy | Low |
| Config | `git checkout .env.prod` to pinned commit, re-deploy | Low |
| Schema | `migrate <app> <previous_migration>` + data backfill | High |
| Health | Liveness: `/health/live/` · Readiness: `/health/ready/` (incl. Redis `bot:liveness`) | — (validation) |

## Prerequisites

Before starting a rollback:

1. Identify the **target commit** — the last known-good git commit with the image
   tag, `.env.prod` content, and migration set you want to roll back to.
2. Ensure the **last good backup** of the production database exists and has been
   restore-tested (see [Database Restore Runbook](restore.md)). A schema rollback
   may destroy data; a backup is your safety net.
3. Confirm you have **write access** to `.env.prod` and `docker compose` on the
   production host.
4. Notify stakeholders — schedule a maintenance window if the rollback affects
   user-facing traffic (the site will be briefly unavailable during container
   recreation).

### Identifying the target image tag

Production image tags are resolved in `docker-compose.prod.yml`:

```yaml
image: ${REGISTRY:-ghcr.io}/${REPOSITORY:-manicko/mko_bazuna}:${IMAGE_TAG:-latest}
```
`IMAGE_TAG` is set in `.env.prod` (see
  [.env.prod.example](../../.env.prod.example), line 68). To find the
  last-known-good tag:

```bash
# Show IMAGE_TAG history from git history of .env.prod
git log --oneline -10 -- .env.prod
git show <commit>:.env.prod | grep IMAGE_TAG
```

If image tags map to git tags, you can also enumerate published tags:

```bash
# List recent image tags from GHCR (if using GitHub Packages)
gh repo view manicko/mko_bazuna --json nameWithPath -t '{{.}}'
# Then inspect: gh api repos/manicko/mko_bazuna/packages/container/mko_bazuna/versions
```

## 1. Image-Tag Rollback

Use this when the deployed **container image** (code release) is broken — e.g.,
a new `IMAGE_TAG` introduced a runtime error, 500s, or bot crashes.

### Procedure

1. **Pin `.env.prod` to the target image tag:**

   ```bash
   # Edit IMAGE_TAG in .env.prod to the last-known-good tag
   # e.g., if rolling back from "v1.4.0" to "v1.3.2"
   sed -i 's/^IMAGE_TAG=.*/IMAGE_TAG=v1.3.2/' .env.prod
   ```

   The image tag is the **only** variable that controls which container image
   `web`, `bot`, and all one-shot services pull. All seven services in
   `docker-compose.prod.yml` (lines 8, 18, 28, 36, 44, 54, 63) reference
   `${IMAGE_TAG:-latest}`.

2. **Recreate the long-lived containers:**

   ```bash
   # Use --pull to force a fresh image pull (avoid stale cached layers)
   docker compose --env-file .env.prod \
     -f docker-compose.yml -f docker-compose.prod.yml \
     up -d --pull always web bot
   ```

   > `up -d` with no service names recreates **all** services. Targeting `web bot`
   > is sufficient for a code-only rollback (the one-shot services `migrate`,
   > `load_catalog`, etc. are not long-lived and will only re-run if their image
   > hash changed and you omit the service filter). If the rollback also reverts
   > migration files, include the one-shot services (see
   > [Schema Rollback](#schema-rollback-considerations)).

3. **Wait for gunicorn graceful restart.** The gunicorn config
   (`gunicorn.conf.py`) sets `graceful_timeout = 30` and `timeout = 60`. When the
   old container receives `SIGTERM`, gunicorn gives in-flight workers up to
   `graceful_timeout` (30 s) to finish requests before force-killing them.
   During this window, new connections may be briefly rejected.

4. **Validate** (see [Health-Check-Gated Validation](#health-check-gated-validation)).

### When to use `--force-recreate`

If only the image tag changed but Docker's container cache does not detect the
difference (same `IMAGE_TAG` string but different digest), force recreation:

```bash
docker compose --env-file .env.prod \
  -f docker-compose.yml -f docker-compose.prod.yml \
  up -d --force-recreate --pull always web bot
```

## 2. Config Rollback

Use this when a change to `.env.prod` (a secret, feature flag, or Django setting)
introduced a regression — e.g., a bad `DJANGO_SECRET_KEY`, an invalid
`ALLOWED_HOSTS`, or a misconfigured `GOOGLE_TRANSLATE_API_KEY`.

The config file is bind-mounted as `/app/src/.env:ro` into every container.
Reverting it on disk and redeploying recreates the containers with the prior
config.

### Procedure

1. **Revert `.env.prod` to the target commit:**

   ```bash
   # Revert the entire file to the last-known-good version
   git checkout <target-commit> -- .env.prod

   # Or revert only the changed variable(s) (preferred for surgical rollback)
   git checkout <target-commit> -- .env.prod
   sed -i 's/^PROBLEM_VAR=.*/PROBLEM_VAR=previous_value/' .env.prod
   ```

2. **Redeploy with the reverted config:**

   ```bash
   docker compose --env-file .env.prod \
     -f docker-compose.yml -f docker-compose.prod.yml \
     up -d
   ```

3. **Validate** (see [Health-Check-Gated Validation](#health-check-gated-validation)).

### Secrets with immediate blast radius

Some config variables invalidate running state. After a config rollback, account
for:

| Variable | Effect of rollback | Restart required |
|----------|--------------------|------------------|
| `DJANGO_SECRET_KEY` | All signed tokens (sessions, CSRF, password-reset) become valid again for the old key | `web`, `bot` |
| `BOT_TOKEN` | Restored bot token resumes polling from the last offset | `bot` only |
| `GOOGLE_TRANSLATE_API_KEY` | Translation calls resume with the valid key | `bot` only |
| `ALLOWED_HOSTS` | Host header validation relaxed/stricter | `web` only |
| `POSTGRES_*` | Database connection target changes — **do not change during rollback** unless DB was also rolled back | `db` (stop writes first) |

> **Do not** roll back `POSTGRES_*` credentials while the database is running
> unless you are also restoring the database from backup. Mismatched credentials
> will cause `web`/`bot` to fail DB connections.

## 3. Schema Rollback Considerations

Django migrations are **forward-only by design**. Rolling back a migration with
`django.db.migrations` reverses schema changes (drops columns, removes indexes,
deletes constraint) but **cannot restore the data** that lived in those columns.
This is the highest-risk rollback dimension.

### Decision tree

```
Did the bad deploy change the SCHEMA (new/reversed migrations)?
  ├── No  → Skip this section. Image + config rollback is sufficient.
  └── Yes → Did the schema migration drop data or alter columns?
        ├── No  → Safe forward fix: deploy a corrective migration (additive fix).
        └── Yes → Risk of data loss. Restore from backup (see restore.md),
                    then re-apply migrations down to the last-good migration.
```

### Forward-only migration reality

Per the project's [Migration Workflow](migration-workflow.md), the
steady state is one `0001_initial.py` per app. Production deployments run the
`migrate` one-shot service once before `web`/`bot` start. There is no
PgBouncer transaction-mode pool in the dev/migrate path; the advisory lock
(ID 100) serializes migration runs.

Django's `migrate` command supports rolling back to a previous migration:

```bash
# Roll back a specific app to a specific migration
docker compose --env-file .env.prod \
  -f docker-compose.yml -f docker-compose.prod.yml \
  run --rm migrate python src/backend/manage.py migrate ads 0003_previous

# Roll back all apps to a specific point (creates a plan)
docker compose --env-file .env.prod \
  -f docker-compose.yml -f docker-compose.prod.yml \
  run --rm migrate python src/backend/manage.py migrate --plan
```

### Data backfill requirement

A rollback that reverses a migration which **added** a column or **reshaped**
data means that data is lost unless you backfill it. The pattern:

1. **Restore** the database from a pre-deploy backup (the safest path):
   ```bash
   # Full restore from last-known-good backup (see restore.md)
   make restore BACKUP_FILE=./backups/dump_<pre-deploy-timestamp>.dump
   ```
2. **Re-apply migrations** down to the target migration (if the backup is ahead):
   ```bash
   docker compose --env-file .env.prod \
     -f docker-compose.yml -f docker-compose.prod.yml \
     run --rm migrate python src/backend/manage.py migrate <app> <target_migration>
   ```
3. **Backfill** any data that the rolled-back migration was responsible for
   creating (e.g., if a migration backfilled translated ad content, re-run
   `manage.py backfill_translations` against the restored DB).

> **Recommendation:** For schema-related failures, prefer a **database restore +
> image rollback** over a `migrate <app> <previous_migration>` rollback. Restore
> from the last-known-good backup, then re-deploy the last-known-good image. This
> avoids the data-loss risk of reversing migrations entirely.

### Post-schema-rollback migration re-run

After restoring the DB and rolling back the image, the `migrate` one-shot service
will see the database at a migration point consistent with the rolled-back image.
Re-deploy normally:

```bash
docker compose --env-file .env.prod \
  -f docker-compose.yml -f docker-compose.prod.yml \
  up -d --force-recreate --pull always
```

The `migrate` service runs again (advisory lock ID 100) and finds all
migrations already applied — it is a no-op, which is the expected steady state.

## 4. Health-Check-Gated Validation

After any rollback (image, config, or schema), validate that both long-lived
services are healthy before declaring the rollback successful.

### Web — `/health/ready/` (readiness endpoint)

The Docker container `HEALTHCHECK` (line 256 of `docker-compose.yml`, and the
`HEALTHCHECK` in `docker/Dockerfile`) curls `http://localhost:8000/health/live/` —
a dependency-free liveness probe. The application-level readiness endpoint
`/health/ready/` is the gated validation target that verifies PostgreSQL, Redis,
and bot liveness. The readiness endpoint returns:

- `200` with `{"version": 1, "status": "ready", "checks": {"database": "ok", "cache": "ok", "bot": "ok"|"stale"|"disabled"}}`
  when PostgreSQL and Redis are both reachable and the bot liveness marker is fresh
  (or marked `"disabled"` in test settings where `BOT_HEALTH_CHECK_ENABLED = False`).
- `503` with `{"status": "not_ready", ...}` when any of database, cache, or bot
  liveness fails.

In production, port 8000 is **not** published (nginx proxies on 80/443).
Poll the endpoint via `docker compose exec` so curl runs inside the `web` container:

```bash
# Poll readiness until 200 (or timeout at 90s)
timeout 90 bash -c 'while ! docker compose exec -T web curl -sf http://localhost:8000/health/ready/ > /dev/null; do sleep 5; done'

# Verify the response body
docker compose exec -T web curl -s http://localhost:8000/health/ready/ | python -m json.tool
```

### Web — `/health/live/` (liveness endpoint)

The liveness endpoint returns `200` with `{"status": "alive"}` regardless of
database or cache state — it confirms the gunicorn process itself is responsive.
This endpoint is what the Docker `HEALTHCHECK` probes (see
`docker-compose.yml:256` and the `HEALTHCHECK` in `docker/Dockerfile`, both of
which were corrected to `/health/live/` per OPS-002). Use `/health/ready/` (above)
for deploy-gated readiness validation that verifies database, Redis, and bot liveness.

```bash
curl -s http://localhost:8000/health/live/
# Expected: {"status": "alive"}
```

### Bot — container healthcheck

The bot container's healthcheck runs `docker/healthcheck-bot.sh` (line 299 of
`docker-compose.yml`). It performs three checks against the file-based marker:

1. **PID 1 alive** — `kill -0 1`
2. **Readiness marker exists** — `/tmp/mko_bazuna_bot_alive` (written by the bot's
   startup lifecycle hook in `telegram_bot/lifecycle.py`)
3. **Marker freshness** — if `BOT_HEALTH_STALE_SECONDS > 0`, the marker's mtime
   must be within that window (detects retry-loop / stuck polling)

In addition to the file-based marker, the bot process writes a Redis-based
`bot:liveness` marker (epoch timestamp) on startup and on every inbound update
via `LivenessMiddleware` in `telegram_bot/lifecycle.py` (OPS-003). The web
readiness probe (`/health/ready/`) reads this Redis key — gated by
`BOT_HEALTH_CHECK_ENABLED` (default `True`, disabled in tests) with a staleness
window of `BOT_HEALTH_STALE_SECONDS` (default 120, set on both `web` and `bot`
services in `docker-compose.yml`) — to verify the bot is alive and fresh. If the
key is absent or older than the staleness window, the readiness endpoint reports
`"bot": "stale"` and returns `503`.

Verify bot health via Docker:

```bash
docker compose --env-file .env.prod \
  -f docker-compose.yml -f docker-compose.prod.yml \
  ps bot

# Look for "healthy" in the "State" column
```

Inspect the marker file directly:

```bash
docker compose --env-file .env.prod \
  -f docker-compose.yml -f docker-compose.prod.yml \
  exec bot ls -la /tmp/mko_bazuna_bot_alive

# Check freshness (marker mtime within BOT_HEALTH_STALE_SECONDS)
docker compose --env-file .env.prod \
  -f docker-compose.yml -f docker-compose.prod.yml \
  exec bot stat -c '%Y %n' /tmp/mko_bazuna_bot_alive
```

### Validation checklist

| Service | Check | Expected | Command |
|---------|-------|----------|---------|
| web | Liveness | HTTP 200, `status: "alive"` | `docker compose exec -T web curl -sf http://localhost:8000/health/live/` |
| web | Readiness | HTTP 200, `status: "ready"` | `docker compose exec -T web curl -sf http://localhost:8000/health/ready/` |
| web | Bot liveness marker (Redis) | `checks.bot == "ok"` in readiness response | `docker compose exec -T web curl -s http://localhost:8000/health/ready/ \| python -m json.tool` |
| bot | Container healthcheck | `healthy` state | `docker compose ps bot` |
| bot | Marker freshness | mtime within `BOT_HEALTH_STALE_SECONDS` | `stat -c %Y /tmp/mko_bazuna_bot_alive` |
| bot | Redis liveness marker | `bot:liveness` key fresh in Redis | `docker compose exec bot python -c "from django.core.cache import cache; print(cache.get('bot:liveness'))"` |
| db | PostgreSQL healthy | `pg_isready` succeeds | `docker compose ps db` |
| redis | Redis healthy | `redis-cli ping` → `PONG` | `docker compose ps redis` |

### Post-rollback smoke test

After health checks pass, verify core user-facing functionality:

```bash
# 1. Site loads (via nginx on 443, or 8000 directly)
curl -sfI https://your-site.example.com/ | head -1
# Expected: HTTP/1.1 200 OK

# 2. Search endpoint responds
curl -sf "https://your-site.example.com/search/?q=apartments" | head -c 200

# 3. Bot responds to /start (via Telegram API or by checking logs)
docker compose logs bot | tail -5
# Expected: bot logs show "Started polling" or recent update processing
```

## 5. Rollback-Test Cadence

The rollback procedure must be exercised in **staging** (a non-production
environment that mirrors production's compose layout) before it is needed in
production. This validates:

- The image tag resolution (`IMAGE_TAG`) flows correctly to all services.
- Config revert + redeploy does not leave stale containers.
- Schema rollback does not corrupt the database.
- Health-check gating catches a broken deploy.

### Cadence schedule

| Scenario | Frequency | Owner | Notes |
|----------|-----------|-------|-------|
| Full rollback drill (image + config + schema) | Every 2 weeks | On-call SRE | Exercises all three dimensions end-to-end |
| Image-only rollback drill | Every sprint (every 2 weeks) | Deploy engineer | Fastest path; covers the most common case |
| Schema rollback drill | Monthly (after any migration deployment) | SRE + DBA | High-risk; only after a migration that touched schema |
| Health-check validation drill | Every deploy | CI gate | Automated — deploy workflow runs health checks |

### Staging rollback drill procedure

```bash
# 1. Deploy a "bad" image to staging (simulated failure)
export IMAGE_TAG=v1.4.0-broken  # or a deliberately broken build
docker compose --env-file .env.staging \
  -f docker-compose.yml -f docker-compose.prod.yml \
  up -d --pull always web bot

# 2. Wait for health checks to fail (or run manually)
sleep 60
docker compose --env-file .env.staging \
  -f docker-compose.yml -f docker-compose.prod.yml ps
# Expected: web/bot show "unhealthy"

# 3. Roll back to last-known-good
export IMAGE_TAG=v1.3.2  # last-known-good tag
docker compose --env-file .env.staging \
  -f docker-compose.yml -f docker-compose.prod.yml \
  up -d --pull always web bot

# 4. Validate health checks recover
timeout 90 bash -c 'while ! docker compose exec -T web curl -sf http://localhost:8000/health/ready/ > /dev/null; do sleep 5; done'
echo "Rollback validated in staging"
```

> **Staging config:** If no staging `.env.prod` file exists yet, create
> `.env.staging` from `.env.prod.example` with staging credentials. The staging
> environment uses the same `docker-compose.prod.yml` override (no separate
> staging compose file — see [Production Deployment](docker-deployment.md#production-deployment)).

### CI integration

Finding 12-OPS-005 (deploy workflow, P0) added a GitHub Actions `deploy.yml`
(workflow_dispatch with `environment: production` manual approval) that gates
production deploys on `/health/ready/` validation (60-second timeout). The
rollback runbook is referenced from that workflow's `on-failure` step. The
monthly `restore-test.yml` workflow (B5 / OPS-006) provides a secondary
validation of backup integrity via an isolated restore + `migrate --plan --check`.
Staging rollback drills continue to be performed manually using the procedure
above (see [Rollback-Test Cadence](#5-rollback-test-cadence)).

## 6. Rollback Failure Escalation Path

If a rollback fails — e.g., the rolled-back image still fails health checks, the
database restore fails, or the config revert does not resolve the issue —
escalate according to the severity table below.

### Escalation severity levels

| Level | Trigger condition | Response time | Owner | Action |
|-------|-------------------|---------------|-------|--------|
| **P0** | Production site down / all users affected | < 5 min | On-call SRE | Initiate full rollback from last-known-good backup |
| **P1** | Partial outage (search broken, bot down) | < 15 min | On-call SRE + backend engineer | Targeted image/config rollback |
| **P2** | Minor regression (one feature broken, site otherwise functional) | < 1 hour | Next-shift engineer | Defer rollback; schedule fix in next deploy |
| **Failure to recover** | Rollback itself fails (restore errors, data corruption) | Immediate | On-call SRE + DBA + team lead | Follow the "Rollback Failure" procedure below |

### Rollback failure procedure

If the standard rollback does not restore service:

1. **Stop the broken deployment:** Prevent further traffic from hitting the
   broken containers.
   ```bash
   docker compose --env-file .env.prod \
     -f docker-compose.yml -f docker-compose.prod.yml \
     stop web bot
   ```

2. **Assess data integrity:** Check if the database is consistent.
   ```bash
   docker compose --env-file .env.prod \
     -f docker-compose.yml -f docker-compose.prod.yml \
     exec db psql -U $POSTGRES_USER -d $POSTGRES_DB -c "SELECT count(*) FROM django_migrations;"
   ```

3. **Restore from the last-known-good backup** (most reliable recovery):
   See [Database Restore Runbook](restore.md). Use the isolated restore-test
   pattern first to verify backup integrity **before** touching production:
   ```bash
   # Validate backup in isolation
   make restore-test BACKUP_FILE=./backups/dump_<pre-deploy-timestamp>.dump

   # If isolated restore succeeds, do the production restore
   make restore BACKUP_FILE=./backups/dump_<pre-deploy-timestamp>.dump
   ```

4. **Re-deploy the last-known-good image:**
   ```bash
   # Ensure IMAGE_TAG in .env.prod points to the last-known-good image
   git checkout <last-good-commit> -- .env.prod
   docker compose --env-file .env.prod \
     -f docker-compose.yml -f docker-compose.prod.yml \
     up -d --force-recreate --pull always
   ```

5. **Validate** (see [Health-Check-Gated Validation](#health-check-gated-validation)).
   If health checks still fail after backup restore + image rollback, the
   database itself may be corrupted — escalate to the team lead and consider
   provisioning a fresh database from an earlier backup.

6. **Post-incident review:** Document the root cause and add a preventive
   measure (CI gate, migration test, or a deploy-workflow healthcheck assertion)
   referenced in finding
   [12-OPS-005](../../.ai/audit/12-production-ops/findings.md) and
   [finding 12-OPS-001](docker-deployment.md#deployment-checks).

### Contact escalation (on-call roster)

| Role | Primary contact | Secondary | Paging method |
|------|----------------|-----------|---------------|
| SRE / On-call | Team lead via PagerDuty | — | PagerDuty + Telegram |
| DBA | (not yet assigned) | On-call SRE | PagerDuty |
| Backend engineer | Rotation via GitHub team | — | Slack #oncall-backend |
| Deployment pipeline (B4) | Pipeline owner | — | GitHub issue / Slack |

> **If PagerDuty is unreachable:** Post in the `#ops-incident` Slack channel
> with `[P0]` prefix and SMS the team lead directly.

## Rollback Decision Matrix

Use this table to select the rollback dimension based on the failure mode:

| Failure mode | Symptom | Rollback dimension | Reference |
|-------------|---------|-------------------|-----------|
| Broken code release | `500` errors, `ImportError`, bot crashes | [1. Image-Tag Rollback](#1-image-tag-rollback) | — |
| Bad secret / setting | `DEBUG=True` in prod, invalid `ALLOWED_HOSTS`, token exposed | [2. Config Rollback](#2-config-rollback) | — |
| Regression from new column | `OperationalError: no such column`, data truncated | [3. Schema Rollback](#3-schema-rollback-considerations) + backup restore | [restore.md](restore.md) |
| Broken migration at deploy | `migrate` one-shot exits non-zero, containers stuck | [3. Schema Rollback](#3-schema-rollback-considerations) + image rollback | [migration-workflow.md](migration-workflow.md) |
| Stale bot polling | Bot not responding to `/start`, marker missing | Image + config rollback of `bot` only | See [Health-Check Validation](#4-health-check-gated-validation) |

## Related Documentation

- [Docker Deployment & Operations](docker-deployment.md) — production deployment
  command, service topology, health checks, troubleshooting
- [Database Restore Runbook](restore.md) — backup/restore procedures, RPO/RTO
- [Migration Workflow](migration-workflow.md) — dev migration workflow,
  advisory locks, consolidation rules
- [Seed Data Workflow](seed-workflow.md) — seed service, destructive re-seed
  behavior
- [PostgreSQL 18 Docker Volume Migration](postgres-18-docker-volume-migration.md)
  — DB volume path configuration
- [Local HTTPS with mkcert](local-https-mkcert.md) — local TLS setup
- [Architecture Guidelines](../99-agent/architecture.md) — two-process/one-DB
  model, advisory lock allocation
- [.env.prod.example](../../.env.prod.example) — production environment variable template
- [gunicorn.conf.py](../../gunicorn.conf.py) — gunicorn runtime config
  (`graceful_timeout = 30`, `timeout = 60`, `preload_app = True`)
- [docker/healthcheck-bot.sh](../../docker/healthcheck-bot.sh) — bot healthcheck
  script
- [Finding 12-OPS-007](../../.ai/audit/12-production-ops/findings.md) — rollback runbook (this document)
- [Finding 12-OPS-005](../../.ai/audit/12-production-ops/findings.md) — deploy workflow (`deploy.yml`, health-check gating)
- [Finding 12-OPS-002](../../.ai/audit/12-production-ops/findings.md) — healthcheck endpoint changed to `/health/live/`
- [Finding 12-OPS-003](../../.ai/audit/12-production-ops/findings.md) — Redis-based bot liveness marker (`bot:liveness`)
- [Finding 12-OPS-006](../../.ai/audit/12-production-ops/findings.md) — restore-test automation (`restore-test.yml`)
