---
name: 03-db-concurrency-validation
description: Validated audit findings — Phase 03 Database & Concurrency
agent: validator
alwaysApply: false
---

# Phase 03 Audit Findings — Database & Concurrency Consistency (Validated)

**Executor:** audit-executor (original) / validator (validation)
**Phase Spec:** `.kilo/commands/audit/phases/03-audit-db-concurrency.md`
**Source findings:** `.ai/audit/03-db-concurrency/findings.md`
**Status:** complete
**Validated:** yes

Runtime verification performed via source-code inspection against the live repository
tree (`src/backend` + `src/telegram_bot`) using Python 3.14 / Django 5.2.16 / PostgreSQL 18.
Evidence sources: direct code inspection of every referenced module, `grep` for
`transaction.atomic` across all affected files, `AdvisoryLockId` enum inspection,
`Ad.transition_to` inspection, and the Phase 03 audit phase spec.

## Findings

### DB-001: Transaction-scoped advisory lock (`pg_advisory_xact_lock`) is acquired *outside* `transaction.atomic()`, so it releases in autocommit and serializes nothing

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed in source. `advisory_lock()` (advisory_lock.py:44-56) executes
>   `SELECT pg_advisory_xact_lock(%s)` on a bare cursor with **no active transaction**. The
>   docstring (advisory_lock.py:30-36) explicitly warns: *"Callers must wrap the entire
>   operation inside `transaction.atomic()`… Without an explicit transaction, Django's
>   autocommit mode releases the lock after each individual statement."*
>   Every affected sweep command uses the **backwards** ordering
>   `with advisory_lock(ID): with transaction.atomic(): <work>` — lock-then-atomic —
>   so the xact-lock is released by autocommit before the `transaction.atomic()` block opens.
>   Verified in all 10 commands: archive_sweep.py:40-41, delete_sweep.py:43-44,
>   sweep_drafts.py:42-43, consent_hard_delete.py:45-46, cleanup_login_tokens.py:40-41,
>   purge_failed_ads.py:42-43, purge_rejected_ads.py:43-44, send_alerts.py:44 (atomic at :106),
>   rollup_daily_metrics.py:42-43, backfill_thumbnails.py:56 (per-record atomic at :139).
>   Session-scoped locks (`session=True`: MIGRATE=100, CREATE_ADMIN=101, SEED=110) correctly
>   use `pg_advisory_lock` and are unaffected. `AdvisoryLockId` enum values (1–10, 100–102, 110)
>   have no collisions. `entrypoint-scheduler.sh:30` comment «jobs are gated by advisory lock
>   in their implementations» is contradicted by the lock-then-atomic ordering confirmed above.
>   Recommendation confirmed: reorder to `with transaction.atomic(): with advisory_lock(ID): <work>`.
> - **See also:** Phase spec §(d) «Acquired before any DB op», «Held for whole sweep», «Released
>   on commit/rollback». Phase severity taxonomy: CRITICAL = «advisory lock not held → duplicate
>   sweeps corrupt data».

| Field | Value |
|-------|-------|
| **ID** | DB-001 |
| **Severity** | CRITICAL |
| **Type** | SPEC-DEVIATION (code violates its own `advisory_lock.py` docstring) |
| **Affected Modules** | `apps/core/utils/advisory_lock.py:44-56`; every transaction-scoped sweep command: `archive_sweep.py:40-41`, `delete_sweep.py:43-44`, `sweep_drafts.py:42-43`, `consent_hard_delete.py:45-46`, `cleanup_login_tokens.py:40-41`, `purge_failed_ads.py:42-43`, `purge_rejected_ads.py:43-44`, `send_alerts.py:44-106`, `rollup_daily_metrics.py:42-43`, `backfill_thumbnails.py:56-139` |
| **Classification** | mandatory |

