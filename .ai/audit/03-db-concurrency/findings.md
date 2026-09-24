---
phase: "03"
phase_name: "Database & Concurrency Consistency"
date: "2026-09-23"
auditor: "Executor (subagent)"
mode: "problems-only"
id_prefix: "DB"
report_status: "draft"
severity_taxonomy: ".kilo/commands/audit/phases/03-audit-db-concurrency.md#severity-taxonomy"
---

# Audit Findings — Database & Concurrency Consistency

## Executive Summary

The audit identified 4 findings across the dual-process Django + aiogram codebase. The highest severity is HIGH: the archive_sweep management command performs per-row read-modify-write via transition_to() without select_for_update(), creating a lost-update window that no other Ad-status-mutating view shares. All other views (edit, archive, reactivate, delete, moderation, submission) correctly use select_for_update() inside transaction.atomic(). The advisory-lock infrastructure is sound: all sweep commands acquire their transaction-scoped advisory lock inside transaction.atomic(), and the bot DatabaseConnectionMiddleware closes connections after each update. Two lower-priority findings concern a docstring/lock-scope mismatch and missing test coverage.

## Scope & Methodology

**Scope:** src/backend/apps/core/management/commands/ (sweep/purge commands), src/backend/apps/ads/models.py (transition_to), src/backend/apps/ads/views/edit.py, src/backend/apps/ads/views/delete.py, src/backend/apps/moderation/views/review.py, src/backend/apps/ads/services/submission.py, src/backend/apps/moderation/admin_actions.py, src/telegram_bot/ (middleware, services, handlers), src/backend/apps/core/utils/advisory_lock.py, src/backend/apps/core/enums.py, src/backend/config/settings/base.py, and related test files.

### Runtime Verification

| R# | Check | Method | Result |
|----|-------|--------|--------|
| R-01 | All sweep commands acquire advisory lock inside transaction.atomic() | test_sweep_lock_structure.py — spy on advisory_lock, asserts in_atomic_block == True | PASS |
| R-02 | All sweep commands use session=False (transaction-scoped) | test_sweep_lock_structure.py — asserts session == False | PASS |
| R-03 | Dry-run paths acquire the lock | test_sweep_lock_structure.py, test_sweep_archive.py::test_dry_run_does_not_mutate | PASS |
| R-04 | Bot ORM access dispatched via sync_to_async | grep for sync_to_async in bots/services/ad_data.py, login.py, alerts.py | PASS |
| R-05 | DatabaseConnectionMiddleware closes connections via sync_to_async | test_db_connection_middleware.py::test_close_dispatched_via_sync_to_async | PASS |
| R-06 | Bot lifecycle shutdown closes connections via sync_to_async | test_lifecycle.py::test_on_shutdown_closes_connections_via_sync_to_async | PASS |
| R-07 | All Ad-status-mutating views use select_for_update() | grep for select_for_update across views/services — PASS except archive_sweep | PASS (except archive_sweep) |
| R-08 | Login token claim is atomic via UPDATE ... RETURNING | login.py:151-169 — single-statement claim with WHERE guard | PASS |
| R-09 | prepare_threshold: None set in DB options | base.py:205 and base.py:218 | PASS |
| R-10 | CONN_MAX_AGE effective value is 0 | base.py:216 (explicit; env.db() defaults to 0 in DATABASE_URL branch) | PASS |
| R-11 | Sweep commands using bulk delete() do not need select_for_update | delete_sweep.py:72, sweep_drafts.py:70, purge_*.py, consent_hard_delete.py:87 | PASS |
| R-12 | create_draft_ad handles DRAFT race via IntegrityError retry | ad_data.py:96-102 — IntegrityError backstop | PASS |

**Tools used:** grep, file inspection, existing test suite analysis.

**Assumptions:** PostgreSQL 18; Django 5.2 LTS; aiogram 3.x; production uses Redis-backed cache; web runs gunicorn sync WSGI; bot runs standalone async process with django.setup(); CONN_MAX_AGE=0 in production.

