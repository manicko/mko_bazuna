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
  - pii-consent-remediation-record
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
container restarts. Other sweeps use their own advisory lock IDs: `purge_consent_records` takes
**14** (`AdvisoryLockId.CONSENT_RECORD_SWEEP`), and the full allocation — which id belongs to
which job, and the reservation of ids below 100 for scheduled jobs — is tabulated in
`src/backend/apps/core/utils/advisory_lock.py`.

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

### purge_consent_records (06-PII-116)

```bash
# Preview the counts without mutating
python src/backend/manage.py purge_consent_records --dry-run

# Run via the scheduler (this is the normal path)
python src/backend/manage.py purge_consent_records
```

**Cadence: daily**, dispatched from `DAILY_COMMANDS` in `apps/core/utils/scheduler.py` on the
first hourly tick at or after **08:00 UTC**. Daily rather than hourly because both bounds are
multi-month: against a 5-year decision window an hourly sweep would find nothing eligible
essentially always. It is the **third** daily command (after `send_alerts` and
`rollup_daily_metrics`), so its **exit code is load-bearing**: `run_one_cycle` writes the durable
`scheduler_daily_state` marker only when *every* daily command exited `0`, and a non-zero entry
clears `hourly_marker`, which re-runs the whole daily set on the next hourly tick —
`send_alerts` is not idempotent, so that is not a free retry. The command therefore returns `0`
on every non-exceptional outcome, including an empty eligible set and `--dry-run`.

**Two windows, both hardcoded, both owner-ratified on 2026-10-03** (decision `Q-D4`):

| Window | Constant | Value | Fields it governs | What the sweep does |
|---|---|---|---|---|
| **Fingerprint** | `_FINGERPRINT_RETENTION_DAYS` | **90 days** | `user`, `session_key`, `ip_address`, `user_agent` | **clears** them |
| **Decision** | `_DECISION_RETENTION_DAYS` | **5 years** (`365 * 5`) | `choice`, `categories`, `consent_version`, `consent_given_at` | **retains** them at every age |

**Anonymise, never delete — and that is the point.** The command has no `DELETE` path. A row past
the decision window is still counted and still logged as *retained*, never removed. Deleting a
`ConsentRecord` would destroy the ability to **demonstrate that consent was given** (GDPR
Art. 7(1)) — the exact opposite failure from the unbounded-retention defect this sweep closes —
and it would contradict `privacy.html` §6, which already promises the data subject that the
consent log exists precisely so compliance can be demonstrated. The decision fields *are* the
evidence and must survive; only the identity material attached to them goes.

Mechanics that are load-bearing and easy to undo by accident:

- `user` and `session_key` are cleared in **one `UPDATE`**, never separately. An anonymous record
  is identified *by* `session_key`, so nulling `user` alone would leave the anonymised record
  re-identifiable through `django_session` — a live link the PII inventory does not declare.
- `user_agent` is **cleared to `""`, not nulled**: the column is `blank=True` and **not nullable**,
  so the action is a CLEAR, not a NULL. `ip_address` is set `NULL` (nullable).
- The sweep **asserts its own ordering**: `0 < _FINGERPRINT_RETENTION_DAYS <= _DECISION_RETENTION_DAYS`
  is checked before any work, so a mis-ordering fails loudly instead of quietly turning the
  fingerprint stage into a no-op. The fingerprint window is additionally **floored at the declared
  Django session lifetime** (`SESSION_COOKIE_AGE`, 14 days), so a run that lands while a session is
  still live cannot destroy that session's support evidence.
- `consent_given_at` is the leading column of `IX_consent_records_sweep`, so the fingerprint
  predicate is an index condition rather than a sequential scan.
- Batching is **off**. `ConsentRecord` grows by consent *actions*, not by requests, and is far
  below the row count that would justify `archive_sweep`'s keyset-batched shape.
- **There is deliberately no `--older-than` flag, no environment variable and no Django setting for
  either window.** A knob is exactly the thing that lets this document and the command drift apart:
  the values above are hardcoded module constants, and that is what makes the two a single fact.