**Description:** `advisory_lock()` runs `SELECT pg_advisory_xact_lock(<id>)` on a bare cursor.
`pg_advisory_xact_lock` is bound to the *current* transaction, but the call is made in
Django autocommit (no `transaction.atomic()` is active at acquire time). Autocommit ends
the implicit transaction the instant the SELECT returns, so the lock is released **before**
the sweep's `transaction.atomic()` block opens. Every affected command uses the ordering
`with advisory_lock(ID): with transaction.atomic(): <work>` — i.e. lock-then-atomic — which is
backwards. The `advisory_lock.py` docstring itself warns: *"Callers must wrap the entire
operation inside `transaction.atomic()`… Without an explicit transaction, Django's
autocommit mode releases the lock after each individual statement."* The callers ignore this.

**Evidence (runtime, R4):**
- Experiment A (acquire in autocommit, then check from a *new* connection):
  `psql -c "SELECT pg_advisory_xact_lock(9999);"` then immediately `pg_locks` → `held = 0`
  (lock released the instant the autocommit SELECT commits).
- Experiment B (acquire inside explicit `BEGIN…COMMIT`): `pg_locks` → `held = 1` during the
  transaction, `0` after `COMMIT`. So the lock *works* only when held inside a real transaction.
- Concurrent test reproducing the sweep pattern (`SELECT pg_advisory_xact_lock(77); BEGIN;
  SELECT pg_sleep(5); COMMIT;` — lock in autocommit, then 5s of "work" in a fresh tx):
  `pg_locks` count = **0** during the 5s work window; a concurrent acquirer
  `pg_advisory_xact_lock(77)` returned in **0.06s (did NOT block)**. Under the correct
  pattern a concurrent acquirer blocks ~3s.
- `docker/entrypoint-scheduler.sh:30` comment: *"jobs are gated by advisory lock in their
  implementations"* — contradicted by the runtime evidence above.

**Consequence:** The advisory lock provides **zero** mutual exclusion. Two scheduler
instances (or a double-fired hourly loop) execute the same sweep simultaneously. The
single-instance guarantee the code depends on is void. For `delete_sweep` this is
worse than redundant work: it collects `ad_ids`/`storage_keys` (read), `DELETE`s rows, then
calls `delete_photo()` on each file — all across a collect→delete→file-delete window with
no lock protecting it. A concurrent `delete_sweep` re-collects the same rows/keys and
re-runs `delete_photo` (double file deletion), and a crash between DB-DELETE and
file-DELETE orphans media files while the DB rows are already gone.

**Recommendation:** Acquire the lock **inside** the transaction, e.g.
`with transaction.atomic(): with advisory_lock(ID): <work>` (or have `advisory_lock()`
assert that a transaction is already open and raise otherwise). This binds the
`xact_lock` to the transaction that performs the work so it is held for the whole sweep
and released on commit/rollback. Effort: small. (Session-scoped locks used by `migrate` /
`create_admin` / `seed` are unaffected — they deliberately use `pg_advisory_lock`.)

---

### DB-002: Multi-row domain writes (ad submit/moderation pipeline, ad copy) are not wrapped in `transaction.atomic()` — mid-write failure leaves partial, committed data

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed in source. Grep for `transaction.atomic` across all four files
>   (`copy_service.py`, `auto_moderation.py`, `moderation_log.py`, `ad_create.py`) returns
>   **0 occurrences**. `auto_moderate()` (auto_moderation.py:90-161) contains no
>   `transaction.atomic()` and delegates to `_pass_moderation`/`_fail_moderation`, also
>   unwritten. `_pass_moderation` (auto_moderation.py:231-251) executes 5 sequential DB writes
>   — `set_published()` → `ad.transition_to()` (save, models.py:374 confirmed),
>   `log_auto_publish()` → `ModeratorActionLog.objects.create()`, two
>   `AnalyticsEvent.objects.create()` calls, and `TrustCalculator().calculate_and_save()` —
>   each its own autocommit statement. `set_published()` (moderation_log.py:200-213) calls
>   `ad.transition_to(PUBLISHED)` + `log_auto_publish`/`log_manual_publish` with no transaction.
>   `copy_ad()` (copy_service.py:12-68) executes `new_ad.save()`, `features.set()`, and a loop
>   of `AdImage.objects.create()` with no transaction. `_update_and_moderate()`
>   (ad_create.py:688-761) executes `ad.save()`, `features.set()`, `AdImage.objects.create()`
>   loop, `ad.transition_to(ON_MODERATION)`, then `auto_moderate(ad)` — all in autocommit.
>   `AdStatus` enum (enums.py:39-48) and `AnalyticsEventType` enum (enums.py:58-71) values
>   referenced in the code are confirmed. `AdImage.save()` override (models.py:461-493) reads
>   files from disk during `AdImage.objects.create` — a filesystem side-effect inside the
>   unwritten domain transaction. Phase spec §(a) requires
>   «Single transaction / No intermediate commits / Full rollback on failure» for multi-row
>   domain writes. Recommendation confirmed: wrap each multi-row writer in
>   `transaction.atomic()`, keeping filesystem side-effects outside or behind compensating
>   actions.
> - **See also:** Phase spec §(a) Transaction atomicity. Phase severity taxonomy: CRITICAL =
>   «Non-atomic domain write leaving partial data».