## Findings Summary

| ID | Title | Severity | Status | Category |
|----|-------|----------|--------|----------|
| DB-010 | archive_sweep lacks select_for_update() on per-row transition_to() — lost-update race | HIGH | Open | Lost-update prevention |
| DB-011 | Advisory lock docstring lists IDs 102/103 as session-scoped but code uses transaction-scoped | LOW | Open | Doc-code mismatch |
| DB-012 | backfill_thumbnails holds transaction.atomic() across filesystem I/O | MEDIUM | Open | Transaction scope |
| DB-013 | No concurrency test for archive_sweep row-level locking — test gap | LOW | Open | Test quality |

## Findings by Severity

### HIGH

#### DB-010: HIGH — archive_sweep lacks select_for_update() on per-row transition_to() — lost-update race

| Field | Value |
|---|---|
| **ID** | DB-010 |
| **Title** | archive_sweep lacks select_for_update() on per-row transition_to() — lost-update race |
| **Severity** | HIGH |
| **Category** | Lost-update prevention |
| **File(s)** | apps/core/management/commands/archive_sweep.py:47-50, :73-75; apps/ads/models.py:362-495 (transition_to) |
| **Status** | Open |
| **Problem** | The archive_sweep command iterates PUBLISHED ads via Ad.objects.filter(status=PUBLISHED, published_at__lt=cutoff) (no .select_for_update()) and calls transition_to(ARCHIVED) per row. Inside transition_to(), the method calls self.refresh_from_db() (unlocked SELECT) at models.py:413, then validates the transition, then calls self.save(update_fields=...) at models.py:495. Between the refresh_from_db() read and the save() write, a concurrent web/bot operation can modify the same Ad row, and the save() will silently overwrite that change — a classic lost-update (read-modify-write without locking) race. |
| **Impact** | A concurrent web edit or bot operation that changes an ad status (e.g., PUBLISHED-to-ON_MODERATION for text edit, or PUBLISHED-to-DELETED for self-delete) can be silently overwritten by archive_sweep save(), resulting in the ad being ARCHIVED instead of the concurrent operation target. This violates ad lifecycle integrity. |
| **Root Cause** | archive_sweep was written to call transition_to() per-row (for search-cache invalidation and ALLOWED_TRANSITIONS enforcement) but did not add .select_for_update() to the queryset. All other views that call transition_to() on Ad rows wrap their fetch in select_for_update(), making archive_sweep the sole exception. |
| **Recommendation** | Add .select_for_update().order_by("pk") to the queryset in archive_sweep.py:47-50. Add a structural assertion to test_sweep_archive.py mirroring test_edit_views_locking.py:51-57. |
| **Effort** | S |
| **Priority** | P1 |

**Evidence — archive_sweep.py:47-50** *(supports: "queryset without select_for_update")*:
```python
queryset = Ad.objects.filter(
    status=AdStatus.PUBLISHED,
    published_at__lt=cutoff_date,
)
```

**Evidence — archive_sweep.py:73-75** *(supports: "per-row transition_to call without row lock")*:
```python
for ad in queryset.order_by("pk"):
    try:
        ad.transition_to(AdStatus.ARCHIVED)
```

**Evidence — ads/models.py:410-413** *(supports: "refresh_from_db is unlocked; comment acknowledges stale-state race but relies on refresh alone, not locking")*:
```python
# DB-003: re-read from DB to defeat stale-state races (DB vs. bot
# process, concurrent sweeps). Raises Ad.DoesNotExist if a hard-delete
# sweep removed the row between caller fetch and transition.
self.refresh_from_db()
```

**Evidence — ads/models.py:494-495** *(supports: "save overwrites concurrent changes without re-checking lock or version")*:
```python
self.status = target
self.save(update_fields=update_fields)
```

