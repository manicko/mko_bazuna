# Phase 03 Audit Findings — Database & Concurrency Consistency (VALIDATED)

**Executor:** audit-executor
**Template:** `.ai/audit/templates/audit-findings.md`
**Status:** complete
**Validated:** yes

> **Validator scope note:** This report validates the findings in `03-db-concurrency/findings.md` only, against the current working tree. All static claims were independently reproduced via `grep` and targeted source reads; the mandatory runtime checks and lint/typecheck tooling outputs were not re-executed (no production deploy or Docker test DB available in this session). No source code was modified. Key path reconciliation: the findings file uses a shortened path notation (`src/telegram_bot/...`, `config/settings/base.py`); the actual repo paths are `src/telegram_bot/...` (bot code at repo-root `src/`, NOT under `src/backend/src/`) and `src/backend/config/settings/base.py`. Line numbers match within +/-1; one structural discrepancy is flagged in DB-001 and DB-003 Validation Notes.

Audit scope: dual-process Django (web gunicorn + aiogram bot) sharing one PostgreSQL 18 DB. Settings in `src/backend/config/settings/{base,dev,prod,test}.py`; bot at `src/telegram_bot/`; management commands at `src/backend/apps/*/management/commands/`.

## Mandatory Runtime Verification

| ID | Verification | Result | Evidence |
|---|---|---|---|
| R1 | Connection-exhaustion / held-beyond-request | **Deviation** (DB-001): connection held for process lifetime, never released/refreshed | `grep close_old_connections src/` = 0 matches (confirmed). `telegram_bot/main.py:43` registers only `AccountStateMiddleware()`; `:65` is the sole `dp.run_polling`. All bot ORM wrapped in `sync_to_async` (login.py:159, contact.py:143, ad_create.py:870, permissions.py:150, alerts.py, language.py, ad_copy.py). `grep select_for_update src/` = 0 matches. **Caveat (evidence quality):** the finding cites `conftest.py:164-165` as confirming "asgiref runs these ORM calls in the MAIN thread", but that comment actually states the opposite — "parks them on its shared single-worker thread, which lives in a separate thread-local context and therefore gets its OWN PostgreSQL backend." The "main thread" framing is incorrect, but the core deviation (no `close_old_connections` ever, `CONN_MAX_AGE=0` with no request cycle to trigger close) is valid regardless of thread. |
| R2 | Per-process CONN_MAX_AGE value + pooler compat | **PASS** (in assumed-correct tier) | `config/settings/base.py:186` `"CONN_MAX_AGE": 0`; `:175` and `:188` `"prepare_threshold": None`; `uv.lock` psycopg `3.3.4`; `docker-compose.prod.yml:100` pgbouncer profile, `:109` `PGBOUNCER_POOL_MODE=transaction`. Value 0 + prepared-stmt disabled is correct for PgBouncer transaction-mode. |
| R3 | Async/sync boundary static check | **PASS** (with caveat) | `sync_to_async` across all bot handlers confirmed (grep: 94 matches across `src/telegram_bot/`). `grep select_for_update src/` = 0 matches. `# pyright: ignore[reportGeneralTypeIssues]` appears on **every** production `transaction.atomic()` line verified via repo-wide grep (28 matches; all 23 production sites carry the suppression; test files use equivalent `# type: ignore`). Type suppressions noted. |
| R4 | Concurrency / transaction tests | **Deviation** (DB-002): max_ads count-then-commit TOCTOU; login-token correctly atomic | `grep select_for_update src/` = 0 matches (no RMW guard). `_validate_max_ads_per_user` (auto_moderation.py:196-204) is a pure `.count()` read. `auto_moderate` (93-165) calls count-check at `:154` and `_pass_moderation` at `:164` in separate transaction scopes. Login-token path corroborated: `_claim_login_token` (login.py:104-137) uses a genuine PostgreSQL `UPDATE ... RETURNING` (lines 120-131) with row-lock WHERE clause — correctly atomic, zero TOCTOU. |
| R5 | Orphaned connections / locks | **Deviations** (DB-001 + DB-004) | `advisory_lock` helper (advisory_lock.py:46-52) asserts `in_atomic_block` and raises `RuntimeError` if not in a transaction — corroborated. All sweeps wrap `advisory_lock` inside `transaction.atomic()` (archive_sweep.py:40, delete_sweep.py:43, sweep_drafts.py:42, consent_hard_delete.py:45). Sweeps delete media OUTSIDE the tx (delete_sweep.py:77-78, sweep_drafts.py:75-76, consent_hard_delete.py:89-90) — DB-004 gap. Bot never calls `close_old_connections` — DB-001 gap. |
| R6 | Linter + type-check + focused tests | **Not re-executed** (no runtime env); structurally consistent | `ruff`/`basedpyright` outputs ("All checks passed!"; "0 errors, 0 warnings") could not be re-run in this session (no `ruff`/`basedpyright` binary, no Docker test DB). Structural corroboration: consistent `# pyright: ignore` usage; `test_sweep_lock_structure.py` and `test_sweep_commands.py` exercise the lock/dispatch paths described in R5. |

## Findings

### DB-001: Bot process never closes DB connections — one connection held for process lifetime, no failover recovery

| Field | Value |
|-------|-------|
| **ID** | DB-001 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | src/telegram_bot/main.py, src/telegram_bot/handlers/{login,contact,ad_create}.py, src/telegram_bot/middlewares/permissions.py, config/settings/base.py |
| **Classification** | mandatory |