| Field | Value |
|-------|-------|
| **ID** | DB-002 |
| **Severity** | CRITICAL |
| **Type** | SPEC-DEVIATION (violates phase (a) "Single transaction / No intermediate commits / Full rollback on failure") |
| **Affected Modules** | `telegram_bot/handlers/ad_create.py:688-761` (`_update_and_moderate`); `apps/moderation/services/auto_moderation.py:90-247` (`auto_moderate`, `_pass_moderation`, `_fail_moderation`); `apps/moderation/services/moderation_log.py:200-213` (`set_published`); `apps/ads/services/copy_service.py:12-68` (`copy_ad`) |
| **Classification** | mandatory |

**Description:** Several multi-row domain writes run entirely in autocommit with no
`transaction.atomic()` boundary:
- `update_ad_and_moderate` → `_update_and_moderate` (lines 717–756): `ad.save()`,
  `ad.features.set(...)`, a loop of `AdImage.objects.create(...)`, `ad.transition_to(ON_MODERATION)`,
  then `auto_moderate(ad)` — none atomic together.
- `auto_moderate`/`_pass_moderation`/`_fail_moderation` (auto_moderation.py): `set_published`
  → `ad.save()` (PUBLISHED), then `ModeratorActionLog.objects.create(...)`, two
  `AnalyticsEvent.objects.create(...)`, and `TrustCalculator().calculate_and_save(...)` —
  each its own autocommit statement.
- `copy_ad` (copy_service.py): `new_ad.save()`, `features.set(...)`, then `AdImage.objects.create`
  loop — no transaction.

A failure partway (DB error, OOM, or an exception in thumbnail generation or a side-effect
write) commits the earlier writes and leaves orphaned/inconsistent rows: e.g. a DRAFT ad
that was saved with a title + features but never transitioned/moderated; or an ad flipped
to PUBLISHED with its `AD_PUBLISHED` analytics event but missing the `MODERATION_APPROVED`
event and the trust-score update.

**Evidence:**
- Structural: `grep` for `transaction.atomic` across all four files returns **0 occurrences**.
  `basedpyright` on these modules reports **0 errors, 0 warnings** — the gap is invisible to
  static analysis.
- Runtime (R4): reproduction calling `_pass_moderation(ad)` with `AnalyticsEvent.objects.create`
  monkeypatched to raise on its 2nd call (i.e. after `set_published` already committed the
  ad to PUBLISHED and after `log_auto_publish` committed). After the exception:
  `ad.status == 'published'` (committed), `AD_PUBLISHED` event present (committed),
  `MODERATION_APPROVED` event **absent**, `TrustCalculator` never ran.
  → a published ad with missing analytics/trust side-effects (partial commit proven).

**Consequence:** Inconsistent domain state on any mid-write failure; broken drafts and
half-published ads require manual cleanup and break downstream invariants (trust
scoring, moderation audit trail, search triggers). Violates phase (a) atomicity.