**Evidence — grep for select_for_update** *(supports: "every other Ad-status-mutating view uses select_for_update; archive_sweep.py has NO match")*:
```
ads/views/edit.py:116      Ad.objects.select_for_update()  # ad_edit POST
ads/views/edit.py:279      Ad.objects.select_for_update()  # ad_archive
ads/views/edit.py:316      Ad.objects.select_for_update()  # ad_reactivate
ads/views/delete.py:41     Ad.objects.select_for_update()  # ad_delete
moderation/views/review.py:73  Ad.objects.select_for_update()  # approve_ad
moderation/views/review.py:103 Ad.objects.select_for_update()  # reject_ad
moderation/views/review.py:142 Ad.objects.select_for_update()  # ban_user_for_ad
ads/services/submission.py:167 Ad.objects.select_for_update()  # submit_ad
# archive_sweep.py: NO match
```

### MEDIUM

#### DB-012: MEDIUM — backfill_thumbnails holds transaction.atomic() across filesystem I/O

| Field | Value |
|---|---|
| **ID** | DB-012 |
| **Title** | backfill_thumbnails holds transaction.atomic() across filesystem I/O |
| **Severity** | MEDIUM |
| **Category** | Transaction scope |
| **File(s)** | apps/media/management/commands/backfill_thumbnails.py:56-119 |
| **Status** | Open |
| **Problem** | The backfill_thumbnails command wraps the entire batch processing loop — including filesystem I/O (reading image files, generating thumbnails) — inside a single outer transaction.atomic() that also holds the transaction-scoped advisory lock (lock 102). The comment at line 89 says "Process in batches to avoid long-running transactions" but the outer transaction.atomic() spans all batches. |
| **Impact** | Extended transaction/lock hold increases PostgreSQL snapshot retention, blocks any operation using select_for_update on the same AdImage rows, and risks transaction-killed-by-timeout during long thumbnail generation. A crash mid-batch rolls back all completed thumbnails. |
| **Root Cause** | Transaction-scoped advisory lock (session=False) requires the lock to be inside transaction.atomic(), so the transaction must span the entire operation including filesystem I/O. |
| **Recommendation** | Move filesystem I/O outside the transaction: read files + generate thumbnails in the loop, accumulate update kwargs, then batch-update DB in short transaction.atomic() blocks. Alternatively, switch to session=True for lock 102 so each batch can commit independently. |
| **Effort** | M |
| **Priority** | P2 |

**Evidence — backfill_thumbnails.py:56-57, 90-97** *(supports: "outer transaction spans filesystem I/O; all IDs loaded eagerly")*:
```python
with transaction.atomic():
    with advisory_lock(LOCK_ID):
        ...
        ids = list(queryset.values_list("id", flat=True))  # ALL ids in memory
        for i in range(0, len(ids), batch_size):
            ...
            self._process_one(service, ad_image)  # filesystem I/O inside txn
```

### LOW

#### DB-011: LOW — Advisory lock docstring lists IDs 102/103 as session-scoped but code uses transaction-scoped

| Field | Value |
|---|---|
| **ID** | DB-011 |
| **Title** | Advisory lock docstring lists IDs 102/103 as session-scoped but code uses transaction-scoped |
| **Severity** | LOW |
| **Category** | Doc-code mismatch |
| **File(s)** | apps/core/utils/advisory_lock.py:52-57 (docstring); apps/core/enums.py:23-43 |
| **Status** | Open |
| **Problem** | The advisory_lock.py docstring lists BACKFILL_THUMBNAILS (102) and SWEEP_ORPHANED_MEDIA (103) under "Session-scoped (pg_advisory_lock)" but both commands use session=False (transaction-scoped, pg_advisory_xact_lock). The test suite enforces session=False for all sweep commands. |
| **Impact** | Misleading documentation. A reader could expect session-scoped lock semantics for IDs 102/103, which would change concurrency behavior (session locks persist beyond transaction boundaries). Could cause confusion during maintenance. |
| **Root Cause** | Docstring was not reconciled with actual code usage when sweep commands were refactored to use transaction-scoped locks. |
| **Recommendation** | Move IDs 102 and 103 from the "Session-scoped" section to the "Transaction-scoped" section in advisory_lock.py docstring. |
| **Effort** | S (doc fix) |
| **Priority** | P2 |