> **Validation Note:**
> - **Action:** validated (unchanged)
> - **Detail:** All structural claims reproduced verbatim against the working tree: `grep "close_old_connections" src/` = 0 matches (confirmed); `telegram_bot/main.py:43` registers only `AccountStateMiddleware()` with no DB-teardown middleware; `:65` is the sole `dp.run_polling(bot)`; `sync_to_async` wraps all bot ORM calls (login.py:159, contact.py:143, ad_create.py:870/1201, permissions.py:150, plus alerts.py, language.py, ad_copy.py); `base.py:186` `"CONN_MAX_AGE": 0`; `:175`/`:188` `prepare_threshold: None`; `uv.lock` psycopg 3.3.4; `docker-compose.prod.yml:100` pgbouncer tx-mode profile. The failover claim (`ensure_connection` does not re-validate a held non-None connection) is a real Django behavior, corroborated by the codebase's own `conftest.py:184-186` comment noting that `pg_terminate_backend` leaves Django's wrapper pointing at a dead socket (non-None) so the framework skips reconnect.
> - **Evidence-quality caveat:** The finding cites `conftest.py:164-165` as confirming "asgiref runs these ORM calls in the **MAIN** thread". That cited comment actually states the opposite — "parks them on its shared single-worker thread, which lives in a **separate thread-local context** and therefore gets its **OWN** PostgreSQL backend." The "main thread" framing is incorrect (it is a separate asgiref worker thread). However, the substance holds: with `thread_sensitive=True` (default) and no parent `AsyncToSync`, all bot ORM calls are funneled to asgiref's single shared worker thread, which holds one Django `BaseDatabaseWrapper` (thread-local); with `CONN_MAX_AGE=0` and no `close_old_connections` call anywhere in `src/`, that wrapper/connection is never closed or refreshed for the process lifetime, and Django's request-cycle hooks (`request_finished` → `close_old_connections`) never fire for bot updates. The deviation is valid; only the mechanistic "main thread" detail is mis-stated.
> - **Labeling collision (operational, not finding-invalidity):** The codebase's own `advisory_lock.py:34` docstring and `test_sweep_lock_structure.py:3` internally reference a **different** "DB-001" — the advisory-lock autocommit-release bug (lock acquired outside `transaction.atomic()`). That internal concern is already resolved (the helper asserts `in_atomic_block` and the test guards it). The Phase 03 audit's DB-001 is the bot-connection issue, a distinct root cause. This ID collision should be disambiguated at the orchestrator/merge layer to avoid confusion.
> - **See also:** R1/R5 evidence; `telegram_bot/tests/conftest.py:164-186` (worker-thread connection leak acknowledgement).

**Description:** The bot (aiogram `dp.run_polling`, `src/telegram_bot/main.py:65`) is a long-running async process that reaches the shared Django ORM exclusively through `@sync_to_async` helpers (`src/telegram_bot/handlers/ad_create.py:870`, `src/telegram_bot/handlers/login.py:159`, `src/telegram_bot/handlers/contact.py:143`, `src/telegram_bot/middlewares/permissions.py:150`). With `sync_to_async`'s default `thread_sensitive=True` and no parent `AsyncToSync` wrapper, asgiref parks these calls on a shared single worker thread that holds one Django `BaseDatabaseWrapper` (thread-local); all bot ORM calls share that one connection. Django's request-cycle hooks that call `close_old_connections()` never fire for bot updates. A repo-wide grep confirms `close_old_connections` appears ZERO times in `src/`, so the connection is never released or refreshed despite `CONN_MAX_AGE=0` (`config/settings/base.py:186`; referenced in comments at `src/telegram_bot/handlers/login.py:151` and `src/telegram_bot/handlers/contact.py:122`).

**Evidence:**
- `src/telegram_bot/main.py:43` — only `AccountStateMiddleware()` registered; `dp.run_polling(bot)` at `:65` is the sole lifecycle hook (no DB teardown).
- `config/settings/base.py:186` — `"CONN_MAX_AGE": 0` (intended: fresh connection per request).
- `grep -rn "close_old_connections" src/` → no matches.
- `grep -rn "select_for_update" src/` → no matches (no compensating row locks).
- `uv.lock` — `psycopg` 3.3.4 (psycopg3; `prepare_threshold: None` at `base.py:175,188` is valid for PgBouncer tx-mode, `docker-compose.prod.yml:100` pgbouncer profile).
- `src/telegram_bot/tests/conftest.py:164-168` — acknowledges sync_to_async worker-thread connection isolation and the failover hazard ("leaves Django's wrapper pointing at a dead socket (non-None), so the framework skips reconnect").

**Exact consequence:** (R1/R5) The bot permanently occupies one PostgreSQL connection slot for its entire lifetime instead of the documented per-request fresh connection. Under PgBouncer transaction-mode with a bounded pool, this slot is never returned; combined with gunicorn workers and the hourly scheduler, pool capacity can be exhausted and starve BOTH processes. Worse, if PostgreSQL restarts or fails over, Django's `ensure_connection()` does not re-validate a held (non-`None`) connection, so the bot's next ORM call raises `OperationalError` and `run_polling` has no reconnect — every subsequent handler fails until the bot is manually restarted, taking the bot fully offline on any DB blip.

**Recommendation:** Add an aiogram middleware that calls `close_old_connections()` at the end of each update's sync ORM work (or scope the sync bridge to open/close per invocation). Add DB-unavailability detection + reconnect around `dp.run_polling`. Effort: small. Priority: mandatory.

---

### DB-002: `max_ads_per_user` enforced via count-then-commit race (TOCTOU), no DB constraint, no row lock

| Field | Value |
|-------|-------|
| **ID** | DB-002 |
| **Severity** | HIGH |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | src/backend/apps/moderation/services/auto_moderation.py, src/backend/apps/moderation/services/moderation_log.py, src/telegram_bot/handlers/ad_create.py, src/backend/apps/moderation/views/review.py, src/backend/apps/ads/models.py |
| **Classification** | mandatory |

