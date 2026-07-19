# Phase 4 Detailed Plan: Analytics + Production Hardening

**Wave:** Infrastructure
**Depends_on:** Phases 1-3
**Files_modified:** `src/backend/apps/analytics/`, `src/backend/apps/core/management/commands/`, `docker/nginx/nginx.conf`, `.github/workflows/ci.yml`, `docs/wiki/*.md`
**Autonomous:** Yes

> **Spec source:** `docs/wiki/technical-specification.md` (decision L, J; US-A5, US-A9), `docs/wiki/packages.md` (Plausible = JS snippet NO python dep; celery/redis/django-storages DEFERRED), `docs/wiki/architecture-structure.md` (zone R8 nginx, systemd/cron), `docs/wiki/db-structure.md` (analytics_events, lifecycle indexes, IX_users_erasure_sweep).
> **Planner note:** Produced via 3 iterative Planner runs. Coverage audit, command-name contract with Docker plan, advisory-lock spec, zone R8 headers verified in run 3.

---

## Coverage Audit Summary

| Requirement | Covered By Task(s) | Notes |
|-------------|-------------------|-------|
| **US-A5**: Auto-archive/delete (2mo/4mo) | Task 2 | `archive_sweep`, `delete_sweep` with partial indexes |
| **US-A9**: Logs/events view | Task 1 | `AnalyticsEvent` model + admin/metrics view; `ModeratorActionLog` preserved on erasure |
| **Decision L**: Plausible + AnalyticsEvent | Task 1 | Plausible JS snippet only (no Python dep, no consent banner); `AnalyticsEvent` on REGISTRATION_CREATED/AD_PUBLISHED/SEARCH_PERFORMED/CONTACT_INITIATED; `user_id` SET NULL on erasure |
| **Decision J**: Lifecycle timers | Task 2, Task 3 | `published_at` resets on every PUBLISHED transition; indexes `IX_ads_archive_sweep`, `IX_ads_delete_sweep` verified |

---

## Task 1: Analytics Event Tracking (decision L)

**Goal:** Cookieless web analytics + internal product metrics.

**Acceptance Criteria:**
- `templates/base.html`: Plausible JS snippet injected via `PLAUSIBLE_HOST` env var (<1KB, cookieless, EU-hosted SaaS, legitimate interest per decision L). **NO consent banner** — Plausible collects no PII.
- `apps/analytics/models.py`: `AnalyticsEvent` model with `event_type` (StrEnum: `REGISTRATION_CREATED`, `AD_PUBLISHED`, `SEARCH_PERFORMED`, `CONTACT_INITIATED`), `timestamp`, nullable `user_id` (SET NULL on erasure, zone R5).
- Events recorded:
  - `REGISTRATION_CREATED`: on successful Telegram login
  - `AD_PUBLISHED`: on auto-moderation pass (Phase 1 Task 10)
  - `SEARCH_PERFORMED`: on search query submission (search view)
  - `CONTACT_INITIATED`: on contact button deep-link generation
- Admin metrics view `/admin/analytics/analyticsdashboard/`: aggregate counts by `event_type`/date.
- CLI command `show_metrics`: aggregates via ORM, outputs counts grouped by type/date.
- No PII beyond already-collected `telegram_id`.

**Artifacts:** `apps/analytics/models.py`, `apps/analytics/admin.py`, `apps/analytics/management/commands/show_metrics.py`, template snippet, integration hooks.
**Dependencies:** Phase 1 Task 4, Task 10
**Risks:** Event tracking gaps in bot vs web; privacy compliance.

---

## Task 2: Lifecycle Sweep Commands (decision J)

**Goal:** Idempotent management commands for scheduled cleanup and consent erasure.

**Acceptance Criteria:**
- `apps/core/management/commands/archive_sweep.py`:
  - Queries `ads` WHERE `status=PUBLISHED` AND `published_at < now() - interval '2 months'`
  - Uses `IX_ads_archive_sweep` partial index
  - Transitions matched ads to `ARCHIVED` status, sets `archived_at=now()`
  - `--dry-run` flag for safe verification (prints count only)
  - **Wrapped in `pg_advisory_xact_lock(1)` released at transaction commit/rollback (PgBouncer-safe, per Docker plan Task 9); use `from apps.core.utils.advisory_lock import advisory_lock`**
  - Logs count to stdout via `logger = logging.getLogger(__name__)` (rule 12)

- `apps/core/management/commands/delete_sweep.py`:
  - Queries `ads` WHERE `status=ARCHIVED` AND `published_at < now() - interval '4 months'`
  - Uses `IX_ads_delete_sweep` partial index
  - Deletes matched ads + CASCADE to `ad_images`
  - `--dry-run` flag for safe verification
  - **Wrapped in `pg_advisory_xact_lock(2)` released at transaction commit/rollback (PgBouncer-safe, per Docker plan Task 9); use `from apps.core.utils.advisory_lock import advisory_lock`**
  - Logs count via `logger`

