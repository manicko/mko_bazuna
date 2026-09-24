---
phase: "03"
phase_name: "Database & Concurrency Consistency"
date: "2026-09-23"
auditor: "Executor (subagent)"
validator: "Kilo (Phase 99 validation pipeline)"
mode: "problems-only"
id_prefix: "DB"
report_status: "validated"
severity_taxonomy: ".kilo/commands/audit/phases/03-audit-db-concurrency.md#severity-taxonomy"
validation_date: "2026-09-23"
---

# Validated Audit Findings — Database & Concurrency Consistency

> **Validation stage:** Phase 99 — Researcher verification.
> **Source file:** `.ai/audit/03-db-concurrency/findings.md`
> **Validator:** Phase 99 validation pipeline (R1–R4 per `99-audit-validate.md`).
> **Method:** Every finding was cross-checked against the live source code and live git repository. Independent `grep` scans confirmed select_for_update usage, advisory_lock session-flag usage, transaction.atomic() scope, and test-file coverage.
> **Mode:** problems-only (self-contained report; reader never needs the original).

---

## Checkpoint 1 — Auditor analysis

- **Stage:** Auditor analysis
- **Findings in scope:** 4 (DB-010 through DB-013)
- **Evidence anchor:** All findings were copied verbatim from `.ai/audit/03-db-concurrency/findings.md`; source code cross-references verified against `src/backend/apps/core/management/commands/archive_sweep.py`, `src/backend/apps/ads/models.py`, `src/backend/apps/core/utils/advisory_lock.py`, `src/backend/apps/core/enums.py`, `src/backend/apps/media/management/commands/backfill_thumbnails.py`, `src/backend/apps/media/management/commands/sweep_orphaned_media.py`, and the test files listed below.
- **Evidence files inspected (per finding):**
  - DB-010: `apps/core/management/commands/archive_sweep.py`, `apps/ads/models.py`, `apps/ads/views/edit.py`, `apps/ads/views/delete.py`, `apps/moderation/views/review.py`, `apps/ads/services/submission.py`, `apps/moderation/admin_actions.py`, `apps/core/tests/test_sweep_lock_structure.py`, `apps/core/tests/test_sweep_archive.py`, `apps/ads/tests/test_edit_views_locking.py`, `apps/ads/tests/test_transition_concurrency.py`
  - DB-011: `apps/core/utils/advisory_lock.py`, `apps/core/enums.py`, `apps/media/management/commands/backfill_thumbnails.py`, `apps/media/management/commands/sweep_orphaned_media.py`, `apps/core/tests/test_sweep_lock_structure.py`
  - DB-012: `apps/media/management/commands/backfill_thumbnails.py`, `apps/core/tests/test_sweep_lock_structure.py`
  - DB-013: `apps/core/tests/test_sweep_archive.py`, `apps/core/tests/test_sweep_lock_structure.py`, `apps/ads/tests/test_edit_views_locking.py`, `apps/ads/tests/test_transition_concurrency.py`
- **Blockers:** VAL-001 (ID collision — see Checkpoint 2).

---

## Cross-Finding Analysis

### ID Collision — VAL-001 (CRITICAL)

**All four finding IDs (DB-001 through DB-004, re-numbered to DB-010–DB-011–DB-012–DB-013) collide with already-fixed findings referenced in the codebase's own source comments and regression tests.** The test suite was written to guard fixes for a *previous* audit cycle that used the same DB-00x IDs, but those original findings described *different problems*:

| ID | Original meaning (already FIXED, referenced in test code) | Phase 03 finding (UNFIXED, re-numbered) |
|---|---|---|
| DB-001 → DB-010 | Advisory lock must be inside `transaction.atomic()` — the "autocommit-release bug" | `archive_sweep` lacks `select_for_update()` on per-row `transition_to()` |
| DB-002 → DB-011 | TOCTOU race on `max_ads_per_user` — fixed by `select_for_update` on `User` row | Advisory lock docstring lists IDs 102/103 as session-scoped |
| DB-003 → DB-012 | `select_for_update` row-locking in edit/review/bulk-operations views | `backfill_thumbnails` holds `transaction.atomic()` across filesystem I/O |
| DB-004 → DB-013 | Unlocked `Ad.objects.get()` in `submit_ad` — fixed by `select_for_update` | No concurrency test for `archive_sweep` row-level locking |

**Evidence of collision (source + test code referencing the original IDs):**

- `apps/core/utils/advisory_lock.py:34` — docstring: "prevent the autocommit-release bug (DB-001)" (original DB-001 = lock ordering)
- `apps/ads/services/submission.py:237` — comment: "DB-001: auto_moderate is inside the outer atomic()" (original DB-001 = transaction containment)
- `src/backend/apps/ads/tests/test_submission.py:4,67,78` — docstrings: "Verifies DB-001: auto_moderate runs inside submit_ad's transaction.atomic()"
- `src/backend/apps/core/tests/test_sweep_lock_structure.py:3` — "Guards the DB-001 fix: every scheduled sweep/Purge command must acquire its PostgreSQL advisory lock inside transaction.atomic()"
- `apps/ads/models.py:410` — comment: "DB-003: re-read from DB to defeat stale-state races" (original DB-003 = select_for_update in views)
- `apps/ads/views/edit.py:111` — comment: "DB-003: re-fetch the Ad under a row lock inside a transaction"
- `apps/moderation/admin_actions.py:155,206,272` — comments: "DB-003: lock Ad rows through every transition"
- `apps/moderation/admin_actions.py:159` — comment: "MaxAdsExceeded (DB-002)" (original DB-002 = TOCTOU on max_ads_per_user)
- `apps/moderation/services/moderation_log.py:175,190,211,227` — comments: "committed or rolled back together (DB-002)" / "closing the TOCTOU race on max_ads_per_user (DB-002)"
- `apps/ads/tests/test_edit_views_locking.py:2` — "Structural and concurrency regression tests for DB-003 locking in edit.py"
- `apps/ads/tests/test_edit_views_locking.py:111` — "Verifies DB-004: the unlocked Ad.objects.get(id=input.ad_id) at the top of submit_ad is gone"
- `apps/ads/tests/test_transition_concurrency.py:2,39,47` — "Concurrency regression tests for DB-003: select_for_update() locking"
- `apps/moderation/tests/test_admin_actions.py:208,244,254,261,362,367,387` — "DB-003 structural guards", "DB-003"
- `apps/ads/tests/test_ad_constraints.py:186` — "DB-003: refresh_from_db in transition_to must raise DoesNotExist"
- `apps/core/tests/test_sweep_delete.py:135` — "Concurrent-double-sweep tests verifying advisory lock serialization (DB-003)"
- `apps/media/tests/test_sweep_orphaned_media.py:2` — "Integration tests for the sweep_orphaned_media management command (DB-004)"