> **Validation Note:**
> - **Action:** validated (unchanged)
> - **Detail:** All claims reproduced verbatim. `_validate_max_ads_per_user` (auto_moderation.py:196-204) is a pure `Ad.objects.filter(...).count()` read returning `count < max_ads` — no lock, no transaction. `auto_moderate` (auto_moderation.py:93-165) invokes the count-check at `:154` as a bare read and the publish at `:164` via `_pass_moderation`, which opens its **own** `transaction.atomic()` (`:248`) → `set_published` (moderation_log.py:218, own `:218` tx) → `ad.transition_to(AdStatus.PUBLISHED)` (ads/models.py:477) committing after the count check returned. The count-check and the publish are therefore in separate transaction scopes. `Ad.Meta.constraints` (ads/models.py:317-344) contains only 6 status/timestamp `CheckConstraint`s — no per-user active-ad count constraint. `grep select_for_update src/` = 0. Web path: `review.py:64` (`get_object_or_404`) → `admin_actions.approve_ad` (`:40` → `set_published`) performs **no** count re-check. Bot path: `ad_create.py:1233` `auto_moderate(ad)`. Cross-process TOCTOU on the shared derived aggregate is real.
> - **Minor line-reference inaccuracy:** The finding cites `moderation_log.py:204` for `set_rejected`'s `transition_to`; the actual `transition_to(AdStatus.REJECTED)` call is at line `199` (line `:204` is inside the subsequent `log_manual_reject(...)` call). This does not affect the finding's substance.
> - **See also:** R4 evidence; `test_sweep_lock_structure.py` (advisory-lock ordering already guarded, distinct from this RMW gap).

**Description:** The per-seller active-ad cap `max_ads_per_user` (read from the `ModerationCriteria` singleton, `apps/moderation/models.py:52`) is enforced ONLY as a count-then-commit check with no database constraint and no row lock. In `auto_moderate`, `_validate_max_ads_per_user` (`auto_moderation.py:196-204`) issues `Ad.objects.filter(user_id=..., status__in=[PUBLISHED, ON_MODERATION]).count()` and returns `count < max_ads` — a pure READ. The actual publish runs in a SEPARATE `transaction.atomic()` block: `_pass_moderation` (`auto_moderation.py:241-261`) → `set_published` (`moderation_log.py:218-222`) → `ad.transition_to(AdStatus.PUBLISHED)` (`ads/models.py:425-438`) which COMMITs after the count check returned. There is no `select_for_update` anywhere in the codebase (grep: 0 matches) and no per-user ad-count constraint in `Ad.Meta` (`ads/models.py:253-344` holds only 6 status-timestamp `CheckConstraint`s — no count/aggregate constraint).

**Evidence:**
- `auto_moderation.py:196-204` — `Ad.objects.filter(...).count()` then `return count < max_ads` (read, no lock).
- `auto_moderation.py:154` — `_validate_max_ads_per_user(...)` called as a bare read; `auto_moderation.py:164` → `_pass_moderation(ad)` which opens its OWN `transaction.atomic()` at `:248`.
- `src/backend/apps/ads/models.py:317-344` — `class Meta` constraints are timestamp/state checks only; no `max_ads_per_user` enforcement.
- `grep -rn "select_for_update" src/` → no matches.
- Cross-process: bot `auto_moderate` (`ad_create.py:1233`) AND web manual `approve_ad` (`review.py:64-65` → `admin_actions.approve_ad` → `set_published`) both transition to PUBLISHED; the web path does NOT even re-run the count check.

**Exact consequence:** (R4) Two concurrent publish attempts — e.g., a seller whose `max_ads_per_user=2` submitting two near-identical drafts, or a bot auto-moderation racing a moderator's manual approve — both read `count=1` (1 < 2 → pass) and both COMMIT, yielding 3 active ads. The seller exceeds the configured publishing cap, bypassing a business/spam-control limit. This is an unguarded read-modify-write on a shared derived aggregate across the bot and web processes — exactly the cross-process lost-update class the phase targets.

