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
| `ARCHIVED` | 2 months (from archived_at) | `delete_sweep` | `IX_ads_delete_sweep` |
| `PUBLISHED` | 2 months (auto-archive) | `archive_sweep` | `IX_ads_archive_sweep` |
| `DRAFT` | 30 minutes **of inactivity** | `sweep_drafts` (advisory lock 4) | `IX_ads_draft_sweep` |

The table names the **implemented** anchor of each sweep, which is not the same as a ratified
decision for every row. `delete_sweep` filters on `archived_at`; whether that is the *correct*
anchor is an open owner question (`AD-004` / `VAL-005`, gate Q4) and no code has changed. Read
that row as a description of the command, not as an endorsement of the anchor. The open gates
are listed in [ad-lifecycle-remediation-record.md](../99-agent/ad-lifecycle-remediation-record.md).

### Soft-delete model

All ad deletions are **soft deletes**: the `status` is set to `DELETED` and
`deleted_at` is populated. Ads remain in the database for 120 days to allow for
accidental-deletion recovery, after which the `purge_deleted_ads` command
hard-deletes them.

### Advisory lock

The `purge_deleted_ads` command acquires PostgreSQL advisory lock ID 11
(`AdvisoryLockId.PURGE_DELETED_ADS`) to prevent concurrent execution across
container restarts. Other sweeps use their own advisory lock IDs.

Every advisory-lock acquisition in the system, not only this one, is bounded by
the same connection-level `lock_timeout`; it is a connection setting, so it is
not configured per command.

## Purge Sweep Commands

### purge_deleted_ads (AD-002)

```bash
# Run via management command
python src/backend/manage.py purge_deleted_ads

# Run inside Docker
docker compose --env-file .env.dev \
  -f docker-compose.yml -f docker-compose.dev.override.yml \
  run --rm web uv run python src/backend/manage.py purge_deleted_ads

# Run with dry-run to preview deletions without executing
docker compose --env-file .env.dev \
  -f docker-compose.yml -f docker-compose.dev.override.yml \
  run --rm web uv run python src/backend/manage.py purge_deleted_ads --dry-run
```

**Behavior:**
- Finds all ads with `status = 'DELETED'` and `deleted_at` older than
  `deleted_at` is older than 120 days (hardcoded).
- Hard-deletes matching rows (cascading to `ad_images` via `on_delete=CASCADE`).
- Uses `IX_ads_purge_deleted` partial index for efficient filtering.
- Acquires advisory lock 11; a contending run blocks until the lock is granted, **bounded by the
  connection-level `lock_timeout`** (`LOCK_TIMEOUT_SECONDS`, default 10 s, set in
  `config/settings/base.py` `DATABASES["default"]["OPTIONS"]["options"]`). After the bound the run
  fails with `canceling statement due to lock timeout` (SQLSTATE `55P03`) and is retried on the next
  hourly scheduler tick.
- `--dry-run` logs the count without deleting.

### Other sweeps

| Command | Retention | Description |
|---------|-----------|-------------|
| `archive_sweep` | 60 days | Archive PUBLISHED ads older than 2 months |
| `delete_sweep` | 60 days | Hard-delete ARCHIVED ads older than 60 days (from archived_at) |
| `purge_failed_ads` | 7 days | Delete ON_MODERATION_FAILED ads older than 7 days |
| `purge_rejected_ads` | 90 days | Delete REJECTED ads older than 90 days |
| `sweep_drafts` | 30 minutes | Delete DRAFT ads with no seller activity for 30 minutes (`Ad.updated_at`) |
| `consent_hard_delete` | 30 days | Hard-delete user PII after 30-day consent withdrawal |

**`DRAFT` retention measures inactivity, not age.** The predicate is
`status = DRAFT AND updated_at < now() - interval '30 minutes'`. `updated_at` is
refreshed by the Telegram dialog heartbeat
(`telegram_bot.services.ad_data.orm.touch_draft`), which every handler registered on
an `AdCreateForm` state calls on entry, and by the web edit form's direct-save branch
for the ad's owner (`apps/ads/views/edit.py::ad_edit`). A seller who is actively
stepping through the dialog is therefore never reaped, however long the dialog takes;
a seller who stops for 30 minutes is. The window itself is unchanged and still
hardcoded — no environment variable or CLI argument (beyond `--dry-run`) is read for
it.