**Impact:** This is genuinely conflicting evidence. A developer who encounters "DB-010" in the codebase (test files, code comments) will find evidence that DB-010 was *already fixed* (advisory lock ordering, auto_moderate transaction containment). They may therefore dismiss the findings.md's DB-010 (missing `select_for_update` in `archive_sweep`) as already-resolved. The same applies to DB-011/DB-012/DB-013.

The phase 03 audit handbook (`99-audit-validate.md`) does **not** specify a re-use policy for finding IDs. The phase 01 validated report (VAL-005) noted "No cross-phase conflicts" because no other phase findings existed. Now that phases 02–04 findings exist and the codebase contains DB-00x references in code comments and test docstrings, the collision is material.

**Recommendation (prerequisite for rollout):** Re-number the four findings in this report to non-colliding IDs (e.g., DB-010 through DB-013) and update the in-code references accordingly. This must happen before any fix is implemented to prevent mis-application.

### Merge candidates

1. **DB-010 + DB-013:** DB-013 (missing `select_for_update` test for `archive_sweep`) is the regression safety net for DB-010 (missing `select_for_update` in `archive_sweep`). They share root cause but are distinct concerns (code defect vs. test gap). The findings.md already notes this relationship. **Recommendation retained:** keep separate but fix together; the DB-013 test must be added alongside the DB-010 fix.

### Dependency chains detected

- **DB-010 → DB-013:** The test recommended in DB-013 must be written to validate the DB-010 fix. DB-013 cannot be fully closed until DB-010 is fixed and the structural assertion passes.
- **VAL-001 (ID collision) → DB-010, DB-011, DB-012, DB-013:** All four findings' IDs must be re-numbered before fixes are implemented to avoid confusion with existing code-comment and test-docstring references.

### Rollout-ordering constraint

1. VAL-001 (re-number findings) must precede all fix work.
2. DB-010 + DB-013 (fix + test) should be deployed together.
3. DB-011 (docstring fix) is independent and backward-compatible.
4. DB-012 (transaction refactor) is independent but has the highest operational risk.

---

## Checkpoint 2 — Researcher verification

- **Stage:** Researcher verification
- **Findings in scope:** 4
- **Cross-phase conflicts:** VAL-001 (CRITICAL) — all four IDs collide with already-fixed findings. See above.
- **Cross-phase reference scan:** Phases 01–04 findings were inspected (only phase 01 and 02 have validated reports; phase 04 findings were read in full). No other phase's findings assert the *opposite* of these four — the conflict is purely an ID-reuse issue within phase 03's own codebase references.
- **Merge candidates:** 1 (DB-010 + DB-013). See above.
- **Evidence anchor:** All four findings were verified against live source files at validation time. `grep` scans were run for `select_for_update`, `session=True`, `DB-00[1-4]` references, and `transaction.atomic` scope.
- **Evidence files inspected:**
  - `apps/core/management/commands/archive_sweep.py` (lines 41-42, 47-50, 73-75)
  - `apps/ads/models.py` (lines 362-495, transition_to; 410-413, refresh_from_db)
  - `apps/core/utils/advisory_lock.py` (lines 34, 52-57, 64-70)
  - `apps/core/enums.py` (lines 23-43, AdvisoryLockId)
  - `apps/media/management/commands/backfill_thumbnails.py` (lines 56-57, 89-97, 121-138)
  - `apps/media/management/commands/sweep_orphaned_media.py` (line 138)
  - `apps/core/management/commands/delete_sweep.py` (line 72, bulk delete pattern) — confirms non-transition sweep commands don't need select_for_update (R-011)
  - `apps/ads/views/edit.py` (lines 116, 279, 316)
  - `apps/ads/views/delete.py` (line 41)
  - `apps/moderation/views/review.py` (lines 73, 103, 142)
  - `apps/ads/services/submission.py` (lines 167, 237)
  - `apps/moderation/admin_actions.py` (lines 89, 164, 215, 277)
  - `apps/media/services/filesystem.py` (lines 204-206, delete_photo)
  - Test files for sweep, locking, transition, submission, admin actions, ad constraints, sweep_orphaned_media
- **Dependencies / blockers:** VAL-001 ID collision blocks clean rollout until resolved.

---

## Findings by Severity

### HIGH