**Evidence — advisory_lock.py:52-57** *(supports: "docstring lists 102/103 under Session-scoped")*:
```
Session-scoped (pg_advisory_lock; spans the connection, pre-PgBouncer):
  100  MIGRATE
  101  CREATE_ADMIN
  102  BACKFILL_THUMBNAILS          thumbnail backfill
  103  SWEEP_ORPHANED_MEDIA         orphaned media sweep
```

**Evidence — backfill_thumbnails.py:57, sweep_orphaned_media.py:138** *(supports: "both use default session=False")*:
```python
# backfill_thumbnails.py:57
with advisory_lock(LOCK_ID):  # BACKFILL_THUMBNAILS=102, no session=True

# sweep_orphaned_media.py:138
with advisory_lock(AdvisoryLockId.SWEEP_ORPHANED_MEDIA):  # no session=True
```

#### DB-013: LOW — No concurrency test for archive_sweep row-level locking

| Field | Value |
|---|---|
| **ID** | DB-013 |
| **Title** | No concurrency test for archive_sweep row-level locking — test gap |
| **Severity** | LOW |
| **Category** | Test quality |
| **File(s)** | apps/core/tests/test_sweep_archive.py, apps/core/tests/test_sweep_lock_structure.py |
| **Status** | Open |
| **Problem** | No test verifies select_for_update() usage or concurrent-modification handling in archive_sweep. test_edit_views_locking.py has structural assertions for ad_edit, ad_archive, ad_reactivate, ad_delete, submit_ad — but not archive_sweep. |
| **Impact** | DB-010 regression can be reintroduced without any test failure. |
| **Root Cause** | The select_for_update structural test pattern was not extended to the management command layer. |
| **Recommendation** | Add structural assertion (assert "select_for_update" in source) to test_sweep_archive.py, mirroring test_edit_views_locking.py:51-57. Add a threading-based concurrency test matching test_transition_concurrency.py pattern. |
| **Effort** | M (structural test: S; concurrency test: M) |
| **Priority** | P2 |

## Cross-Finding Analysis

- **Merge candidates:** DB-010 and DB-013 are related — DB-013 (missing test) is the safety net that would catch DB-010 (missing lock). Fixing DB-010 should include adding the test from DB-013.
- **Conflicting evidence:** None.
- **Dependency chains:** DB-010 should be fixed alongside DB-013 (add test). DB-011 and DB-012 are independent.

## Remediation Roadmap

| Order | ID | Severity | Effort | Priority | Recommendation (summary) |
|-------|----|----------|--------|----------|--------------------------|
| 1 | DB-010 | HIGH | S | P1 | Add .select_for_update().order_by("pk") to archive_sweep queryset |
| 2 | DB-013 | LOW | S | P2 | Add structural select_for_update assertion to test_sweep_archive.py |
| 3 | DB-012 | MEDIUM | M | P2 | Move filesystem I/O outside transaction in backfill_thumbnails.py |
| 4 | DB-011 | LOW | S | P2 | Fix advisory_lock.py docstring (move IDs 102/103 to transaction-scoped) |

## Rollout Safety

| ID | Risk | Backward-compatible? | Test gap (must cover) |
|----|------|----------------------|-----------------------|
| DB-010 | Low | Yes | Concurrency test for archive_sweep vs concurrent web edit |
| DB-013 | N/A | Yes | New structural test; existing tests unaffected |
| DB-012 | Medium | Yes (performance opt) | Verify backfill processes all images; no DB rows lost |
| DB-011 | None | Yes (doc-only) | None |