**Do not revert the predicate to `created_at`.** `created_at` measures age since
`/post`; with no heartbeat it reaps a seller who is still typing (finding 03-DB-003).
If the sweep ever reverts to `created_at`, the heartbeat becomes dead code and the
defect returns silently — no test in the suite fails.

**Do not remove the heartbeat.** Coverage is enforced by
`src/telegram_bot/tests/test_ad_create_heartbeat_coverage.py`, an AST guard that
fails if any handler registered on an `AdCreateForm` state does not call
`touch_draft`, or if any `AdCreateForm` state has no such handler. Adding a new
dialog state without a heartbeat fails that test.

**Staging TTL is an independent backstop, not a partner of `DRAFT` retention.**
`sweep_orphaned_media._STAGING_TTL_SECONDS` (2 h, hourly) is measured from each file's
**mtime**, while `DRAFT` retention is measured from the **database** `updated_at`. The
dialog heartbeat refreshes both (`touch_draft` for the row,
`telegram_bot.services.ad_data.media.touch_staging_photos` for the `staging/` files the
FSM still references), so a live dialog keeps both alive on one clock. The
pre-03-DB-003 comment "2 hours — safely beyond the 30-minute DRAFT retention" was true
only while the draft always died first and **is no longer the justification**. The
2-hour value is a hard backstop for *abandoned* uploads, not a bound on dialog length;
a dialog that goes silent still loses its row (30 min) before its files (2 h).

**`staging/` also holds files awaiting post-commit promotion (03-DB-005).**
`submit_ad` writes the `AdImage` row with the **permanent** key but defers the physical
`os.replace` to a `transaction.on_commit` callback, so a file is never visible to the
orphan sweep (`apps.media.management.commands.sweep_orphaned_media._walk_media_files`,
which excludes `staging/`) before its row commits. That closes the window in which a
promoted-but-uncommitted file could be classified as an orphan and deleted. The 2 h
**mtime** TTL is what bounds the remaining gap: between a committed `AdImage` row and
its promoted file, and — if the process is killed in that sub-millisecond window — it
reclaims the file and the dangling reference becomes permanent (accepted risk). A
rolled-back submission promotes nothing, so its staged file stays in `staging/` for the
same TTL, exactly like an abandoned upload.

## §3 Post-Withdrawal Data Retention

When a seller withdraws consent (GDPR Article 21 opt-out), the following lifecycle applies:

1. **T+0 (withdrawal):** `withdraw_consent()` executes atomically inside `transaction.atomic()`:
   - `consent_revoked_at = now()`, `is_deleted = True`, `deleted_at = now()`
   - `telegram_id` and `username` set to NULL (PII erasure)
   - All user `LoginToken` rows deleted (prevents re-login)
   - All user ads set to `DELETED` status with `deleted_at = now()` (soft-deleted, hidden from buyers)
   - DRAFT ads' media files deleted after transaction commits (TX-then-FS pattern)

2. **T+0 → 30 days (anonymized retained state):** User row retains `id`, empty PII fields, and `consent_revoked_at`. Ads remain soft-deleted (hidden from buyers, not searchable via FTS).