**Recommendation:** [SELECTED approach: A -- application-level `select_for_update`] Fold the `max_ads_per_user` count check and the PUBLISHED transition into a single `transaction.atomic()` that locks the User row -- NOT a DB-level constraint. Rationale from codebase research: (1) `max_ads_per_user` is a dynamic value from the `ModerationCriteria` singleton (moderation/models.py:52, cached via `_get_cached_criteria` in auto_moderation.py:30-78), so a static exclusion/partial-unique constraint cannot enforce a dynamic threshold; (2) `Ad.Meta.constraints` (ads/models.py:317-344) contains only 6 `CheckConstraint`s -- zero aggregate/exclusion precedent in the codebase; (3) `grep select_for_update src/` = 0 matches -- no locking infrastructure exists yet, but the codebase's own `advisory_lock.py:29-34` docstring explicitly describes the "count-to-mutate sequence" as the codebase's advocated pattern for read-modify-write races; (4) the only `_claim_login_token` DB-side `UPDATE...RETURNING` precedent (login.py:119-137) is a handler-level atomic claim for a different entity, not a reusable model-layer constraint. Approach B is NOT viable -- PostgreSQL exclusion constraints cannot count rows per group against a dynamic cap. **Concrete changes:** (1) In `auto_moderate` (auto_moderation.py:154-164), wrap the `_validate_max_ads_per_user` check (line 154), the `_is_duplicate_title` check (line 159), and `_pass_moderation(ad)` (line 164) in a single outer `transaction.atomic()` that begins AFTER locking the user row: `User.objects.select_for_update(of='user').get(pk=ad.user_id)` (add `from apps.users.models import User` at module top). The existing inner `transaction.atomic()` in `_pass_moderation` (auto_moderation.py:248) and `set_published` (moderation_log.py:218) become savepoints -- Django supports nested `atomic()` as savepoints, so no behavioral change. If the count check fails, `_fail_moderation(ad)` (auto_moderation.py:224) runs within the same locked tx so the failure is atomic too. (2) In `admin_actions.approve_ad` (admin_actions.py:25-41), the web path currently performs NO count check at all (validation note #6) -- add `_validate_max_ads_per_user(ad.user_id, max_ads)` inside a `transaction.atomic()` that locks the same User row with `User.objects.select_for_update(of='user').get(pk=ad.user_id)` before delegating to `set_published` at line 40; import `_validate_max_ads_per_user` and the max_ads value from `apps.moderation.services.auto_moderation`. (3) Lock the **User** row (not the Ad row) because the cap is per-seller -- this serializes all concurrent publish attempts for the same user across both bot (ad_create.py:1233) and web (review.py:64 to admin_actions.py:40) processes. Under PgBouncer transaction-mode (confirmed: base.py:186 `CONN_MAX_AGE=0`, `:188` `prepare_threshold: None`, docker-compose.prod.yml:100), the lock is held for the tx duration and released at commit. Effort: medium. Priority: mandatory.

---

### DB-003: Moderation & ad-edit state-machine guard runs on stale in-memory instances (no refresh, no row lock)

| Field | Value |
|-------|-------|
| **ID** | DB-003 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | src/backend/apps/ads/models.py, src/backend/apps/moderation/services/moderation_log.py, src/backend/apps/moderation/admin_actions.py, src/backend/apps/moderation/views/review.py, src/backend/apps/ads/views/edit.py |
| **Classification** | mandatory |

> **Validation Note:**
> - **Action:** validated (unchanged)
> - **Detail:** `Ad.transition_to` (ads/models.py:349-469) reads `self.status` in-memory at `:397` (`current = AdStatus(self.status)`) and calls `self.save(update_fields=...)` at `:410`/`:477` — no `refresh_from_db()`, no `select_for_update`. Repo-wide: `grep refresh_from_db src/backend/apps` returns matches ONLY under `**/tests/` (100+ hits, all test files); `grep select_for_update src/` = 0 matches. All cited call sites confirmed: `review.py:64` (`approve_ad`) and `:85-89` (`reject_ad`) fetch via `get_object_or_404(Ad, ...)` with no lock/refresh; `edit.py:100` (ad_edit fetch), `:168` (reactivation transition), `:206` (text-edit transition, unmentioned in finding), `:269` (archive), `:303` (reactivate); `admin_actions.approve_ad` (`:40`) and `:soft_delete_ad` (`:104`) call `set_published`/`transition_to` on the passed instance. `moderation_log.set_published/set_rejected/set_moderation_failed` open their own `transaction.atomic()` (lines `:182`/`:198`/`:218`) and call `ad.transition_to(...)` on the passed instance. `archive_sweep` (lock 1, AdvisoryLockId.ARCHIVE_SWEEP=1) and `delete_sweep` (lock 2, AdvisoryLockId.DELETE_SWEEP=2) use `queryset.update()`/`:delete()` bulk ops (no per-row lock) on PUBLISHED/ARCHIVED ads hourly (docs/ops/docker-deployment.md:520-521). Cross-process contention with concurrent sweeps is real.
> - **Line-reference correction:** The finding cites `ads/models.py:572-591` as `Ad.save()`, but line 572 is `AdImage.save()` (the `AdImage` class begins at line 513). The `Ad` model (line 23) has **no** custom `save()` — it uses Django's default `Model.save()`. The substance is unaffected: `transition_to` operates on the in-memory instance with `self.save()` (Django default) and there is no `refresh_from_db` or `select_for_update` in production code. Separately, the finding cites `moderation_log.py:204` for `set_rejected`'s transition; the actual `transition_to(AdStatus.REJECTED)` is at line `:199`.
> - **Corroborating tests:** `test_sweep_commands.py:567-604` (`test_file_deletion_after_commit_not_inside_transaction`) proves `delete_photo` runs AFTER `transaction.atomic()` commits — confirming the bulk-update/delete sweep structure. `test_sweep_lock_structure.py:75-129` guards that advisory locks are acquired inside `transaction.atomic()`.
> - **See also:** R5 evidence; cross-process sweep structure (archive_sweep.py:40-64, delete_sweep.py:43-72).

**Description:** `Ad.transition_to` (`ads/models.py:349-469`) validates the transition matrix and applies side-effects against `self.status` and `self.original_published_at` read from the **in-memory** instance; it never calls `refresh_from_db()` and the caller holds no `select_for_update` lock. Every production call site fetches the `Ad` once at request entry and passes that stale instance through to `transition_to`: `review.py:64` `approve_ad` (`get_object_or_404(Ad, id=ad_id, status=ON_MODERATION)`), `review.py:85-89` `reject_ad`, `edit.py:100/168/206/269/303` (reactivate/reactivate text-edit/archive), and `moderation_log.set_published`/`set_rejected`/`set_moderation_failed` (`moderation_log.py:182,198,218` → `:183`/`:199`/`:219`) which call `ad.transition_to(...)` on the passed instance. A repo-wide grep shows `refresh_from_db` appears ONLY in test files (100+ hits, all under `**/tests/`) — never in `review.py`, `edit.py`, `admin_actions.py`, or `moderation_log.py` — and `select_for_update` appears ZERO times in `src/`.

**Evidence:**
- `ads/models.py:397` — `current = AdStatus(self.status)` (in-memory, stale).
- `ads/models.py:410,477` — `self.save(update_fields=...)` on the in-memory instance; the `Ad` model uses Django's default `save()` with no refresh.
- `grep -rn "refresh_from_db" src/backend/apps` → all hits under `**/tests/` only.
- `grep -rn "select_for_update" src/` → no matches.
- Cross-process contention source: `archive_sweep` (lock 1, `archive_sweep.py:40-64`) and `delete_sweep` (lock 2, `delete_sweep.py:43-72`) use `queryset.update()` / `queryset.delete()` (bulk, no per-row lock) on PUBLISHED/ARCHIVED ads hourly — see `docs/ops/docker-deployment.md:520-523`.

**Exact consequence:** (cross-process consistency) A concurrent sweep can ARCHIVE or hard-DELETE the ad between the moderation fetch and `transition_to`. Because `self.status` is stale, the transition-matrix guard is evaluated against the request-time snapshot, not current DB state: a moderator/seller can "resurrect" an ad that `archive_sweep`/`delete_sweep` already transitioned/removed, or `ad.save()` performs an `UPDATE ... WHERE id=pk` that matches 0 rows (row already deleted) and Django silently records success — leaving the DB inconsistent with the handler's in-memory assumption (e.g., `original_published_at` read stale, `published_by` not set). The state-machine contract is only as strong as the freshest read, which here is the request-time fetch.

**Recommendation:** [SELECTED approach: A -- `select_for_update(of='ad')` at fetch sites + `self.refresh_from_db()` in `Ad.transition_to`] Add a row-level lock on the `Ad` at every moderation/edit fetch site and insert `self.refresh_from_db()` at the top of `Ad.transition_to`. Rationale from codebase research: (1) All six transition call sites already open `transaction.atomic()` (set_published:218, set_rejected:198, set_moderation_failed:182, soft_delete_ad:103, _pass_moderation:248, _fail_moderation:231 -- each carrying `# pyright: ignore[reportGeneralTypeIssues]` per R3), so the codebase already has the transaction discipline for row-level locking; (2) `grep refresh_from_db src/backend/apps` returns matches ONLY under `**/tests/` (100+ hits, all test files) -- never in production -- so adding it in `transition_to` as a single chokepoint makes every caller safe without modifying each call site; (3) the hourly sweeps use `queryset.update()/queryset.delete()` (bulk ops that acquire row-level locks in PK order -- see archive_sweep.py:61, delete_sweep.py:72, purge_rejected_ads.py:73), so a single-row `select_for_update` will serialize naturally: moderation locks one row, sweeps lock rows in PK order, single-row-lock vs. bulk-lock = wait, not deadlock. Approach C (DB-side `UPDATE ... WHERE id=pk AND status=expected` with rowcount + retry) is NOT selected because: the only codebase precedent (`_claim_login_token` in login.py:119-137) is a handler-level `UPDATE...RETURNING` for a different entity, not a model-layer pattern; converting `transition_to` from `self.save(update_fields=...)` to `filter().update()` would bypass Django model `post_save` signals and break the established state-machine method; and `Ad` has no custom `save()` (confirmed by validation note: models.py:572-591 is `AdImage.save()`, not `Ad.save()`), so replacing the default `save()` is a larger departure from the codebase pattern than simply adding a lock + refresh. **Concrete changes:** (1) In `Ad.transition_to` (ads/models.py:349-477), insert `self.refresh_from_db()` as the first statement after the docstring (before line 397 `current = AdStatus(self.status)`); if the row was hard-deleted by a concurrent sweep, `refresh_from_db()` raises `Ad.DoesNotExist` -- catch and re-raise as `ValueError` so callers handle the stale-row case gracefully. (2) In `review.py:approve_ad` (line 64): fetch `Ad.objects.select_for_update(of='ad').get(id=ad_id, status=AdStatus.ON_MODERATION)` wrapped in `transaction.atomic()` covering `do_approve(ad, request.user.id)` at line 65. (3) In `review.py:reject_ad` (lines 85-89): same `select_for_update(of='ad')` pattern. (4) In `edit.py:ad_edit` (line 100): fetch with `select_for_update(of='ad')`; wrap the POST branch (field save at 157/194 + transition at 168/206) in `transaction.atomic()`. (5) In `edit.py:ad_archive` (line 257) and `ad_reactivate` (line 290): wrap in `transaction.atomic()` with `select_for_update(of='ad')`. No changes to `moderation_log.py` or `admin_actions.py` -- they receive the already-locked instance from the view-level fetch; their existing `transaction.atomic()` blocks become savepoints that preserve the lock. Effort: small. Priority: mandatory.

---

### DB-004: Sweep filesystem cleanup decoupled from the DB transaction — orphaned media on crash, no retry

| Field | Value |
|-------|-------|
| **ID** | DB-004 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | src/backend/apps/core/management/commands/{delete_sweep,sweep_drafts,consent_hard_delete}.py, src/telegram_bot/services/media.py |
| **Classification** | advisory |

> **Validation Note:**
> - **Action:** validated (unchanged)
> - **Detail:** All three sweep files confirmed to collect `storage_keys` INSIDE `transaction.atomic()`, call `queryset.delete()` (which commits at tx exit), then run the `delete_photo` loop at function-body indentation (outside the tx). `delete_sweep.py:77-78`, `sweep_drafts.py:75-76`, `consent_hard_delete.py:89-90` — all dedented to the `handle()` body, outside the `with transaction.atomic():` block. `delete_photo` is defined at `media.py:85`. Each sweep file's inline comment (delete_sweep.py:74-76, sweep_drafts.py:72-74, consent_hard_delete.py:86-88) explicitly states "Delete physical media after the transaction commits." `delete_photo` (media.py:85-123) has internal retry (3 attempts, exponential backoff) and swallows all exceptions (never raises), so a single file error does not abort the loop — BUT there is no dead-letter/pending-delete DB table and no reaper: a process crash between DB commit and file-deletion orphans files with no recovery path (already-deleted rows are never revisited by re-runs). `test_sweep_commands.py:567-604` corroborates the structural split (monkeypatches `delete_photo` to raise; asserts DB rows are gone despite file-deletion failure).
> - **See also:** R5 evidence; `delete_sweep.py:74-78`, `sweep_drafts.py:72-76`, `consent_hard_delete.py:86-90`.

**Description:** In `delete_sweep`, `sweep_drafts`, and `consent_hard_delete`, the physical media deletion (`delete_photo`) runs OUTSIDE the `transaction.atomic()` block that deletes the DB rows. The code collects `storage_keys` inside the tx, calls `queryset.delete()` (which COMMITs), then executes `for storage_key in storage_keys: delete_photo(storage_key)` AFTER the `with transaction.atomic():` block exits (`delete_sweep.py:63-79`; `sweep_drafts.py:62-77`; `consent_hard_delete.py:83-90`). The inline comment correctly worries about DB rollback orphaning rows, but the inverse failure mode is unhandled: a process crash (or a `delete_photo` exception mid-loop) AFTER the DB commit but BEFORE filesystem cleanup orphans media files on disk. Because the rows are already deleted, a re-run of the sweep will NOT re-attempt deletion of those keys — there is no outbox/orphan-reaper to recover them.

**Evidence:**
- `delete_sweep.py:63-79` — `ad_ids`/`storage_keys` collected in tx (lines 64-68); `queryset.delete()` at `:72` (tx commits); `delete_photo` loop at `:77-78` runs outside (function-body level, dedented from the `with`).
- `sweep_drafts.py:62-77` — same structure; `delete_photo` loop at `:75-76` outside tx.
- `consent_hard_delete.py:83-90` — `queryset.delete()` at `:84` (tx); `delete_photo` loop at `:89-90` outside tx.
- grep `delete_photo` definition: `telegram_bot/services/media.py:85`.

**Exact consequence:** (dimension a edge case: "A domain write partially commits due to a crash mid-transaction") A DB commit followed by a crash/error in the file-deletion pass orphans image files on the shared `media_volume` (growing storage leak); `pg_dump`/backup and the daily sweeps never revisit already-deleted ad rows, so orphaned files accumulate with no recovery path. Atomicity is split: DB side is atomic, filesystem side is not and is not idempotent/retryable.

**Recommendation:** [SELECTED approach: B -- pending-delete outbox + media-reaper command] Implement a durable outbox model + periodic reaper command. Rationale from codebase research: (1) All SIX media-deleting sweeps follow the identical pattern: `transaction.atomic()` + `advisory_lock(N)` to collect `image` keys then `queryset.delete()` then `delete_photo` outside tx (delete_sweep.py:43-79, sweep_drafts.py:42-77, purge_deleted_ads.py:44-79, purge_failed_ads.py:42-77, purge_rejected_ads.py:43-79, consent_hard_delete.py:45-90) -- the codebase's established management-command + advisory-lock architecture (AdvisoryLockId enum: IDs 1-12 for jobs, 100-111 for services, advisory_lock.py:36-37) is the natural template for the reaper; (2) `delete_photo` (media.py:85-123) already has 3-attempt exponential backoff and swallows all exceptions (never raises) -- the per-file error containment is already met; the gap is purely the crash-between-commit-and-delete window with no retry path; (3) `sweep_orphaned_media.py` exists as a broken filesystem-level backstop (`AdvisoryLockId.SWEEP_ORPHANED_MEDIA` at line 87 is NOT defined in the enum per NEW-ME-007, and it is unscheduled in entrypoint-scheduler.sh:28-37 -- providing zero working crash recovery); (4) Approach A (delete files BEFORE DB) is REJECTED because a DB rollback after file deletion leaves DB rows pointing to already-deleted files -- a worse data-integrity outcome than orphaned files (which are at most a storage leak). The pending-delete outbox converts the crash hazard into a recoverable, auditable workflow. **Concrete changes:** (1) Create a `MediaPendingDelete` model in `apps/core/models.py` (alongside `SiteConfig` per the shared-model convention): `storage_key` (CharField, max_length=64, db_index=True), `ad_image_id` (FK to AdImage, on_delete=SET_NULL, blank/null), `created_at` (DateTimeField, auto_now_add=True), `deleted_at` (DateTimeField, blank/null, set when file confirmed deleted). Table: `media_pending_deletes`; index: `IX_media_pending_deletes_created_at`. (2) Add `MEDIA_REAPER = 13` to `AdvisoryLockId` (enums.py:23-42) and document it in `advisory_lock.py:36-37` docstring. (3) In each of the SIX sweeps, inside the existing `transaction.atomic()` + `advisory_lock(N)` block: expand the storage-key collection to ALL four AdImage fields (`image`, `thumbnail_small`, `thumbnail_medium`, `thumbnail_large`) -- currently only `image` is collected (per ME-002) -- filter to non-null, then `MediaPendingDelete.objects.bulk_create([MediaPendingDelete(storage_key=k) for k in all_keys])` BEFORE `queryset.delete()` so the pending records commit atomically with the DB row deletion (either both commit or neither). (4) After the tx commits (same function-body level as the current `delete_photo` loop), change the file-deletion pass to: call `delete_photo(storage_key)` for each pending record, then `MediaPendingDelete.objects.filter(storage_key=k).delete()` to prune the record on completion; `delete_photo` is already idempotent (returns silently on `FileNotFoundError`), so exhausted-retry failures leave the record for the reaper. (5) Create `apps/core/management/commands/reap_pending_deletes.py` following the exact same `transaction.atomic()` + `advisory_lock(AdvisoryLockId.MEDIA_REAPER)` pattern as the existing sweeps: query `MediaPendingDelete.objects.filter(deleted_at__isnull=True)` in batches, call `delete_photo(storage_key)` on each, and on success set `deleted_at = timezone.now()` and `save(update_fields=['deleted_at'])` (leaving records whose files are gone marked as deleted for audit). Add `--dry-run`. (6) Add `reap_pending_deletes` to the `hourly_commands` list in `docker/entrypoint-scheduler.sh:28-37`. (7) Fix `sweep_orphaned_media.py` (NEW-ME-007): add `SWEEP_ORPHANED_MEDIA = 103` to the `AdvisoryLockId` enum and schedule it -- the outbox is the primary mechanism; the orphan sweep is a coarse filesystem-level backstop for any files that escape it. Rollout ordering: migration (model + lock ID 13) then reaper command + sweep modifications then scheduler entry then fix sweep_orphaned_media. No circular dependencies; the outbox records are atomic with the DB-delete, so a crash leaves either (rows + outbox) or (no rows + outbox only) -- never (no rows + orphaned file). Effort: medium. Priority: advisory.

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
- **DB-002 (HIGH):** Fold the `max_ads_per_user` count check inside the publish transaction under `User.objects.select_for_update(of='user')` on the User row on both bot (`auto_moderate`) and web (`admin_actions.approve_ad`) publish paths. Rejects DB-level constraint approach (dynamic cap cannot be a static constraint).
- **DB-003 (MEDIUM):** `select_for_update(of='ad')` at fetch sites in `review.py` and `edit.py`, plus `self.refresh_from_db()` in `Ad.transition_to` itself. Rejects DB-side rowcount precondition approach (would bypass `post_save` signals and depart from `self.save()` pattern).

## Advisory Recommendations

- **DB-004 (MEDIUM):** Pending-delete outbox table + `reap_pending_deletes` management command (AdvisoryLockId.MEDIA_REAPER=13). Rejects files-before-DB approach.

## Doc Updates Needed

- None. The documented two-process/one-DB model, advisory-lock allocation (`docker-deployment.md:143`, `migration-workflow.md:79-103`), and `CONN_MAX_AGE=0` + `prepare_threshold: None` (`packages-list.md:42,75`) are consistent with the code; the deviations above are implementation gaps, not doc drift.

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 4 | DB-001, DB-002, DB-003, DB-004 |
| Reclassified | 0 | — |
| Merged | 0 | — |
| Rejected | 0 | — |

### Rejected Findings

_None._ All 4 findings were verified against the current working tree and found technically correct, currently applicable, and architecturally sound. No stale, duplicate, or low-ROI findings.

### Merged Findings

_None._ Cross-finding analysis within this phase surfaced related concerns (all touch transaction/connection hygiene), but each has a distinct root cause:
- DB-001 (bot connection lifecycle) vs DB-003 (stale in-memory instance in `transition_to`) — both involve connection/transaction state, but DB-001 is about connection close/refresh at the bot boundary while DB-003 is about row-level staleness inside the state machine.
- DB-002 (max_ads count-then-commit) vs DB-003 (stale instance) — DB-002 is a read-modify-write race on a derived aggregate; DB-003 is a stale-read guard on the ad row.

No cross-phase conflicts were introduced (this validator did not read other phases; the orchestrator handles cross-phase merges).

### Reclassified Findings

_None._ DB-001 and DB-003 retain `SPEC-DEVIATION` (implementation violates the documented connection/transaction contract); DB-002 and DB-004 retain `BEST-PRACTICE`. The evidence-quality caveats (see Validation Notes) do not warrant reclassification — the underlying deviations are real.

### Rollout Safety

- **DB-001 (mandatory, HIGH):** Adding an aiogram `close_old_connections` middleware and a reconnect wrapper around `run_polling` is purely additive. The advisory-lock ordering is already enforced (`advisory_lock.py:46-52` asserts `in_atomic_block`); the new middleware does not interact with advisory locks, so no circular dependency or ordering conflict. Safe to introduce incrementally.
- **DB-002 (mandatory, HIGH):** Folding the count check inside the publish transaction with `User.objects.select_for_update(of='user')` introduces a row lock on the User row during publish. Under PgBouncer transaction-mode (confirmed: base.py:186 `CONN_MAX_AGE=0`, `:188` `prepare_threshold: None`, docker-compose.prod.yml:100), `SELECT FOR UPDATE` is fine; the lock is held for the tx duration and released at commit. Must be applied to BOTH bot (`auto_moderate`) and web (`admin_actions.approve_ad`) paths (partial rollout reintroduces the race). No circular dependency.
- **DB-003 (mandatory, MEDIUM):** `select_for_update(of='ad')` at fetch sites + `self.refresh_from_db()` in `transition_to` adds row locks on the Ad row. The moderation fetch + transition must be wrapped in `transaction.atomic()` (the inner `set_published`/`set_rejected` txs become savepoints). Lock contention with hourly sweeps (which use bulk `update()`/`delete()` acquiring PK-order row locks) is safe -- single-row lock vs bulk lock = wait, not deadlock. Sweeps already use advisory locks (1-4, 6, 7, 11); moderation does not acquire one, but the PK-ordered bulk locks prevent circular waits. No unsafe insertion points.
- **DB-004 (advisory, MEDIUM):** A pending-delete outbox (`MediaPendingDelete` model in apps/core/models.py) + `reap_pending_deletes` management command (AdvisoryLockId.MEDIA_REAPER=13) + scheduler entry. Rollout ordering: migration (model + lock ID 13) must run before the reaper starts consuming; the DB-delete must record the pending-delete BEFORE commit (same tx) so a crash leaves either (rows+outbox) or (no rows + outbox only). Also fix `sweep_orphaned_media.py` (NEW-ME-007: add enum entry `SWEEP_ORPHANED_MEDIA=103` + schedule it). No circular dependency.
- No hidden dependency chains detected. All fixes are independent and can ship in any order, though DB-001 and DB-003 are independent of DB-002/DB-004.

### Execution Validation

| Finding | Targets still exist? | Static verified? | Ready for execution |
|---------|----------------------|------------------|---------------------|
| DB-001 | Yes — main.py:43,65; base.py:186; login.py:151,159; contact.py:122,143; ad_create.py:870; permissions.py:150; conftest.py:164-165 | Yes (grep + file reads) | Yes — small (middleware + reconnect) |
| DB-002 | Yes — auto_moderation.py:154,154-204,248; moderation_log.py:218; review.py:64-65; admin_actions.py:40; ad_create.py:1233; ads/models.py:317-344 | Yes | Yes — medium |
| DB-003 | Yes — models.py:349-477,397; moderation_log.py:182,198,218; review.py:64,85-89; edit.py:100,168,206,269,303; archive_sweep.py:40; delete_sweep.py:43 | Yes (note: finding cites moderation_log.py:204, actual transition_to for REJECTED is at :199; finding cites models.py:572 for Ad.save but that is AdImage.save) | Yes — small |
| DB-004 | Yes — delete_sweep.py:43,72,77-78; sweep_drafts.py:42,70,75-76; consent_hard_delete.py:45,84,89-90; media.py:85 | Yes | Yes — medium |

### Warnings

1. **Evidence-quality discrepancy (DB-001):** The finding cites `telegram_bot/tests/conftest.py:164-165` as confirming "asgiref runs these ORM calls in the MAIN thread." The cited source actually states asgiref parks them on a **separate shared single-worker thread** (separate thread-local context, its own backend). The "main thread" framing is incorrect, though the substance (single shared connection, never closed) holds because all worker-thread sync_to_async calls are funneled to one asgiref worker thread. This mis-citation should be corrected when the fix is implemented.

2. **Line-reference inaccuracies (DB-002, DB-003):** DB-002 cites `moderation_log.py:204` for `set_rejected`'s `transition_to`; the actual call is at line `:199`. DB-003 cites `ads/models.py:572-591` as `Ad.save()`; that range is actually `AdImage.save()` (the `Ad` model has no custom `save()`, using Django's default). Neither affects finding validity, but the references should be corrected.