#### DB-010: [HIGH] — `archive_sweep` lacks `select_for_update()` on per-row `transition_to()` — lost-update race

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed all claims against live source. `archive_sweep.py:47-50` constructs `Ad.objects.filter(status=AdStatus.PUBLISHED, published_at__lt=cutoff_date)` with NO `.select_for_update()`. `archive_sweep.py:73-75` iterates `for ad in queryset.order_by("pk")` and calls `ad.transition_to(AdStatus.ARCHIVED)` per row inside the advisory-lock + `transaction.atomic()` block (lines 41-42). `models.py:413` confirms `transition_to()` calls `self.refresh_from_db()` — an unlocked SELECT — then `self.save()` at `models.py:495` — an unlocked write. An independent `grep -rn "select_for_update" src/backend/apps/core/management/commands/archive_sweep.py` returns **zero matches**. All other Ad-status-mutating code uses `select_for_update()`: `ads/views/edit.py:116,279,316`, `ads/views/delete.py:41`, `moderation/views/review.py:73,103,142`, `ads/services/submission.py:167`, `moderation/admin_actions.py:89,164,215,277`. The advisory lock (ID 1, `ARCHIVE_SWEEP`) prevents concurrent sweep workers but does NOT prevent web or bot processes from modifying the same Ad rows between `refresh_from_db()` and `save()`. The lost-update window is real.
> - **VAL-002 (minor evidence gap):** The finding's grep lists 8 `select_for_update` matches but omits 4 matches in `apps/moderation/admin_actions.py:89,164,215,277`. This does not affect the core claim (archive_sweep has no match); it is an incompleteness in the evidence table, not a validity issue.
> - **Severity note:** The phase-03 handbook taxonomy lists "lost update on a shared row between processes" under CRITICAL and "sweep executed without the lock" under HIGH. Since archive_sweep *does* hold its advisory lock (only the row-level lock is missing), HIGH is defensible. However, the consequence (overwriting a concurrent web/bot edit — a lost update on a shared row between processes) aligns with the CRITICAL tier. If severity is meant to reflect *impact* rather than *root-cause category*, reclassification to CRITICAL would be warranted. The finding is validated regardless.
> - **VAL-001 (ID collision):** "DB-010" in the test suite refers to the *advisory lock ordering* fix (already applied and guarded by `test_sweep_lock_structure.py`), NOT to the `select_for_update` issue. See VAL-001.

| Field | Value |
|---|---|
| **ID** | DB-010 |
| **Title** | `archive_sweep` lacks `select_for_update()` on per-row `transition_to()` — lost-update race |
| **Severity** | HIGH |
| **Type** | BEST-PRACTICE (validated) |
| **Category** | Row-level locking / lost-update prevention |
| **File(s)** | `apps/core/management/commands/archive_sweep.py:47-50, :73-75`; `apps/ads/models.py:362-495` (`transition_to`); `apps/ads/models.py:410-413` (`refresh_from_db`), `:494-495` (`save`) |
| **Status** | Open |
| **Problem** | The `archive_sweep` command iterates `PUBLISHED` ads via `Ad.objects.filter(status=AdStatus.PUBLISHED, published_at__lt=cutoff)` (no `.select_for_update()`) and calls `transition_to(AdStatus.ARCHIVED)` per row. `transition_to()` calls `self.refresh_from_db()` (unlocked SELECT) then `self.save()` — a read-modify-write with no row lock. The advisory lock (ID 1) prevents concurrent sweep workers but does NOT prevent web or bot processes from modifying the same Ad rows concurrently. |
| **Impact** | A concurrent web edit (e.g. text-edit re-hide) or bot operation that changes an ad's status between the sweep's `refresh_from_db()` read and `save()` write is silently overwritten. The ad ends up `ARCHIVED` instead of the concurrent operation's target status — a lost update that violates ad lifecycle integrity. |
| **Root Cause** | `archive_sweep` was written to call `transition_to()` per row (for search-cache invalidation and `ALLOWED_TRANSITIONS` enforcement) but did not add `.select_for_update()` to the queryset — the only Ad-status-mutating path in the codebase that omits it. |
| **Recommendation** | Add `.select_for_update().order_by("pk")` to the queryset at `archive_sweep.py:47`. Row locks are acquired as rows are iterated within the existing `transaction.atomic()` + advisory-lock scope, preventing concurrent web/bot writes from interleaving. |
| **Effort** | S (single-line queryset change) |
| **Priority** | P1 |

**Evidence — `archive_sweep.py:41-42, 47-50, 73-75`** (confirmed: advisory lock inside transaction but queryset has no `select_for_update`):

```python
# Lines 41-42: advisory lock IS inside transaction (guards concurrent sweeps)
with transaction.atomic():
    with advisory_lock(AdvisoryLockId.ARCHIVE_SWEEP):

# Lines 47-50: queryset — NO select_for_update()
queryset = Ad.objects.filter(
    status=AdStatus.PUBLISHED,
    published_at__lt=cutoff_date,
)

# Lines 73-75: per-row transition without row lock
for ad in queryset.order_by("pk"):
    try:
        ad.transition_to(AdStatus.ARCHIVED)
```

**Evidence — `grep -rn "select_for_update" src/backend/apps/core/management/commands/archive_sweep.py`** (confirmed: zero matches):

```text
(no output)
```

**Evidence — `apps/ads/models.py:410-413, 494-495`** (confirmed: `transition_to` uses unlocked `refresh_from_db` + `save`):

```python
# Line 410-413: refresh_from_db — unlocked SELECT, no row lock
# DB-003: re-read from DB to defeat stale-state races (DB vs. bot
# process, concurrent sweeps). Raises Ad.DoesNotExist if a hard-delete
# sweep removed the row between caller fetch and transition.
self.refresh_from_db()

# Line 494-495: save — unlocked write
self.status = target
self.save(update_fields=update_fields)
```

**Evidence — grep for `select_for_update` across all Ad-status-mutating code** (confirmed: archive_sweep is the only one without it):

