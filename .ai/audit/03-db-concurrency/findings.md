# Phase 03 Audit Findings — Database & Concurrency Consistency

**Executor:** audit-executor
**Template:** .ai/audit/templates/audit-findings.md
**Status:** complete
**Validated:** no

Runtime evidence captured against the running test DB container `mko-bazuna-test-db-1` (pg 5433) and the production psycopg3 + PgBouncer-tx-mode profile. Lint/typecheck (R6): `ruff` = "All checks passed!"; `basedpyright` (advisory_lock, auto_moderation, review, edit) = "0 errors, 0 warnings". Note: the bot/sweep/login transaction calls carry `# pyright: ignore[reportGeneralTypeIssues]` suppressions on every `transaction.atomic()` line, hiding type regressions in transaction-demarcation code on the bot surface (DB-003 evidence).

## Findings

### DB-001: Bot process never closes DB connections — one connection held for process lifetime, no failover recovery

| Field | Value |
|-------|-------|
| **ID** | DB-001 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | src/telegram_bot/main.py, src/telegram_bot/handlers/{login,contact,ad_create}.py, src/telegram_bot/middlewares/permissions.py, config/settings/base.py |
| **Classification** | mandatory |

**Description:** The bot (aiogram `dp.run_polling`, `src/telegram_bot/main.py:65`) is a long-running async process that reaches the shared Django ORM exclusively through `@sync_to_async` helpers (`src/telegram_bot/handlers/ad_create.py:870`, `src/telegram_bot/handlers/login.py:159`, `src/telegram_bot/handlers/contact.py:143`, `src/telegram_bot/middlewares/permissions.py:150`). With `sync_to_async`'s default `thread_sensitive=True` and no parent `AsyncToSync` wrapper, asgiref runs these ORM calls in the MAIN thread (confirmed by `src/telegram_bot/tests/conftest.py:164-165`), so all bot ORM calls share Django's single per-thread connection. Django's request-cycle hooks that call `close_old_connections()` never fire for bot updates. A repo-wide grep confirms `close_old_connections` appears ZERO times in `src/`, so the connection is never released or refreshed despite `CONN_MAX_AGE=0` (`config/settings/base.py:186`, `src/telegram_bot/handlers/login.py:151`, `src/telegram_bot/handlers/contact.py:122`).

**Evidence:**
- `src/telegram_bot/main.py:43` — only `AccountStateMiddleware()` registered; `dp.run_polling(bot)` is the sole lifecycle hook (no DB teardown).
- `config/settings/base.py:186` — `"CONN_MAX_AGE": 0` (intended: fresh connection per request).
- `grep -rn "close_old_connections" src/` → no matches.
- `grep -rn "select_for_update" src/` → no matches (no compensating row locks).
- `uv.lock:791` — `psycopg` 3.3.4 (psycopg3; `prepare_threshold: None` at `base.py:175,188` is valid for PgBouncer tx-mode, `docker-compose.prod.yml:100` pgbouncer profile).

**Exact consequence:** (R1/R5) The bot permanently occupies one PostgreSQL connection slot for its entire lifetime instead of the documented per-request fresh connection. Under PgBouncer transaction-mode with a bounded pool, this slot is never returned; combined with gunicorn workers and the hourly scheduler, pool capacity can be exhausted and starve BOTH processes. Worse, if PostgreSQL restarts or fails over, Django's `ensure_connection()` does not re-validate a held (non-`None`) connection (`django/db/backends/utils.py` connect path), so the bot's next ORM call raises `OperationalError` and `run_polling` has no reconnect — every subsequent handler fails until the bot is manually restarted, taking the bot fully offline on any DB blip.

**Recommendation:** Add an aiogram middleware that calls `close_old_connections()` at the end of each update's sync ORM work (or scope the sync bridge to open/close per invocation). Add DB-unavailability detection + reconnect around `dp.run_polling`. Effort: small. Priority: recommended (mandatory classification — service availability/correctness).

---

### DB-002: `max_ads_per_user` enforced via count-then-commit race (TOCTOU), no DB constraint, no row lock