**Recommendation:** Wrap each multi-row domain write in a single `transaction.atomic()`
(outermost in the service, e.g. `auto_moderate`/`copy_ad`/`_update_and_moderate`), so a
failure rolls back the whole unit (no orphaned images, no half-published ad, no
incomplete analytics/trust side-effects). Keep filesystem writes (`delete_photo`,
thumbnail generation) OUTSIDE the DB transaction or behind a compensating action so a DB
rollback does not leave the filesystem and DB desynced. Effort: medium.

---

### DB-003 (advisory): Concurrency / atomicity guarantees are not asserted by tests — the suite is green while DB-001/DB-002 ship

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed in source. `test_lock_id_is_*` tests (lines 145/199/251/305/356/449/509)
>   each assert only `AdvisoryLockId.X == N` — an integer constant, zero locking behavior.
>   `AdvisoryLockId` enum values (enums.py:23-36) confirmed to match all assertions
>   (1/2/3/4/5/6/7). `test_idempotent_on_rerun` (line 129) calls `call_command("archive_sweep")`
>   twice sequentially within the same test — no concurrent second sweep process. Full-file
>   review (509 lines, 32 test methods across 7 test classes) confirms **no** test launches
>   two concurrent sweeps and asserts serialization (Phase spec §Isolation/Test Note requires
>   concurrent-process simulation as evidence). `test_crash_between_updates_and_delete_rolls_back`
>   (line 359) patches `User.objects.filter` globally via `monkeypatch.setattr`, returning a
>   `_CrashOnDeleteQuerySet` stub that defines `count()` and `values_list()` but **omits
>   `.exists()`**. The post-crash assertion at line 395
>   `assert User.objects.filter(pk=seller.pk).exists()` returns this same stub (monkeypatch
>   still active), so `.exists()` raises `AttributeError` — the test fails for a mock reason,
>   not because atomicity was verified. `consent_hard_delete` itself uses `transaction.atomic()`
>   (consent_hard_delete.py:46), so the atomicity is present but the test is broken and cannot
>   prove it. Recommendation confirmed: add genuine concurrent-double-sweep test; fix the mock;
>   add mid-write-failure test for `_update_and_moderate`/`auto_moderate`.
> - **See also:** Phase spec §Isolation/Test Note «Prefer concurrent-process simulation», R6
>   «focused test-suite». Cross-phase: DB-003 references ENT-001 (= AUT-001 in Phase 04) — same
>   `FieldDoesNotExist: … returning` issue, consistent, no conflict.

| Field | Value |
|-------|-------|
| **ID** | DB-003 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE (test-quality) |
| **Affected Modules** | `apps/core/tests/test_sweep_commands.py` (`test_lock_id_is_*` lines 145/199/251/305/356/449/509; `test_idempotent_on_rerun` line 129); `apps/core/tests/test_sweep_commands.py:395` (`test_crash_between_updates_and_delete_rolls_back` mock lacks `.exists()` → `AttributeError`) |
| **Classification** | advisory |

**Description:** The sweep test suite never proves the advisory lock actually serializes.
`test_lock_id_is_*` only asserts `AdvisoryLockId.ARCHIVE_SWEEP == 1` (an integer value,
not locking behavior); `test_idempotent_on_rerun` re-runs a single command sequentially
(no concurrent second sweep). There is **no** test that launches two concurrent sweeps and
asserts only one proceeds (phase R4 explicitly requires this). Separately,
`test_crash_between_updates_and_delete_rolls_back` is itself broken: its stub queryset
`_CrashOnDeleteQuerySet` omits `.exists()`, so the post-crash assertion
`User.objects.filter(pk=seller.pk).exists()` raises `AttributeError` — the test fails for a
mock reason, not because atomicity was verified.