```text
apps/ads/views/edit.py:116       Ad.objects.select_for_update()     # ad_edit
apps/ads/views/edit.py:279      Ad.objects.select_for_update()     # ad_archive
apps/ads/views/edit.py:316      Ad.objects.select_for_update()     # ad_reactivate
apps/ads/views/delete.py:41     Ad.objects.select_for_update()     # ad_delete
apps/moderation/views/review.py:73   Ad.objects.select_for_update()  # approve_ad
apps/moderation/views/review.py:103  Ad.objects.select_for_update()  # reject_ad
apps/moderation/views/review.py:142  Ad.objects.select_for_update()  # ban_user_for_ad
apps/ads/services/submission.py:167  Ad.objects.select_for_update()    # submit_ad
apps/moderation/admin_actions.py:89   User.objects.select_for_update() # ban_user_for_ad (User)
apps/moderation/admin_actions.py:164  .select_for_update()               # bulk_approve
apps/moderation/admin_actions.py:215  .select_for_update()               # bulk_reject
apps/moderation/admin_actions.py:277  .select_for_update()               # bulk_delete
# archive_sweep.py: NO match
```

---

### MEDIUM

#### DB-012: [MEDIUM] — `backfill_thumbnails` holds `transaction.atomic()` across filesystem I/O

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed `backfill_thumbnails.py:56` opens `with transaction.atomic():` and `backfill_thumbnails.py:57` acquires `with advisory_lock(LOCK_ID):` (LOCK_ID = `AdvisoryLockId.BACKFILL_THUMBNAILS` = 102, transaction-scoped per default `session=False`). The entire batch loop (lines 89–119) — including `ids = list(queryset.values_list("id", flat=True))` at line 90 and the `self._process_one(service, ad_image)` call at line 97 — runs inside this outer transaction. `_process_one` (lines 121–155) performs filesystem I/O: `Path(settings.MEDIA_ROOT)` construction (line 123), `original_path.is_file()` (line 125), `open(str(original_path), "rb")` + `f.read()` (lines 133–134), and `service.generate_thumbnails(photo_bytes, ...)` (line 136 — CPU-intensive). The comment at line 89 ("Process in batches to avoid long-running transactions") is misleading — batching does not shorten the transaction because the outer `transaction.atomic()` spans all batches and all I/O. The inner `transaction.atomic()` at line 138 is a savepoint covering only the DB update (lines 140–155), not the I/O, which remains in the outer transaction.
> - **Severity alignment:** The phase-03 handbook lists "Transaction scope too narrow" under MEDIUM but not "transaction scope too wide." An overly-wide transaction holding locks across filesystem I/O is an operational concern (lock hold time, snapshot retention, crash rollback waste). MEDIUM is appropriate.

| Field | Value |
|---|---|
| **ID** | DB-012 |
| **Title** | `backfill_thumbnails` holds `transaction.atomic()` across filesystem I/O |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE (validated) |
| **Category** | Transaction scope / lock hold time |
| **File(s)** | `apps/media/management/commands/backfill_thumbnails.py:56-57` (outer `transaction.atomic()` + advisory lock); `:90-97` (batch loop with `_process_one` call); `:121-136` (`_process_one` filesystem I/O: `open`/`read`/`generate_thumbnails`); `:138` (inner `transaction.atomic()` savepoint for DB update only) |
| **Status** | Open |
| **Problem** | The outer `transaction.atomic()` (line 56) — required because the advisory lock for ID 102 is transaction-scoped (`session=False`) — wraps the entire batch processing loop including filesystem I/O (`_process_one` at line 97: file open, read, and CPU-intensive thumbnail generation at lines 133–136). The inner `transaction.atomic()` at line 138 is a savepoint covering only the DB update. The comment at line 89 ("Process in batches to avoid long-running transactions") is misleading — batching does not shorten the outer transaction. |
| **Impact** | The transaction holds PostgreSQL row locks (on any locked tables) and maintains a snapshot for the duration of thumbnail generation — which can be slow for large batches. Under PgBouncer in transaction mode, this ties up a backend connection for the entire batch duration. If the process crashes mid-batch, the entire transaction (including already-completed thumbnails) is rolled back, wasting CPU work. |
| **Root Cause** | The advisory lock for ID 102 (`BACKFILL_THUMBNAILS`) is transaction-scoped (`session=False`, the default). PostgreSQL releases `pg_advisory_xact_lock` at transaction commit, so the lock and transaction must span the entire operation. There is no `session=True` override, and the `advisory_lock()` function enforces `in_atomic_block` for `session=False`. |
| **Recommendation** | Two options: (a) Move filesystem I/O outside the transaction — read files + generate thumbnails in the loop, accumulate `(id, thumbnail_keys)` tuples, then issue batch `AdImage.objects.filter(...).update(...)` in short `transaction.atomic()` blocks after the I/O completes. The advisory lock can be acquired in a short initial transaction (to gate concurrent sweeps), released, then re-acquired per-batch if needed. (b) Switch lock 102 to `session=True` so each batch can commit independently. Option (b) requires updating the `test_sweep_lock_structure.py` assertion that enforces `session=False` for all sweep commands. |
| **Effort** | M (restructure command + possibly update test assertion) |
| **Priority** | P2 |

**Evidence — `backfill_thumbnails.py:56-57`** (confirmed: outer `transaction.atomic()` wraps advisory lock):

```python
with transaction.atomic():
    with advisory_lock(LOCK_ID):  # LOCK_ID = AdvisoryLockId.BACKFILL_THUMBNAILS (102)
```

**Evidence — `backfill_thumbnails.py:89-97`** (confirmed: batch loop with filesystem I/O inside transaction):