**Advisory lock 14** (`AdvisoryLockId.CONSENT_RECORD_SWEEP`,
`src/backend/apps/core/enums.py`), acquired transaction-scoped inside `transaction.atomic()` and
therefore bounded by the same connection-level `lock_timeout` as every other sweep. A **fresh** id
was taken rather than reusing an existing one: this is a distinct destructive operation on a
distinct table and nothing in the suite catches an id collision. Ids are allocated from the
`AdvisoryLockId` table in `src/backend/apps/core/utils/advisory_lock.py`, which reserves **ids below
100 for scheduled jobs** (`1`–`14` transaction-scoped sweeps, `100`–`111` session-scoped
bootstrap jobs); re-read that table immediately before taking a new id, because id reuse across
two phases is a silent, collision-prone failure.

### purge_media_deletion_errors (07-MEDIA-010)

`delete_photo` records a `MediaDeletionError` row whenever a storage-key deletion exhausts all
retries; until this command shipped nothing bounded that table. Rows older than `--older-than`
days (**30 by default**) are **deleted**. The predicate filters on `created_at`, which carries
`idx_media_del_err_created`, so the eligible set is an index range scan.

```bash
# Mandatory first run — counts, deletes nothing
python src/backend/manage.py purge_media_deletion_errors --dry-run
# Optional override
python src/backend/manage.py purge_media_deletion_errors --older-than 90
```

- The purge is **irreversible** — a revert does not restore purged rows — so `--dry-run` is the
  mandatory first run.
- `--older-than` is **the one retention window this project deliberately exposes as a CLI knob**;
  all other retention durations are hardcoded module constants.
- The rows are **diagnostic, not personal data**: `storage_key` is an unguessable UUID (or a
  `seed/` filename), `error_type` is a class name, and `error_message` is `str(exc)[:1000]`.
- **Hourly**, advisory lock **15** (`AdvisoryLockId.PURGE_MEDIA_DELETION_ERRORS`). The command is
  hourly rather than daily because a daily command's non-zero exit is load-bearing for the durable
  daily marker; an hourly command only gates the liveness marker.
- The admin reader (`apps.media.admin.MediaDeletionErrorAdmin`) is **read-only** — no add, change or
  delete permission and no editable field.

### sweep_orphaned_media --check (07-MEDIA-012)

`sweep_orphaned_media --check` is the **non-destructive report** half of the store-versus-database
diff: it reports a dangling row (a referenced `AdImage` key whose file is absent) and orphan files,
then exits **non-zero** via `CommandError` when either count is non-zero, so an operator's cron or
monitoring observes the condition. The report scope **includes `seed/`** and probes each referenced
key verbatim; `staging/` is the sole suppression (its files are bounded by the mtime TTL). `--check`
is mutually exclusive with `--dry-run`, and the deletion counter now counts only files actually
removed.

### Other sweeps