| Field | Value |
|-------|-------|
| **ID** | DB-002 |
| **Severity** | HIGH |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | src/backend/apps/moderation/services/auto_moderation.py, src/backend/apps/moderation/services/moderation_log.py, src/telegram_bot/handlers/ad_create.py, src/backend/apps/moderation/views/review.py, src/backend/apps/ads/models.py |
| **Classification** | mandatory |

**Description:** The per-seller active-ad cap `max_ads_per_user` (read from the `ModerationCriteria` singleton, `apps/moderation/models.py:52`) is enforced ONLY as a count-then-commit check with no database constraint and no row lock. In `auto_moderate`, `_validate_max_ads_per_user` (`auto_moderation.py:196-204`) issues `Ad.objects.filter(user_id=..., status__in=[PUBLISHED, ON_MODERATION]).count()` and returns `count < max_ads` — a pure READ. The actual publish runs in a SEPARATE `transaction.atomic()` block: `_pass_moderation` (`auto_moderation.py:241-261`) → `set_published` (`moderation_log.py:218-222`) → `ad.transition_to(AdStatus.PUBLISHED)` (`ads/models.py:425-438`) which COMMITs after the count check returned. There is no `select_for_update` anywhere in the codebase (grep: 0 matches) and no per-user ad-count constraint in `Ad.Meta` (`ads/models.py:253-344` holds only 6 status-timestamp `CheckConstraint`s — no count/aggregate constraint).

**Evidence:**
- `auto_moderation.py:196-204` — `Ad.objects.filter(...).count()` then `return count < max_ads` (read, no lock).
- `auto_moderation.py:164` — `_pass_moderation(ad)` is called OUTSIDE the count-check transaction; `set_published` (`moderation_log.py:218`) opens its OWN `transaction.atomic()`.
- `src/backend/apps/ads/models.py:253-344` — `class Meta` constraints are timestamp/state checks only; no `max_ads_per_user` enforcement.
- `grep -rn "select_for_update" src/` → no matches.
- Cross-process: bot `auto_moderate` (`ad_create.py:1233`) AND web manual `approve_ad` (`review.py:64-65` → `admin_actions.approve_ad` → `set_published`) both transition to PUBLISHED; the web path does NOT even re-run the count check.

**Exact consequence:** (R4 / dimension b) Two concurrent publish attempts — e.g., a seller whose `max_ads_per_user=2` submitting two near-identical drafts, or a bot auto-moderation racing a moderator's manual approve — both read `count=1` (1 < 2 → pass) and both COMMIT, yielding 3 active ads. The seller exceeds the configured publishing cap, bypassing a business/spam-control limit. This is an unguarded read-modify-write on a shared derived aggregate across the bot and web processes — exactly the cross-process lost-update class the phase targets.

**Recommendation:** Fold the count check INSIDE the single transaction that performs the PUBLISHED transition using `select_for_update(of=...)` on the user, or add a DB-level guard (partial unique index / exclusion constraint counting active ads per user). At minimum, re-check the count under `transaction.atomic(select_for_update)` immediately before `transition_to(PUBLISHED)` on both bot and web paths. Effort: medium. Priority: recommended (mandatory — business-rule correctness).

---

### DB-003: Moderation & ad-edit state-machine guard runs on stale in-memory instances (no refresh, no row lock)

| Field | Value |
|-------|-------|
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **ID** | DB-003 |
| **Affected Modules** | src/backend/apps/ads/models.py, src/backend/apps/moderation/services/moderation_log.py, src/backend/apps/moderation/admin_actions.py, src/backend/apps/moderation/views/review.py, src/backend/apps/ads/views/edit.py |
| **Classification** | mandatory |

**Description:** `Ad.transition_to` (`ads/models.py:349-469`) validates the transition matrix and applies side-effects against `self.status` and `self.original_published_at` read from the **in-memory** instance; it never calls `refresh_from_db()` and the caller holds no `select_for_update` lock. Every production call site fetches the `Ad` once at request entry and passes that stale instance through to `transition_to`: `review.py:64` `approve_ad` (`get_object_or_404(Ad, id=ad_id, status=ON_MODERATION)`), `review.py:85-89` `reject_ad`, `edit.py:100/168/269/303` (reactivate/reactivate text-edit), and `moderation_log.set_published`/`set_rejected`/`set_moderation_failed` (`moderation_log.py:183,204,219`) which call `ad.transition_to(...)` on the passed instance. A repo-wide grep shows `refresh_from_db` appears ONLY in test files (100+ hits, all under `**/tests/`) — never in `review.py`, `edit.py`, `admin_actions.py`, or `moderation_log.py` — and `select_for_update` appears ZERO times in `src/`.