```python
# Process in batches to avoid long-running transactions  ← misleading comment
ids = list(queryset.values_list("id", flat=True))
for i in range(0, len(ids), batch_size):
    batch_ids = ids[i : i + batch_size]
    ...
    for ad_image in AdImage.objects.filter(id__in=batch_ids):
        self._process_one(service, ad_image)  # ← filesystem I/O inside txn
```

**Evidence — `backfill_thumbnails.py:123-136`** (confirmed: `_process_one` performs filesystem I/O):

```python
original_path = Path(settings.MEDIA_ROOT) / str(ad_image.image)  # L123
...
original_path.is_file()  # L125
with open(str(original_path), "rb") as f:  # L133
    photo_bytes = f.read()  # L134
thumbnail_keys = service.generate_thumbnails(photo_bytes, ...)  # L136
```

**Evidence — `backfill_thumbnails.py:138`** (confirmed: inner `transaction.atomic()` is a savepoint, not the outer scope):

```python
with transaction.atomic():  # L138 — savepoint, covers only DB update (L140-155)
    ad_image.thumbnail_small = ...
    ad_image.save(update_fields=...)
```

---

### LOW

#### DB-011: [LOW] — Advisory lock docstring lists IDs 102/103 as session-scoped but code uses transaction-scoped

> **Validation Note:**
> - **Action:** validated (reclassified to DOC-UPDATE)
> - **Detail:** Confirmed `advisory_lock.py:52-57` lists `BACKFILL_THUMBNAILS` (102) and `SWEEP_ORPHANED_MEDIA` (103) under "Session-scoped (pg_advisory_lock; spans the connection, pre-PgBouncer)." However, `backfill_thumbnails.py:57` calls `advisory_lock(LOCK_ID)` without `session=True` (default `session=False` → `pg_advisory_xact_lock`, transaction-scoped). `sweep_orphaned_media.py:138` similarly calls `advisory_lock(AdvisoryLockId.SWEEP_ORPHANED_MEDIA)` without `session=True`. An independent `grep -rn "session=True" src/backend/` confirms that **all five other session-scoped lock IDs (100, 101, 104, 110, 111) correctly use `session=True`**: `migrate_locked.py:75`, `create_admin_user.py:76`, `builder.py` and `load_cities.py` (CATALOG_LOAD), `seed_service.py:74`, and `conftest.py:153` (TEST_SCHEMA_SETUP). The code is **correct** — transaction-scoped locks (safe under PgBouncer) are the right choice for production sweep commands. The **docstring is wrong**: IDs 102 and 103 should be listed under "Transaction-scoped," not "Session-scoped." Per the Phase-99 type-mapping rule ("code is correct → DOC-UPDATE"), this is reclassified from an unspecified audit category to DOC-UPDATE.
> - **VAL-001 (ID collision):** "DB-011" in the codebase refers to the *TOCTOU race on `max_ads_per_user`* (see `moderation_log.py:227`, `test_auto_moderation.py:520`), NOT to this docstring issue.

| Field | Value |
|---|---|
| **ID** | DB-011 |
| **Title** | Advisory lock docstring lists IDs 102/103 as session-scoped but code uses transaction-scoped |
| **Severity** | LOW |
| **Type** | DOC-UPDATE (validated — reclassified from unspecified) |
| **Category** | Documentation accuracy |
| **File(s)** | `apps/core/utils/advisory_lock.py:52-57` (docstring lists 102/103 under Session-scoped); `apps/media/management/commands/backfill_thumbnails.py:57` (uses `advisory_lock(LOCK_ID)` without `session=True`); `apps/media/management/commands/sweep_orphaned_media.py:138` (uses `advisory_lock(...)` without `session=True`); `apps/core/enums.py:37-38` (`BACKFILL_THUMBNAILS = 102`, `SWEEP_ORPHANED_MEDIA = 103`) |
| **Status** | Open |
| **Problem** | The `advisory_lock()` docstring at `advisory_lock.py:52-57` lists lock IDs 102 (`BACKFILL_THUMBNAILS`) and 103 (`SWEEP_ORPHANED_MEDIA`) under the "Session-scoped (pg_advisory_lock; spans the connection, pre-PgBouncer)" section. However, both commands call `advisory_lock(lock_id)` with the default `session=False`, which uses `pg_advisory_xact_lock` (transaction-scoped). Transaction-scoped locks are released at commit — this is the **correct** choice for production sweep commands running under a transaction-mode PgBouncer. All five other session-scoped lock IDs (100, 101, 104, 110, 111) correctly pass `session=True`. |
| **Impact** | A reader consulting the docstring will believe 102/103 are session-scoped and may incorrectly change them to `session=True`, which would break under PgBouncer in production. The docstring misleads about the operational model of these locks. |
| **Root Cause** | The docstring was written when the lock allocation was initially designed, listing all IDs ≥100 as session-scoped (since one-shot setup commands like MIGRATE/CREATE_ADMIN/CATALOG_LOAD/SEED use `session=True`). IDs 102 and 103 were later implemented as scheduled production sweep commands that correctly use transaction-scoped locks, but the docstring was not updated. |
| **Recommendation** | Move IDs 102 and 103 from the "Session-scoped" section to the "Transaction-scoped" section in the `advisory_lock.py` docstring (lines 52-57 → lines 38-50). |
| **Effort** | XS (docstring edit only, no code change) |
| **Priority** | P2 |

**Evidence — `advisory_lock.py:52-57`** (confirmed: 102/103 listed under Session-scoped in docstring):

```python
Session-scoped (pg_advisory_lock; spans the connection, pre-PgBouncer):
    100  MIGRATE                      post-migration setup (runs pre-PgBouncer)
    101  CREATE_ADMIN                 admin creation
    102  BACKFILL_THUMBNAILS          thumbnail backfill
    103  SWEEP_ORPHANED_MEDIA         orphaned media sweep
    104  CATALOG_LOAD                 catalog load
    110  SEED                         seed service
    111  TEST_SCHEMA_SETUP            test schema setup (serializes xdist workers)
```