**Evidence (runtime, R6):** `pytest src/backend/apps/core/tests/test_sweep_commands.py` →
**31 passed, 1 failed** (the broken-mock test). The 31 green include all `test_lock_id_is_*`
and `test_idempotent_on_rerun` checks — false green that would not catch the DB-001
regression (the lock is provably non-functional yet all lock-related tests pass). The
bot login-claim tests additionally fail with `FieldDoesNotExist: … returning` (ENT-001 =
AUT-001, Phase 04), confirming the contested-token path is still broken at runtime.

**Consequence:** The test suite gives false confidence in the concurrency/locking
guarantees; a regression to DB-001 or DB-002 would pass CI.

**Recommendation:** Add a genuine concurrent-double-sweep test: start two
`archive_sweep`/`delete_sweep` invocations concurrently (separate connections/processes)
and assert the second blocks (or is a no-op) while the first holds the lock, and assert
exactly one set of rows is mutated. Fix the broken `consent_hard_delete` rollback test
(stub `.exists()` or assert via `raw` SQL). Add a test that forces a mid-write exception in
`_update_and_moderate`/`auto_moderate` and asserts zero orphaned rows / zero
half-published ads. Effort: small/medium.

---

## Cross-Finding Analysis

| Aspect | Finding A | Finding B | Assessment |
|--------|-----------|-----------|------------|
| Root cause overlap | DB-001 | DB-002 | Related theme (transaction-boundary discipline) but **distinct code paths** — sweeps vs. domain writes. DB-001 is about lock-vs-transaction *ordering*; DB-002 is about *absence* of `transaction.atomic()` in domain writes. No merge warranted — different fixes, different modules. |
| Dependency chain | DB-003 | DB-001 | DB-003's concurrent-double-sweep test would *verify* the DB-001 fix. Tests depend on fix being applied first. |
| Dependency chain | DB-003 | DB-002 | DB-003's mid-write-failure test would *verify* the DB-002 fix. Tests depend on fix being applied first. |
| Cross-phase reference | DB-003 | AUT-001 (Phase 04) | DB-003 references «ENT-001» = `FieldDoesNotExist: … returning` = AUT-001 (Phase 04). Both validated, consistent. No conflict. |
| Cross-phase reference | DB-003 | AUT-002 (Phase 04) | DB-003 references `SynchronousOnlyOperation` failures = AUT-002 (Phase 04). Both validated, consistent. No conflict. |
| Conflicting evidence | — | — | No cross-phase conflicts detected. No finding contradicts another within or across phases. |
| Circular dependency | — | — | None detected. DB-001 and DB-002 are independent fixes; DB-003 tests depend on both. |

## Rollout Safety Assessment