**Evidence:**
- `ads/models.py:397` — `current = AdStatus(self.status)` (in-memory, stale).
- `ads/models.py:410,425-438` — `self.save(update_fields=...)` on the in-memory instance; `Ad.save()` (`ads/models.py:572-591`) does NOT refresh.
- `grep -rn "refresh_from_db" src/backend/apps` → all hits under `**/tests/` only.
- `grep -rn "select_for_update" src/` → no matches.
- Cross-process contention source: `archive_sweep` (lock 1, `archive_sweep.py:40-64`) and `delete_sweep` (lock 2, `delete_sweep.py:43-72`) use `queryset.update()` / `queryset.delete()` (bulk, no per-row lock) on PUBLISHED/ARCHIVED ads hourly — see `docs/ops/docker-deployment.md:520-523`.

**Exact consequence:** (dimension e / cross-process consistency) A concurrent sweep can ARCHIVE or hard-DELETE the ad between the moderation fetch and `transition_to`. Because `self.status` is stale, the transition-matrix guard is evaluated against the request-time snapshot, not current DB state: a moderator/seller can "resurrect" an ad that `archive_sweep`/`delete_sweep` already transitioned/removed, or `ad.save()` performs an `UPDATE ... WHERE id=pk` that matches 0 rows (row already deleted) and Django silently records success — leaving the DB inconsistent with the handler's in-memory assumption (e.g., `original_published_at` read stale, `published_by` not set). The state-machine contract is only as strong as the freshest read, which here is the request-time fetch.

**Recommendation:** `select_for_update(of=(...)` — or `nowait`/re-fetch — the `Ad` row inside the publish/edit/review transaction, then `refresh_from_db()` immediately before `transition_to`, or re-fetch-and-reenqueue the transition with a DB-side status precondition (e.g., `UPDATE ... WHERE id=pk AND status=expected` with rowcount check + retry). Effort: small. Priority: recommended (mandatory — state-machine correctness under concurrent sweeps).

---

### DB-004: Sweep filesystem cleanup decoupled from the DB transaction — orphaned media on crash, no retry

| Field | Value |
|-------|-------|
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **ID** | DB-004 |
| **Affected Modules** | src/backend/apps/core/management/commands/{delete_sweep,sweep_drafts,consent_hard_delete}.py, src/telegram_bot/services/media.py |
| **Classification** | advisory |

**Description:** In `delete_sweep`, `sweep_drafts`, and `consent_hard_delete`, the physical media deletion (`delete_photo`) runs OUTSIDE the `transaction.atomic()` block that deletes the DB rows. The code collects `storage_keys` inside the tx, calls `queryset.delete()` (which COMMITs), then executes `for storage_key in storage_keys: delete_photo(storage_key)` AFTER the `with transaction.atomic():` block exits (`delete_sweep.py:63-79`; `sweep_drafts.py:62-77`; `consent_hard_delete.py:69-90`). The inline comment correctly worries about DB rollback orphaning rows, but the inverse failure mode is unhandled: a process crash (or a `delete_photo` exception mid-loop) AFTER the DB commit but BEFORE filesystem cleanup orphans media files on disk. Because the rows are already deleted, a re-run of the sweep will NOT re-attempt deletion of those keys — there is no outbox/orphan-reaper to recover them.

**Evidence:**
- `delete_sweep.py:63-79` — `ad_ids`/`storage_keys` collected in tx; `queryset.delete()` (tx commits at `:72`); `delete_photo` loop at `:77` runs outside (lines 74-79 are at function-body level, dedented from the `with`).
- `sweep_drafts.py:62-77` — same structure; `delete_photo` loop at `:75-76` outside tx.
- `consent_hard_delete.py:83-90` — `queryset.delete()` at `:84` (tx), `delete_photo` loop at `:89-90` outside tx.
- grep `delete_photo` definition: `telegram_bot/services/media.py`.