3. **Labeling collision (operational):** The codebase internally references a different concern as "DB-001" in `advisory_lock.py:34` (docstring) and `test_sweep_lock_structure.py:3` (advisory-lock autocommit-release bug — the lock must be acquired inside `transaction.atomic()`). That internal issue is already resolved and guarded by tests. The Phase 03 audit's DB-001 is the bot-connection issue (a distinct root cause). This ID collision must be disambiguated at the orchestrator/merge layer.

4. **Tooling outputs not re-executed (R6):** The `ruff` "All checks passed!" and `basedpyright` "0 errors, 0 warnings" claims could not be re-run in this session (no `ruff`/`basedpyright` binary available on the Windows shell, no Docker test DB). Structural evidence is consistent (uniform `# pyright: ignore[reportGeneralTypeIssues]` on all production `transaction.atomic()` lines; 23 production sites confirmed via repo-wide grep). Execution of DB-001's fix should include re-running `make test` to confirm no regressions in the bot connection/middleware surface.

5. **DB-004 partial mitigation already present:** `delete_photo` (media.py:85-123) already implements 3-attempt exponential backoff and swallows errors (never raises), so a single failing file does not abort the sweep loop. The finding's "at minimum" recommendation is partially met; the remaining gap is the lack of a dead-letter/pending-delete outbox for true crash recovery (a process crash between DB commit and file-deletion still orphans files).