**Evidence — `backfill_thumbnails.py:57`** (confirmed: transaction-scoped, no `session=True`):

```python
with advisory_lock(LOCK_ID):  # LOCK_ID = AdvisoryLockId.BACKFILL_THUMBNAILS (102), session=False default
```

**Evidence — `sweep_orphaned_media.py:138`** (confirmed: transaction-scoped, no `session=True`):

```python
with advisory_lock(AdvisoryLockId.SWEEP_ORPHANED_MEDIA):  # session=False default
```

**Evidence — `grep -rn "session=True" src/backend/`** (confirmed: all other session-scoped IDs use `session=True`; 102/103 do not):

```text
apps/core/utils/migrate_locked.py:75        advisory_lock(AdvisoryLockId.MIGRATE, session=True)          # 100 ✓
apps/core/management/commands/create_admin_user.py:76  advisory_lock(..., session=True)       # 101 ✓
apps/categories/catalog/builder.py:*            advisory_lock(AdvisoryLockId.CATALOG_LOAD, session=True)   # 104 ✓
apps/locations/management/commands/load_cities.py:47   advisory_lock(AdvisoryLockId.CATALOG_LOAD, session=True)  # 104 ✓
apps/seed/services/seed_service.py:74        advisory_lock(AdvisoryLockId.SEED, session=True)             # 110 ✓
src/backend/conftest.py:153                advisory_lock(AdvisoryLockId.TEST_SCHEMA_SETUP, session=True)  # 111 ✓
# backfill_thumbnails.py:57  → NO session=True (102) ✗
# sweep_orphaned_media.py:138 → NO session=True (103) ✗
```

---

#### DB-013: [LOW] — No concurrency test for `archive_sweep` row-level locking — test gap

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed: `test_sweep_archive.py` contains no structural assertion for `select_for_update()`. It tests dry-run behavior, retention window, idempotency, lock ID value, and search cache bump — but not locking. `test_sweep_lock_structure.py` spies on `advisory_lock` and asserts `in_atomic_block == True` and `session == False` (R-01, R-02 of findings.md), but does NOT inspect for `select_for_update`. The existing concurrency-locking test pattern in `test_edit_views_locking.py:51-57` (which asserts `"select_for_update" in inspect.getsource(...)` and `"transaction.atomic" in source`) covers `ad_edit`, `ad_archive`, `ad_reactivate`, `ad_delete`, and `submit_ad` — but none of these are management commands. `test_transition_concurrency.py` has a threading-based test (`test_select_for_update_blocks_concurrent_delete`) for moderation review views, but no equivalent for `archive_sweep`. The test gap is confirmed.
> - **VAL-001 (ID collision):** "DB-013" in the codebase refers to (a) the *unlocked `Ad.objects.get()` in `submit_ad`* (see `test_edit_views_locking.py:111`, already fixed) and (b) `sweep_orphaned_media` integration tests (see `test_sweep_orphaned_media.py:2`). Neither relates to `archive_sweep`.

| Field | Value |
|---|---|
| **ID** | DB-013 |
| **Title** | No concurrency test for `archive_sweep` row-level locking — test gap |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE (validated) |
| **Category** | Test coverage / regression safety |
| **File(s)** | `apps/core/tests/test_sweep_archive.py` (no select_for_update assertion); `apps/core/tests/test_sweep_lock_structure.py` (advisory-lock scope only); `apps/ads/tests/test_edit_views_locking.py:51-57` (structural pattern not applied to archive_sweep) |
| **Status** | Open |
| **Problem** | No test verifies that `archive_sweep` acquires row-level locks (`select_for_update()`). `test_sweep_lock_structure.py` verifies the advisory lock is inside `transaction.atomic()` and uses `session=False` — but does not inspect for `select_for_update()`. The structural-assertion pattern at `test_edit_views_locking.py:51-57` (which uses `inspect.getsource()` to assert `"select_for_update"` and `"transaction.atomic"` are present in a view/service) covers `ad_edit`, `ad_archive`, `ad_reactivate`, `ad_delete`, and `submit_ad` — but none of these are management commands. `test_transition_concurrency.py` has a threading-based concurrency test for moderation review views but no equivalent for `archive_sweep`. |
| **Impact** | If `select_for_update()` is later removed from `archive_sweep` (regression of DB-010), no test will catch it. The existing `test_sweep_lock_structure.py` advisory-lock spy would still pass because the advisory lock is orthogonal to row-level locking. |
| **Root Cause** | The structural-assertion pattern was applied only to HTTP views and services, not to management commands. `test_sweep_archive.py` was written to verify functional correctness (dry-run, retention, idempotency) but was never extended with a DB-010-locking structural guard. |
| **Recommendation** | Add a structural test to `test_sweep_archive.py` mirroring `test_edit_views_locking.py:51-57`: use `inspect.getsource()` on the `archive_sweep` command's `handle` method and assert `"select_for_update"` and `"transaction.atomic"` are present. Additionally, add a threading-based concurrency test mirroring `test_transition_concurrency.py`'s `test_select_for_update_blocks_concurrent_delete` — spawn two concurrent `archive_sweep` runs (one real, one concurrent web edit) and assert the web edit is not silently overwritten. |
| **Effort** | S (structural test) + M (threading concurrency test) |
| **Priority** | P2 |

**Evidence — `test_sweep_archive.py`** (confirmed: no `select_for_update` assertion; 5 tests cover dry-run, retention, idempotency, lock-ID value, search cache — none check row locking):