**Exact consequence:** (dimension a edge case: "A domain write partially commits due to a crash mid-transaction") A DB commit followed by a crash/error in the file-deletion pass orphans image files on the shared `media_volume` (growing storage leak); `pg_dump`/backup and the daily sweeps never revisit already-deleted ad rows, so orphaned files accumulate with no recovery path. Atomicity is split: DB side is atomic, filesystem side is not and is not idempotent/retryable.

**Recommendation:** Either delete files BEFORE the DB delete (accepting that a rollback re-creates DB rows you'd re-clean — and dedup by key), or — preferred — keep file deletion outside the tx but record pending-deletes in a small DB table as part of the same tx and have a separate media-reaper sweep retry failed deletes idempotently. At minimum, wrap each `delete_photo` in try/except with retry + dead-letter logging so a single failing key does not abort the rest. Effort: medium. Priority: recommended (advisory — storage hygiene / auditability).

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH | 2 |
| MEDIUM | 2 |
| LOW | 0 |

## Mandatory Fixes

- **DB-001 (HIGH):** Add `close_old_connections()` per bot update (aiogram middleware) plus DB-unavailability reconnect around `dp.run_polling`.
- **DB-002 (HIGH):** Move `max_ads_per_user` count check inside the publish transaction under `select_for_update` (or enforce via a DB-level per-user active-ad constraint) on both bot and web publish paths.
- **DB-003 (MEDIUM):** `select_for_update`/`refresh_from_db` the `Ad` row immediately before `transition_to` in `review.py`, `edit.py`, `admin_actions.py`, and `moderation_log.py`; rely on a DB-side status precondition with rowcount + retry.

## Advisory Recommendations

- **DB-004 (MEDIUM):** Make sweep media cleanup idempotent/retryable with a pending-delete outbox + media-reaper so a crash after DB commit cannot orphan files silently.

## Doc Updates Needed

- None. The documented two-process/one-DB model, advisory-lock allocation (`docker-deployment.md:143`, `migration-workflow.md:79-103`), and `CONN_MAX_AGE=0` + `prepare_threshold: None` (`packages-list.md:42,75`) are consistent with the code; the deviations above are implementation gaps, not doc drift.

---

## Runtime Verification (R1–R6) Evidence

| ID | Verification | Evidence captured | Result |
|----|--------------|--------------------|--------|
| R1 | Connection-exhaustion / held-beyond-request | `close_old_connections` grep in `src/` = 0; bot `main.py:65` single `run_polling`; sync_to_async thread_sensitive → main-thread shared connection | **Deviation** (DB-001): one connection held for process lifetime, no release/refresh |
| R2 | Per-process CONN_MAX_AGE value + pooler compat | `base.py:186` `CONN_MAX_AGE: 0`; `base.py:175,188` `prepare_threshold: None`; `uv.lock` psycopg 3.3.4; `docker-compose.prod.yml:100` pgbouncer profile | Value 0 + prepared-stmt disabled — OK (in this phase's assumed-correct tier) |
| R3 | Async/sync boundary static check | grep `sync_to_async` across handlers (all ORM wrapped); grep `select_for_update`=0; `# pyright: ignore[reportGeneralTypeIssues]` on every `transaction.atomic()` in bot/login/sweeps | No unwrapped sync ORM in async handlers — OK; type suppressions noted in DB-003 |
| R4 | Concurrency / transaction tests | `grep select_for_update`=0 (no RMW guard); `max_ads_per_user` count-then-commit path traced | **Deviation** (DB-002) max_ads TOCTOU; login-token claim correctly atomic (UPDATE…RETURNING) |
| R5 | Orphaned connections / locks | Advisory-lock helper asserts active tx for xact-scoped locks; sweeps delete media outside tx | DB-004: orphaned-media-on-crash gap; DB-001: no connection close |
| R6 | Linter + type-check + focused tests | `ruff` = "All checks passed!"; `basedpyright` (advisory_lock/auto_moderation/review/edit) = "0 errors, 0 warnings" | Clean on checked surface |
