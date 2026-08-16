# Phase 03 Audit Findings — Database & Concurrency Consistency

**Executor:** audit-executor
**Phase Spec:** `.kilo/commands/audit/phases/03-audit-db-concurrency.md`
**Template:** `.ai/audit/templates/audit-findings.md`
**Status:** complete
**Validated:** no

Runtime verification performed host-side against a live PostgreSQL 18 (`audit-pg` on
127.0.0.1:5432 / `mko_bazuna`) and the dev DB behind the running `mko-bazuna-dev-web-1` /
`-bot-1` containers (5433), using the project `.venv` (Python 3.14 / Django 5.2.16).
`PYTHONPATH=src/backend;src`; `DJANGO_SETTINGS_MODULE=config.settings.test|dev`.

## Findings

### DB-001: Transaction-scoped advisory lock (`pg_advisory_xact_lock`) is acquired *outside* `transaction.atomic()`, so it releases in autocommit and serializes nothing

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
  `psql -c "SELECT pg_advisory_xact_lock(9999);"` then immediately `pg_locks` ? `held = 0`
  (lock released the instant the autocommit SELECT commits).
- Experiment B (acquire inside explicit `BEGIN…COMMIT`): `pg_locks` ? `held = 1` during the
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
worse than redundant work: it collects `ad_ids`?`storage_keys` (read), `DELETE`s rows, then
calls `delete_photo()` on each file — all across a collect?delete?file-delete window with
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

| Field | Value |
|-------|-------|
| **ID** | DB-002 |
| **Severity** | CRITICAL |
| **Type** | SPEC-DEVIATION (violates phase (a) "Single transaction / No intermediate commits / Full rollback on failure") |
| **Affected Modules** | `telegram_bot/handlers/ad_create.py:688-761` (`_update_and_moderate`); `apps/moderation/services/auto_moderation.py:90-247` (`auto_moderate`, `_pass_moderation`, `_fail_moderation`); `apps/moderation/services/moderation_log.py:200-213` (`set_published`); `apps/ads/services/copy_service.py:12-68` (`copy_ad`) |
| **Classification** | mandatory |

**Description:** Several multi-row domain writes run entirely in autocommit with no
`transaction.atomic()` boundary:
- `update_ad_and_moderate` ? `_update_and_moderate` (lines 717–756): `ad.save()`,
  `ad.features.set(...)`, a loop of `AdImage.objects.create(...)`, `ad.transition_to(ON_MODERATION)`,
  then `auto_moderate(ad)` — none atomic together.
- `auto_moderate`/`_pass_moderation`/`_fail_moderation` (auto_moderation.py): `set_published`
  ? `ad.save()` (PUBLISHED), then `ModeratorActionLog.objects.create(...)`, two
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
- Structural: `inspect.getsource(...)` for `copy_ad`, `auto_moderate`, `_pass_moderation`,
  `set_published` each reports **"transaction.atomic present: False"** (grep across all four
  files returns no `transaction.atomic` occurrence). `basedpyright` on these modules reports
  **0 errors, 0 warnings** — the gap is invisible to static analysis.
- Runtime (R4): reproduction calling `_pass_moderation(ad)` with `AnalyticsEvent.objects.create`
  monkeypatched to raise on its 2nd call (i.e. after `set_published` already committed the
  ad to PUBLISHED and after `log_auto_publish` committed). After the exception:
  `ad.status == 'published'` (committed), `AD_PUBLISHED` event present (committed),
  `MODERATION_APPROVED` event **absent**, `TrustCalculator` never ran.
  ? a published ad with missing analytics/trust side-effects (partial commit proven).

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

| Field | Value |
|-------|-------|
| **ID** | DB-003 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE (test-quality) |
| **Affected Modules** | `apps/core/tests/test_sweep_commands.py` (`test_lock_id_is_*` lines 145/199/251/305/357/450/509; `test_idempotent_on_rerun` line 129); `apps/core/tests/test_sweep_commands.py:395` (`test_crash_between_updates_and_delete_rolls_back` mock lacks `.exists()` ? `AttributeError`) |
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

**Evidence (runtime, R6):** `pytest src/backend/apps/core/tests/test_sweep_commands.py` ?
**31 passed, 1 failed** (the broken-mock test). The 31 green include all `test_lock_id_is_*`
and `test_idempotent_on_rerun` checks — false green that would not catch the DB-001
regression (the lock is provably non-functional yet all lock-related tests pass). The
bot login-claim tests additionally fail with `FieldDoesNotExist: ... returning`
(ENT-001), confirming the contested-token path is still broken at runtime.

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

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 2 |
| HIGH | 0 |
| MEDIUM | 1 |
| LOW | 0 |

## Mandatory Fixes
- **DB-001** — Fix advisory-lock ordering: acquire `pg_advisory_xact_lock` **inside**
  `transaction.atomic()` (`with transaction.atomic(): with advisory_lock(ID): <work>`) in
  every transaction-scoped sweep command (archive, delete, drafts, consent, login-token
  cleanup, purge-failed, purge-rejected, alerts, rollup, backfill). Restores single-instance
  serialization.
- **DB-002** — Wrap the bot ad-submit/moderation pipeline
  (`_update_and_moderate`, `auto_moderate`, `set_published`) and `copy_ad` in a single
  `transaction.atomic()` so mid-write failures roll back fully (no orphaned images, no
  half-published ads, no incomplete analytics/trust side-effects).

## Advisory Recommendations
- **DB-003** — Replace lock-integer tautology tests with a real concurrent-double-sweep
  serialization test; fix the broken `consent_hard_delete` rollback test (mock missing
  `.exists()`); add a mid-write-failure test asserting zero partial state for
  `_update_and_moderate`/`auto_moderate`.

## Doc Updates Needed
(None — all findings carry in-source code + runtime evidence. The `advisory_lock.py`
docstring already documents the *correct* pattern; DB-001 is a code deviation from it, so
the doc needs no change — only the callers.)