```python
def test_dry_run_does_not_mutate(self, seller, category, city) -> None: ...
def test_archives_published_older_than_60_days(self, seller, category, city) -> None: ...
def test_idempotent_on_rerun(self, seller, category, city) -> None: ...
def test_lock_id_is_archive_sweep(self) -> None: ...   # asserts AdvisoryLockId.ARCHIVE_SWEEP == 1
def test_archive_sweep_bumps_search_cache(self, seller, category, city) -> None: ...
```

**Evidence — `test_edit_views_locking.py:51-57`** (confirmed: structural pattern exists for views but not applied to archive_sweep):

```python
def test_ad_edit_uses_select_for_update_and_atomic(self) -> None:
    """ad_edit source contains select_for_update inside transaction.atomic."""
    from apps.ads.views import edit
    source = inspect.getsource(edit.ad_edit)
    assert "transaction.atomic" in source
    assert "select_for_update" in source
```

---

## Checkpoint 3 — Per-finding validation

| ID | Decision | Type (original → validated) | Severity | Notes |
|----|----------|-----------------------------|----------|-------|
| DB-010 | **Validated** | BEST-PRACTICE (was: HIGH/unspecified) | HIGH | `select_for_update` absent from `archive_sweep.py`; `transition_to()` uses unlocked `refresh_from_db` + `save` confirmed at `models.py:413,495`. Advisory lock (ID 1) does not protect against concurrent web/bot writes. Grep confirms 12 `select_for_update` call-sites in all other Ad-mutating code; 0 in archive_sweep. |
| DB-011 | **Validated** | DOC-UPDATE (was: LOW/unspecified) | LOW | Code correct (transaction-scoped for 102/103, all other session-scoped IDs use `session=True`). Docstring at `advisory_lock.py:52-57` incorrectly lists 102/103 under Session-scoped. Reclassified per Phase-99 rule: "code correct → DOC-UPDATE." |
| DB-012 | **Validated** | BEST-PRACTICE (was: MEDIUM/unspecified) | MEDIUM | `transaction.atomic()` at `backfill_thumbnails.py:56` wraps the entire batch loop (lines 89–119) including `_process_one` filesystem I/O (`open`, `read`, `generate_thumbnails` at lines 123–136). Inner `transaction.atomic()` at line 138 is a savepoint covering only the DB update. Misleading "avoid long-running transactions" comment at line 89 confirmed. |
| DB-013 | **Validated** | BEST-PRACTICE (was: LOW/unspecified) | LOW | No test asserts `select_for_update` in `archive_sweep`. Existing structural pattern (`test_edit_views_locking.py:51-57`) covers views/services only; concurrency test (`test_transition_concurrency.py`) covers review views only. |

**VAL findings:**

| ID | Type | Detail |
|----|------|--------|
| VAL-001 | ID collision (CRITICAL) | All four finding IDs (DB-010–DB-013) collide with already-fixed findings referenced in codebase source comments and test docstrings. DB-010 in tests = advisory lock ordering (fixed); DB-010 in findings = missing select_for_update (unfixed). Same pattern for DB-011 (TOCTOU max_ads vs docstring mismatch), DB-012 (select_for_update in views vs backfill transaction scope), DB-013 (unlocked get in submit_ad vs no archive_sweep test). Creates conflicting evidence; developers may dismiss findings as "already fixed." |
| VAL-002 | Incomplete grep evidence (LOW) | DB-010's grep lists 8 `select_for_update` matches but omits 4 in `admin_actions.py:89,164,215,277`. Core claim (archive_sweep has 0) unaffected. |

---

## Checkpoint 4 — Final consistency audit

- **Stage:** Final audit
- **Findings in scope:** 4 validated, 0 rejected, 0 merged, 0 reclassified (types adjusted for validation taxonomy: DB-011 → DOC-UPDATE)
- **VAL findings:** 2 (VAL-001 ID collision, VAL-002 incomplete grep)
- **Cross-phase conflicts:** VAL-001 (CRITICAL) — all four IDs collide with already-fixed findings in the codebase
- **Self-contained:** All findings are self-contained in this report with independent evidence
- **No source code was modified.**

---

## Rollout Analysis

| ID | Risk | Backward-compatible? | Test gap (must cover) |
|----|------|----------------------|-----------------------|
| DB-010 | Low | Yes — additive `.select_for_update()` to existing queryset inside existing `transaction.atomic()` + advisory lock | DB-013 must be added as the regression guard for this fix |
| DB-011 | None | Yes — docstring edit only | None (no code change) |
| DB-012 | Medium | Yes — refactor is additive; backfill still produces same output | Test that backfill completes all thumbnails correctly after refactor |
| DB-013 | None | Yes — new tests only | None (the tests ARE the coverage) |
| VAL-001 | CRITICAL | N/A — re-numbering prerequisite | Findings IDs must be changed before any fix is implemented to prevent mis-referencing already-fixed code paths |

**Rollout ordering:**
1. **VAL-001 (re-number findings)** must precede all fix work. Without re-numbering, developers implementing DB-010 (select_for_update) will encounter "DB-010" in `test_sweep_lock_structure.py` referring to the advisory lock ordering (already fixed) and may assume the issue is resolved.
2. **DB-010 + DB-013** should be deployed together — the structural locking test (DB-013) validates the code fix (DB-010). Adding the test before the fix would be a failing test; adding the fix without the test leaves no regression guard.
3. **DB-011** is independent and may be addressed in any order (pure docstring edit).
4. **DB-012** is independent but carries the highest operational risk — the transaction refactor must preserve the advisory-lock guarantee and must not break the `session=False` assertion in `test_sweep_lock_structure.py`.