| Command | Retention | Description |
|---------|-----------|-------------|
| `archive_sweep` | 60 days | Archive PUBLISHED ads older than 2 months |
| `delete_sweep` | 60 days | Hard-delete ARCHIVED ads older than 60 days (from archived_at) |
| `purge_failed_ads` | 7 days | Delete ON_MODERATION_FAILED ads older than 7 days |
| `purge_rejected_ads` | 90 days | Delete REJECTED ads older than 90 days |
| `sweep_drafts` | 30 minutes | Delete DRAFT ads with no seller activity for 30 minutes (`Ad.updated_at`) |
| `consent_hard_delete` | 30 days | Hard-delete user PII after 30-day consent withdrawal |
| `purge_media_deletion_errors` | 30 days (default) | **Hourly**, advisory lock 15. Deletes `MediaDeletionError` rows older than `--older-than` days (default 30, the one operator-overridable retention window). **Irreversible** — `--dry-run` is the mandatory first run. Admin reader is read-only. Diagnostic table, no PII (see [purge_media_deletion_errors](#purge_media_deletion_errors-07-media-010)) |
| `purge_consent_records` | 90 days (fingerprint) / 5 years (decision) | **Daily**, advisory lock 14. Anonymises the `ConsentRecord` fingerprint fields (`user`, `session_key`, `ip_address`, `user_agent`) at 90 days and retains the decision fields (`choice`, `categories`, `consent_version`, `consent_given_at`) for 5 years. **Never deletes rows** — see [purge_consent_records](#purge_consent_records-06-pii-116) |

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
    - Physical ad-image files (including thumbnail derivatives) deleted via `delete_photo()` loop (`apps.media.services.filesystem`) after transaction commits, using `AdImage.storage_keys()` to collect all key variants (image + `thumbnail_small/medium/large`). A key still referenced by **any** `AdImage` row is **skipped** — the reference check covers **all four** key columns in `apps.media.services.references.unreferenced_keys`. That per-key reference check **is** the AD-003 fix; it retired as `64a9de6` and was repaired to four columns at `59cc460`. The receiver captures `storage_keys()` by value at `pre_delete` time and evaluates the check **inside** the `transaction.on_commit` closure, after commit and unexcluded ("referenced by any row", `copy_ad` shares keys instead of duplicating files, so unconditional deletion would destroy another ad's photo). Evaluating after commit is what eliminates the multi-row-cascade leak of the earlier `pre_delete`-time shape, where two rows sharing a key in one cascade each saw the other still present and both skipped. `.exclude(pk=instance.pk)` is deliberately **absent**: by closure time the departing row is already gone, and `Collector` sets `instance.pk = None` after its `atomic()` block, so an exclusion would raise `ValueError`. Residual characteristics remain: in a multi-row cascade a shared key is freed once per departing row, and a concurrent insert between the reference query and the `unlink` is not closed.

   **Note:** This is a **30-day** hard-delete, distinct from `purge_deleted_ads` which uses a **120-day** retention window for all `DELETED`-status ads regardless of consent withdrawal. Consent-withdrawn users' ads are purged at 30 days; other soft-deleted ads persist until 120 days.

4. **Analytics:** `AnalyticsEvent.user_id` and `ModeratorActionLog.user_id` are SET NULL during the hard-delete (aggregates and audit trail preserved without PII linkage).

See also: [technical-specification.md Decision F](../01-spec/technical-specification.md) (lines 79–87).

## Configuration

All retention values are hardcoded in the respective management command source files. No environment variables or CLI arguments are read for retention durations, **with one deliberate exception**: `purge_media_deletion_errors --older-than` (default 30 days) exposes the `MediaDeletionError` diagnostic-table window as an operator knob (07-MEDIA-010). The values are: `archive_sweep` (60 days), `delete_sweep` (60 days), `purge_deleted_ads` (120 days), `purge_failed_ads` (7 days), `purge_rejected_ads` (90 days), `sweep_drafts` (30 minutes), `consent_hard_delete` (30 days), `purge_consent_records` (90-day fingerprint window / 5-year decision window), `purge_media_deletion_errors` (30 days, overridable).

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
The scheduler runs **10 hourly** commands (`archive_sweep`, `delete_sweep`,
`consent_hard_delete`, `sweep_drafts`, `sweep_orphaned_media`,
`cleanup_login_tokens`, `purge_failed_ads`, `purge_rejected_ads`,
`purge_deleted_ads`, `purge_media_deletion_errors`) and **3 daily** commands (`send_alerts`,
`rollup_daily_metrics`, `purge_consent_records` — all three fire at 08:00 UTC on
the first hourly tick at or after that hour; the daily set is gated on the
durable `scheduler_daily_state` marker, see
[db-schema.md](db-schema.md#scheduler_daily_state-singleton)).
The scheduler depends on `load_catalog` completing successfully (via `depends_on:
condition: service_completed_successfully` in `docker-compose.yml`/`docker-compose.prod.yml`).
Each command is individually advisory-locked, so concurrent container restarts
won't cause duplicate work.
