---
id: db-retention
domain: database
tags:
  - database
  - retention
  - purge
  - cleanup
  - postgresql
related:
  - db-schema
  - db-indexes
  - db-enums
  - docker-deployment
---

## Purpose

Documents the soft-delete retention policies, purge sweep schedules, and the
`purge_deleted_ads` management command (AD-002). Single source of truth for how
long each ad status is retained before permanent deletion.

## Retention Policy

| Status | Retention | Sweep Command | Index |
|--------|-----------|---------------|-------|
| `DELETED` | 120 days | `purge_deleted_ads` | `IX_ads_purge_deleted` |
| `REJECTED` | 90 days | `purge_rejected_ads` | `IX_ads_rejected_sweep` |
| `ON_MODERATION_FAILED` | 7 days | `purge_failed_ads` | `IX_ads_purge_failed` |
| `ARCHIVED` | 4 months | `delete_sweep` | `IX_ads_delete_sweep` |
| `PUBLISHED` | 2 months (auto-archive) | `archive_sweep` | `IX_ads_archive_sweep` |
| `DRAFT` | 7 days | `sweep_drafts` | *(no index — full scan)* |

### Soft-delete model

All ad deletions are **soft deletes**: the `status` is set to `DELETED` and
`deleted_at` is populated. Ads remain in the database for 120 days to allow for
accidental-deletion recovery, after which the `purge_deleted_ads` command
hard-deletes them.

### Advisory lock

The `purge_deleted_ads` command acquires PostgreSQL advisory lock ID 11
(`AdvisoryLockId.PURGE_DELETED_ADS`) to prevent concurrent execution across
container restarts. Other sweeps use their own advisory lock IDs.

## Purge Sweep Commands

### purge_deleted_ads (AD-002)

```bash
# Run via management command
python src/backend/manage.py purge_deleted_ads

# Run inside Docker
docker compose --env-file .env.docker \
  -f docker-compose.yml -f docker-compose.dev.override.yml \
  run --rm web uv run python src/backend/manage.py purge_deleted_ads

# Run with dry-run to preview deletions without executing
docker compose --env-file .env.docker \
  -f docker-compose.yml -f docker-compose.dev.override.yml \
  run --rm web uv run python src/backend/manage.py purge_deleted_ads --dry-run
```

**Behavior:**
- Finds all ads with `status = 'DELETED'` and `deleted_at` older than
  `--retention-days` (default: 120, from `PURGE_DELETED_RETENTION_DAYS` env var).
- Hard-deletes matching rows (cascading to `ad_images` via `on_delete=CASCADE`).
- Uses `IX_ads_purge_deleted` partial index for efficient filtering.
- Acquires advisory lock 11; skips if another instance is running.
- `--dry-run` logs the count without deleting.

### Other sweeps

| Command | Env Var | Default | Description |
|---------|---------|---------|-------------|
| `archive_sweep` | `ARCHIVE_AGE_DAYS` | 60 | Archive PUBLISHED ads older than 2 months |
| `delete_sweep` | `DELETE_AGE_DAYS` | 120 | Hard-delete ARCHIVED ads older than 4 months |
| `purge_failed_ads` | `PURGE_FAILED_DAYS` | 7 | Delete ON_MODERATION_FAILED ads older than 7 days |
| `purge_rejected_ads` | `PURGE_REJECTED_DAYS` | 90 | Delete REJECTED ads older than 90 days |
| `sweep_drafts` | *(none)* | 7 days | Delete DRAFT ads older than 7 days |
| `consent_hard_delete` | `ERASURE_RETENTION_DAYS` | 30 | Hard-delete user PII after 30-day consent withdrawal |

## §3 Post-Withdrawal Data Retention

When a seller withdraws consent (GDPR Article 21 opt-out), the following lifecycle applies:

1. **T+0 (withdrawal):** `withdraw_consent()` executes atomically inside `transaction.atomic()`:
   - `consent_revoked_at = now()`, `is_deleted = True`, `deleted_at = now()`
   - `telegram_id` and `username` set to NULL (PII erasure)
   - All user `LoginToken` rows deleted (prevents re-login)
   - All user ads set to `DELETED` status with `deleted_at = now()` (soft-deleted, hidden from buyers)
   - DRAFT ads' media files deleted after transaction commits (TX-then-FS pattern)

2. **T+0 → 30 days (anonymized retained state):** User row retains `id`, empty PII fields, and `consent_revoked_at`. Ads remain soft-deleted (hidden from buyers, not searchable via FTS).

3. **T+30 days (hard-delete sweep):** `consent_hard_delete` management command (advisory lock 3) hard-deletes all user rows where `consent_revoked_at < now() - 30 days` (`ERASURE_RETENTION_DAYS=30`). This CASCADE-deletes:
   - All `Ad` rows belonging to the user (including `DELETED` status ads)
   - All `AdImage` rows (via `on_delete=CASCADE`)
   - All `SellerVerification` rows (via `on_delete=CASCADE`)
   - Physical ad-image files deleted via `delete_photo()` loop after transaction commits

   **Note:** This is a **30-day** hard-delete, distinct from `purge_deleted_ads` which uses a **120-day** retention window for all `DELETED`-status ads regardless of consent withdrawal. Consent-withdrawn users' ads are purged at 30 days; other soft-deleted ads persist until 120 days.

4. **Analytics:** `AnalyticsEvent.user_id` and `ModeratorActionLog.user_id` are SET NULL during the hard-delete (aggregates and audit trail preserved without PII linkage).

See also: [technical-specification.md Decision F](../01-spec/technical-specification.md) (lines 79–87).

## Configuration

```python
# Environment variables (set in .env.docker)
PURGE_DELETED_RETENTION_DAYS = 120  # days to keep soft-deleted ads before purging
ARCHIVE_AGE_DAYS = 60  # days before auto-archiving published ads
DELETE_AGE_DAYS = 120  # days before hard-deleting archived ads
PURGE_FAILED_DAYS = 7  # days to keep ON_MODERATION_FAILED ads
PURGE_REJECTED_DAYS = 90  # days to keep REJECTED ads
ERASURE_RETENTION_DAYS = 30  # days after consent withdrawal before hard-delete
```

## Scheduler

All sweep commands run hourly via the `scheduler` service
(`entrypoint-scheduler.sh`), which loops every hour and executes each sweep.
Each command is individually advisory-locked, so concurrent container restarts
won't cause duplicate work.