6. **DB-002 cross-process gap:** The web `approve_ad` path (`review.py:64-65` → `admin_actions.approve_ad:40` → `set_published`) performs NO `max_ads_per_user` count check at all (unlike the bot path which calls `auto_moderate`). This means a moderator manual-approve can exceed the cap even without a race — a stricter finding than the TOCTOU alone. The recommendation (fold count check inside the publish tx) must therefore cover the web path explicitly.

### Required Fixes

1. **DB-001 (mandatory):** Register an aiogram update-scoped middleware that calls `close_old_connections()` after each bot update's sync ORM work; wrap `dp.run_polling` with DB-unavailability detection + reconnect (leverage the `connection_created` signal pattern already proven in `conftest.py:193-213` for production use).
2. **DB-002 (mandatory):** Fold the `_validate_max_ads_per_user` count inside the `transaction.atomic()` that performs the PUBLISHED transition, using `User.objects.select_for_update(of='user')` on the user row. Apply to BOTH bot (`auto_moderate`, auto_moderation.py:154-164) and web (`admin_actions.approve_ad`, add count check, admin_actions.py:25-41) paths. Rejects DB-level constraint (dynamic cap).
3. **DB-003 (mandatory):** In `review.py` and `edit.py`, add `select_for_update(of='ad')` to Ad fetches inside the `transaction.atomic()` that covers the transition. Insert `self.refresh_from_db()` at the top of `Ad.transition_to` (ads/models.py:349) as a single chokepoint. Rejects DB-side rowcount precondition (would bypass `post_save` signals).

### Advisory Recommendations

1. **DB-004:** Create `MediaPendingDelete` model (apps/core/models.py) + `reap_pending_deletes` command (AdvisoryLockId.MEDIA_REAPER=13) + scheduler entry. Record all 4 AdImage fields (`image`, `thumbnail_small`, `thumbnail_medium`, `thumbnail_large`) as pending-deletes inside the same tx as `queryset.delete()`. Reaper retries via existing `delete_photo` (already idempotent + retry-capable). Also fix `sweep_orphaned_media.py` (NEW-ME-007: add `SWEEP_ORPHANED_MEDIA=103` to enum + schedule it). Converts crash-orphaned-files hazard into a recoverable, auditable workflow.
2. **DB-002 (web path):** Add `_validate_max_ads_per_user` check (under User row lock) to `admin_actions.approve_ad`, since it currently bypasses the cap entirely -- this is not just a TOCTOU fix, it's adding a check that doesn't exist at all on the web path.
3. **DB-001 (conftest reuse):** The `connection_created` signal + `_close_all_thread_connections` pattern in `telegram_bot/tests/conftest.py:193-213` should be promoted to a production-safe connection-reaping helper, since it already solves the exact worker-thread connection leak the finding describes.