3. **T+30 days (hard-delete sweep):** `consent_hard_delete` management command (advisory lock 3) hard-deletes all user rows where `consent_revoked_at < now() - 30 days` (`hardcoded 30 days`). This CASCADE-deletes:
   - All `Ad` rows belonging to the user (including `DELETED` status ads)
   - All `AdImage` rows (via `on_delete=CASCADE`)
   - All `SellerVerification` rows (via `on_delete=CASCADE`)
    - Physical ad-image files (including thumbnail derivatives) deleted via `delete_photo()` loop (`apps.media.services.filesystem`) after transaction commits, using `AdImage.storage_keys()` to collect all key variants (image + `thumbnail_small/medium/large`). A key still referenced by another `AdImage` row is **skipped** by the `pre_delete` signal (`apps.media.signals`) — `copy_ad` shares keys instead of duplicating files, so unconditional deletion would destroy another ad's photo. That per-key reference check **is** the AD-003 fix; it retired as `64a9de6`. The receiver collects `storage_keys()`, drops the keys still referenced by any **other** `AdImage` row, and defers `delete_photo` for the remainder to `transaction.on_commit`. The exclusion of the row being deleted is load-bearing: `pre_delete` runs before the cascade, so an unexcluded existence check always matches the row itself and would silently stop all file cleanup, leaking every orphaned file.

   **Note:** This is a **30-day** hard-delete, distinct from `purge_deleted_ads` which uses a **120-day** retention window for all `DELETED`-status ads regardless of consent withdrawal. Consent-withdrawn users' ads are purged at 30 days; other soft-deleted ads persist until 120 days.

4. **Analytics:** `AnalyticsEvent.user_id` and `ModeratorActionLog.user_id` are SET NULL during the hard-delete (aggregates and audit trail preserved without PII linkage).

See also: [technical-specification.md Decision F](../01-spec/technical-specification.md) (lines 79–87).

## Configuration

All retention values are hardcoded in the respective management command source files. No environment variables or CLI arguments (beyond `--dry-run`) are read for retention durations. The values are: `archive_sweep` (60 days), `delete_sweep` (60 days), `purge_deleted_ads` (120 days), `purge_failed_ads` (7 days), `purge_rejected_ads` (90 days), `sweep_drafts` (30 minutes), `consent_hard_delete` (30 days).

Separately, `LOCK_TIMEOUT_SECONDS` (default 10) bounds every lock wait; it is a
connection setting, not a retention value.

**Transaction batching (finding 03-DB-008).** `archive_sweep` and
`recompute_normalized_prices` process their rows in per-batch transactions of
`_BATCH_SIZE = 500`, each committing before the next batch is read. `_BATCH_SIZE`
is a hardcoded module constant — a transaction-batching size, **not** a retention
duration, and deliberately not an environment variable or a CLI argument: it is
the number that bounds the production lock hold, so it must not be
operator-variable.

Because a transaction-scoped advisory lock (`pg_advisory_xact_lock`) is released
by the first batch `COMMIT`, these two commands hold a **session-scoped** lock
(`pg_advisory_lock(AdvisoryLockId.ARCHIVE_SWEEP)` /
`…RECOMPUTE_NORMALIZED_PRICES`) taken once and released when the sweep ends.
Every other sweep command keeps the transaction-scoped, PgBouncer-safe shape.
**A session-scoped advisory lock is not safe under PgBouncer transaction-mode
pooling; enabling the pgbouncer profile requires revisiting these two commands.**

`archive_sweep` acquires its lock (id 1) before its per-batch mutation loop; a
contending run blocks until the lock is granted, **bounded by the connection-level
`lock_timeout`** (`LOCK_TIMEOUT_SECONDS`, default 10 s). (The dry-run branch's
`count()` is issued only under `--dry-run`, so it does not run on the production
path.)

The retention-values sentence above is scoped to **durations**, not to the
transaction-batching constant. `recompute_normalized_prices` has **no retention
duration** — it is bounded by the table, not by a time window — and its
`_BATCH_SIZE` is a transaction size, not a retention value.

## Scheduler

All sweep commands run hourly via the `scheduler` service, which dispatches
them through the extracted module `apps.core.utils.scheduler`
(`python -m apps.core.utils.scheduler`, invoked by `entrypoint-scheduler.sh`).
The scheduler depends on `load_catalog` completing successfully (via `depends_on:
condition: service_completed_successfully` in `docker-compose.yml`/`docker-compose.prod.yml`).
Each command is individually advisory-locked, so concurrent container restarts
won't cause duplicate work.