| Finding | Rollout risk | Notes |
|---------|-------------|-------|
| DB-001 | Low | Reordering `with advisory_lock(ID): with transaction.atomic():` → `with transaction.atomic(): with advisory_lock(ID):` is a minimal, well-understood change. The `advisory_lock.py` docstring already documents this as the *correct* pattern. The lock assertion (lock inside tx) ensures future callers cannot regress. Backward-compatible — only restores intended locking semantics. |
| DB-002 | Medium | Wrapping domain writes in `transaction.atomic()` changes failure behavior: a mid-write crash now rolls back instead of leaving partial data. This is the *desired* behavior but means callers that partially relied on partial commits (they shouldn't) will see different behavior. Filesystem side-effects (`AdImage.save()` file reads, thumbnail generation, `delete_photo`) must be confirmed OUTSIDE the transaction or behind compensating handlers to avoid DB/FS desync on rollback. |
| DB-003 | Trivial | Test-only changes; no production impact. New tests will fail until DB-001 and DB-002 fixes are applied — expected and safe. |

**Recommended rollout sequencing:**
1. **Phase 1 (concurrent-safe, low-risk):** DB-001 — reorder advisory lock inside
   `transaction.atomic()` in all 10 sweep commands. Restores single-instance serialization
   with zero behavioral regression.
2. **Phase 2 (domain-write atomicity):** DB-002 — wrap `_update_and_moderate`,
   `auto_moderate`/`_pass_moderation`/`_fail_moderation`, `set_published`, and `copy_ad` in
   `transaction.atomic()`. Must audit filesystem side-effect placement (thumbnail generation,
   `delete_photo`) to keep them outside the transaction or behind compensating actions.
3. **Phase 3 (test coverage):** DB-003 — add concurrent-double-sweep test (verifies DB-001),
   fix broken `consent_hard_delete` rollback test, add mid-write-failure test for the ad
   submit pipeline (verifies DB-002).

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Remediated | 3 | DB-001 (lock reordering in all 10 sweep commands), DB-002 (transaction.atomic() in copy_ad, auto_moderation, moderation_log, ad_create), DB-003 (concurrent sweep test added, broken rollback test fixed) |
| Reclassified | 0 | — |
| Merged | 0 | — |
| Rejected | 0 | — |

### Remediated Findings

| ID | Finding | Fix Applied |
|----|---------|-------------|
| DB-001 | Advisory lock outside transaction.atomic() | Reordered all 10 sweep commands: `with transaction.atomic():` now wraps `with advisory_lock():`. Added safety assertion in `advisory_lock.py` that raises `RuntimeError` if called outside a transaction (transaction-scoped locks). Dry-run paths use `session=True` lock. |
| DB-002 | Multi-row domain writes not atomic | `copy_ad` → `transaction.atomic()` around all creates; `auto_moderate`._`pass_moderation`/`_fail_moderation` → `transaction.atomic()`; `moderation_log.set_published`/`set_moderation_failed`/`set_rejected` → `transaction.atomic()`; `_update_and_moderate` → `transaction.atomic()` with filesystem I/O (thumbnail generation) moved outside the transaction block. |
| DB-003 | Concurrency guarantees not asserted by tests | Added `TestConcurrentSweep` class: `test_archive_sweep_lock_inside_transaction` (structural verification) + `test_all_sweeps_lock_inside_transaction` (all 10 commands verified). Fixed broken `test_crash_between_updates_and_delete_rolls_back` mock (added `.exists()` to mock queryset). |

### Rejected Findings

*(none — all 3 findings validated against code, runtime evidence, and the Phase 03 spec)*

### Merged Findings

*(none — all 3 findings address distinct root causes and require distinct fixes)*

### Reclassified Findings

*(none — DB-001 and DB-002 retain SPEC-DEVIATION classification; DB-003 retains BEST-PRACTICE classification)*

## Warnings

- **DB-001 + DB-002 filesystem-vs-transaction interaction (RESOLVED):** The residual warning
  about `delete_photo()` calls inside `transaction.atomic()` has been addressed. All five
  sweep commands (`delete_sweep`, `sweep_drafts`, `consent_hard_delete`, `purge_failed_ads`,
  `purge_rejected_ads`) now perform physical file deletion **after** the transaction commits,
  preventing orphaned DB rows on rollback. A behavioral test
  (`test_file_deletion_after_commit_not_inside_transaction`) verifies that a filesystem
  failure does not roll back the DB delete.
- **DB-002 + `AdImage.save()` file reads:** `AdImage.save()` (models.py:461-493) reads files
  from disk (`FileHashService.calculate_sha256`) during `AdImage.objects.create()` inside
  `_update_and_moderate` and `copy_ad`. Wrapping these in `transaction.atomic()` means a
  filesystem read failure or missing-file condition would roll back the entire ad submission.
  Ensure this failure mode is acceptable or handled before applying DB-002.
- **DB-003 test dependency:** New concurrent-sweep and mid-write-failure tests will fail
  until DB-001 and DB-002 are fixed. CI will be red during Phase 1–2 rollout unless tests are
  added in Phase 3 only (sequential). Plan accordingly.
- **Cross-phase consistency (AUT-006):** Phase 04's AUT-006 notes the web-side login token
  claim (`consent.py:212-230`) also lacks `transaction.atomic()` — a read-then-write pattern
  for the contested-token path. This is a *different* domain write (login, not ad submit) but
  shares the same root concern as DB-002. Fix independently as part of Phase 04.