- `apps/core/management/commands/consent_hard_delete.py`:
  - Queries `users` WHERE `consent_revoked_at IS NOT NULL` AND `consent_revoked_at < now() - interval '30 days'`
  - Uses `IX_users_erasure_sweep` index
  - Sets `telegram_id=NULL`, `username=NULL`
  - DELETE all user ads + images (CASCADE)
  - SET NULL `analytics_events.user_id` (preserves aggregates)
  - SET NULL `ModeratorActionLog.user_id` (preserves reason/admin/timestamp for audit)
  - `--dry-run` flag for safe verification
  - **Wrapped in `pg_advisory_xact_lock(3)` released at transaction commit/rollback (PgBouncer-safe, per Docker plan Task 9); use `from apps.core.utils.advisory_lock import advisory_lock`**
  - Logs via `logger`

- `apps/core/management/commands/sweep_drafts.py`:
  - Purges `Ad` rows with `status=DRAFT` where `created_at < now() - interval '30 minutes'` (zone C8/I)
  - **Wrapped in `pg_advisory_xact_lock(4)` released at transaction commit/rollback (PgBouncer-safe, per Docker plan Task 9); use `from apps.core.utils.advisory_lock import advisory_lock`**
  - `--dry-run` flag, logs via `logger`

- `apps/core/management/commands/cleanup_login_tokens.py`:
  - DELETE `login_tokens` where `expires_at < now()` OR (`consumed_at IS NOT NULL` AND `created_at < now() - interval '1 day'`) (zone C1)
  - **Wrapped in `pg_advisory_xact_lock(5)` released at transaction commit/rollback (PgBouncer-safe, per Docker plan Task 9); use `from apps.core.utils.advisory_lock import advisory_lock`**
  - `--dry-run` flag, logs via `logger`

**Artifacts:** 5 management command files in `apps/core/management/commands/`
**Dependencies:** Phase 1 Task 6, Phase 2 Tasks 4-5 (for context on purge patterns)
**Risks:** FK cascade; sweep/edit concurrency.

---

## Task 3: Lifecycle Index Verification (zone C4, R1)

**Goal:** Confirm lifecycle-related partial indexes exist; add guarded migration if missing.

**Acceptance Criteria:**
- Inspects existing migrations/DB state. The indexes are defined in `Ad.Meta.indexes` (Phase 1 Task 6) and `User.Meta.indexes`.
- Creates no-op if already present (guarded check).
- Adds ONLY if absent:
  - `IX_ads_archive_sweep`: `fields=['status','published_at']`, condition `Q(status=AdStatus.PUBLISHED)`
  - `IX_ads_delete_sweep`: `fields=['status','published_at']`, condition `Q(status=AdStatus.ARCHIVED)`
  - `IX_users_erasure_sweep`: `fields=['consent_revoked_at']` (zone R1, 30-day hard delete)
- `uv run manage.py migrate` succeeds.

**Artifacts:** `apps/core/migrations/000X_verify_lifecycle_indexes.py` or verification note.
**Dependencies:** Phase 1 Task 6
**Risks:** Accidental duplicate index if re-run.

---

## Task 4: nginx Security Hardening (zone R8)

**Goal:** Production media + rate limiting with exact headers.

**Acceptance Criteria:**
- `docker/nginx/nginx.conf` updated with:
  - `X-Content-Type-Options: nosniff always` on all responses
  - `X-Frame-Options: DENY always`
  - `Content-Security-Policy: default-src 'none'; img-src 'self' data:; object-src 'none'`
  - MIME whitelist: `image/jpeg` only for `/media/`; default `application/octet-stream`
  - `Content-Disposition: inline`
  - Script execution blocked: `location ~* /media/.*\.(php|py|cgi|pl|sh)$ { deny all; return 403; }`
  - Rate limiting zone `login_limit`: 10 req/sec burst 20 on `/login/`
  - Rate limiting zone `search_limit`: 20 req/sec burst 40 on `/search/`
- Media key format: UUID v4 (never sequential or guessable, zone R6)
- `USE_X_FORWARDED_HOST=True`, `SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO','https')`, `SECURE_SSL_REDIRECT=True` (Phase 1 Task 7)
- TLS termination via nginx (cert mount points configurable via env)

**Artifacts:** `docker/nginx/nginx.conf`, rate-limit configuration.
**Dependencies:** Phase 1 Task 8
**Risks:** Over-restrictive rate limiting; media accessibility.

---

## Task 5: CI/CD Quality Gates

**Goal:** Automated lint + types + tests on GitHub Actions.

**Acceptance Criteria:**
- `.github/workflows/ci.yml` created with jobs:
  - `build`: docker build verification
  - `lint`: `uv run ruff check src/` (select E,F,I,B,UP per project standard)
  - `typecheck`: `uv run basedpyright src/` (`typeCheckingMode="standard"`)
  - `test`: `uv run pytest` with coverage against real PostgreSQL