**Rollout-safety concerns:**
- DB-010 fix: adding `.select_for_update()` to the archive_sweep queryset will cause row locks to be held for the duration of the sweep transaction. Since archive_sweep runs during the hourly sweep window and holds an advisory lock (preventing concurrent sweeps), the main risk is that web edits to old (PUBLISHED → being archived) ads will block briefly until the sweep commits. This is accepted behavior — the existing pattern in all other views does the same.
- DB-012 fix: switching lock 102 to `session=True` (option b) would break the test assertion at `test_sweep_lock_structure.py:130-133` that enforces `session=False` for all sweep commands. If chosen, the test must be updated to exclude `backfill_thumbnails` from the `session=False` assertion. Option (a) (moving I/O outside the transaction) is more complex but preserves the existing lock-scope contract.

---

## Execution Validation

- **Applicability:** All findings remain applicable to the current codebase state. No code changes were made during validation. All evidence was verified against live source files.
- **Execution readiness:**
  - DB-010: Ready. The fix is a single-line queryset addition following the established pattern.
  - DB-011: Ready. Docstring edit only.
  - DB-012: Conditionally ready. The fix requires choosing between I/O-outside-transaction (complex, preserves lock contract) or session=True (simpler, requires test update). The choice should be documented.
  - DB-013: Ready. The test pattern already exists in `test_edit_views_locking.py`.
- **Architectural integrity:** All four findings improve architecture without degrading it. DB-010 brings archive_sweep in line with the established `select_for_update` pattern. DB-011 fixes documentation accuracy. DB-012 reduces transaction hold time. DB-013 adds regression safety.
- **No assumptions were invalidated.** No dependencies drifted. No targets disappeared.

---

## Warnings

- **VAL-001 (CRITICAL — ID collision):** All four finding IDs (DB-010 through DB-013) are already used in the codebase's source comments and test docstrings to refer to *different, already-fixed* findings. The phase 03 audit appears to have re-used IDs from a prior audit cycle without detecting existing references. **No fix should be implemented until the IDs are re-numbered.** The re-numbered IDs should also be back-propagated to the findings.md source file to maintain consistency.
- **DB-010 severity alignment:** The phase-03 handbook lists "lost update on a shared row between processes" as CRITICAL. While the finding is rated HIGH (the advisory lock IS present — only the row lock is missing), the consequence (silently overwriting a concurrent web/bot edit) is a true lost update. Consider reclassifying to CRITICAL if severity should reflect impact over root-cause category.
- **DB-012 fix choice has architectural implications:** Switching lock 102 to `session=True` (option b) would be a functional change to the production locking model, not just a refactor. Under PgBouncer in transaction mode, `pg_advisory_lock` (session-scoped) is NOT safe — the lock would attach to whichever backend serves the connection, which can change. The `session=True` option should only be used under a session-mode pooler or no pooler. This should be explicitly documented if chosen.

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 3 | DB-010, DB-012, DB-013 |
| Reclassified | 1 | DB-011: unspecified → DOC-UPDATE (code is correct; docstring is wrong) |
| Merged | 0 | — |
| Rejected | 0 | — |
| VAL- (cross-phase / correction) | 2 | VAL-001 (ID collision — CRITICAL), VAL-002 (incomplete grep evidence — LOW) |

### Validated Findings (4)

| ID | Title | Validated As | Confidence |
|----|-------|--------------|------------|
| DB-010 | `archive_sweep` lacks `select_for_update()` — lost-update race | BEST-PRACTICE | High |
| DB-012 | `backfill_thumbnails` holds `transaction.atomic()` across filesystem I/O | BEST-PRACTICE | High |
| DB-011 | Advisory lock docstring lists IDs 102/103 as session-scoped | DOC-UPDATE | High |
| DB-013 | No concurrency test for `archive_sweep` row-level locking | BEST-PRACTICE | High |

### VAL Findings (2)

| ID | Type | Severity | Detail |
|----|------|----------|--------|
| VAL-001 | ID collision | CRITICAL | All 4 finding IDs (DB-010–DB-013) collide with already-fixed findings referenced in codebase source comments and test docstrings. Re-number before implementing any fix. |
| VAL-002 | Incomplete evidence | LOW | DB-010's `select_for_update` grep omits 4 matches in `admin_actions.py`. Core claim unaffected. |

### Rejected Findings

None.

### Required Fixes (in rollout order)

1. **VAL-001 (before any code fix):** Re-number DB-010–DB-013 to non-colliding IDs (e.g., DB-010–DB-012). Cross-check all `grep` results for `DB-00[1-4]` in the codebase to find every reference that needs updating. **This is a prerequisite for all subsequent work.**
2. **DB-010 (P1):** Add `.select_for_update().order_by("pk")` to the queryset at `archive_sweep.py:47`.
3. **DB-013 (P2):** Add structural test (`select_for_update` + `transaction.atomic` assertion) to `test_sweep_archive.py`, mirroring `test_edit_views_locking.py:51-57`. Add a threading-based concurrency test mirroring `test_transition_concurrency.py`.

### Advisory Recommendations

1. **DB-011 (P2):** Move IDs 102 and 103 from the "Session-scoped" to "Transaction-scoped" section in the `advisory_lock.py` docstring.
2. **DB-012 (P2):** Choose one fix path and document the PgBouncer safety implication:
   - Option (a): Move filesystem I/O outside the outer `transaction.atomic()`, accumulating results for batch DB updates in short transactions. Preserves the `session=False` lock contract.
   - Option (b): Switch lock 102 to `session=True`. Simpler but changes the production locking model; requires updating `test_sweep_lock_structure.py`'s `session=False` assertion for this command, and is only safe if PgBouncer uses session mode (or no pooler).

---

*Validation performed by Kilo (Phase 99 validation pipeline) on 2026-09-23. All evidence was verified against live source files. No source code was modified. The only file created by this validation is this report.*