- `pyproject.toml` contains `[tool.ruff]` and `[tool.basedpyright]` config
- All gates green before merge.

**Artifacts:** `.github/workflows/ci.yml`, ruff/basedpyright config in `pyproject.toml`
**Dependencies:** Phase 1 Task 12
**Risks:** Environment drift; false positives in types.

---

## Task 6: Documentation Updates (English-only per rule 1)

**Goal:** Final wiki + deployment docs.

**Acceptance Criteria:**
- `docs/wiki/technical-specification.md`: Decision L (Plausible + AnalyticsEvent) finalized; Decision J (lifecycle timers) confirmed.
- `docs/wiki/architecture-structure.md`: Deployment section complete (systemd/cron examples, nginx hardening).
- `docs/wiki/db-structure.md`: Lifecycle indexes verified; `IX_users_erasure_sweep` documented.
- All docs English-only with proper frontmatter (doc-maintenance-rules).

**Artifacts:** Updated wiki files.
**Dependencies:** Tasks 1-5
**Risks:** Doc drift.

---

## Command-Name Contract (Docker Plan Task 9)

**Phase 4 commands (this file):**
| Command | Purpose | Advisory Lock |
|---------|---------|---------------|
| `archive_sweep` | PUBLISHED → ARCHIVED after 2 months | `pg_advisory_xact_lock(1)` |
| `delete_sweep` | ARCHIVED → DELETED after 4 months | `pg_advisory_xact_lock(2)` |
| `consent_hard_delete` | User erasure after 30 days | `pg_advisory_xact_lock(3)` |
| `sweep_drafts` | DRAFT cleanup after 30 min idle | `pg_advisory_xact_lock(4)` |
| `cleanup_login_tokens` | Expired/consumed token cleanup | `pg_advisory_xact_lock(5)` |

**Phase 2 commands (owned by 02_detailed_plan_moderation.md):**
| Command | Purpose | Advisory Lock |
|---------|---------|---------------|
| `purge_failed_ads` | ON_MODERATION_FAILED after 7 days | Phase 2 Task 4 |
| `purge_rejected_ads` | REJECTED after 90 days | Phase 2 Task 5 |

All 7 commands wired to scheduler service in `docker-compose.prod.yml` per Docker plan Task 9.

## Advisory Lock Specification

Each sweep command MUST use the shared transaction-scoped advisory-lock utility owned by the Docker Environment plan (Task 9, `apps/core/utils/advisory_lock.py`). The lock is `pg_advisory_xact_lock(lock_id)` — transaction-scoped, released automatically on commit/rollback, and PgBouncer-safe (session-scoped `pg_advisory_lock`/`pg_advisory_unlock` inline snippets are FORBIDDEN per the Docker plan's resolved C-1 finding and L-4 note).

```python
# In each management command — DO NOT inline a session-scoped snippet.
from apps.core.utils.advisory_lock import advisory_lock

with advisory_lock(lock_id):  # lock_id per table below; released at txn end
    # ... query + mutate within a single DB transaction ...
```

Lock IDs per command (must NOT collide — allocated by the Docker plan):
- `archive_sweep`: 1
- `delete_sweep`: 2
- `consent_hard_delete`: 3
- `sweep_drafts`: 4
- `cleanup_login_tokens`: 5

## Version Exactness (vs docs/wiki/packages.md)

- `django>=5.2.16,<6.0` — Django 5.2 LTS
- `psycopg[binary]>=3.2.0` — psycopg3 only (no psycopg2-binary)
- `django-storages`, `boto3` — **DEFERRED** (YAGNI phase 1; local MEDIA_ROOT via STORAGES)
- `celery`, `redis` — **DEFERRED** (management commands + systemd/cron per spec)
- `plausible` — **NO PYTHON PACKAGE** (JS snippet only per decision L)

## Rule Compliance Checklist

| Rule | Status | Evidence |
|------|--------|----------|
| 10 (StrEnum for constants) | OK | `AnalyticsEventType` in Task 1; all enums from Phase 1 Task 1 |
| 13 (Migrations) | OK | Task 3 creates guarded migration for indexes |
| 15 (Small modules/functions) | OK | Each command is isolated; analytics model separate from core |
| 1 (English-only) | OK | All task artifacts in English; doc-maintenance-rules applied |
| 12 (Logging not print) | OK | All sweeps use `logger = logging.getLogger(__name__)` |

## Deferred Items (Post-MVP)

- Self-hosted Plausible/Umami via Docker (decision L)
- Log aggregation (Loki/Promtail)
- Metrics (Prometheus/Grafana)
- Point-in-time recovery (WAL archiving)
- Multi-arch Docker builds
- Docker secrets for production
