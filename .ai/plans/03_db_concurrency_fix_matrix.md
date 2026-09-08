# Phase 03 — Database & Concurrency Fix Matrix

**Audit source:** `.ai/audit/99-validation/03-db-concurrency-validated-findings.md`
**Status:** Batch A (DB-001 + DB-004) implemented, tested, and committed (commit 2039249). Batch B (DB-002) implementation in progress.
**Execution order (dependency):** DB-001 → DB-002 → DB-003 → DB-004
**DB-004 runs independently (no file overlap with DB-001/002/003)**

---

## 1. Classification Summary

| ID | Severity | Type | Classification | Rationale | Selected approach |
|----|----------|------|----------------|-----------|-------------------|
| DB-001 | HIGH | SPEC-DEVIATION | **Simple / Low-risk** | Single new middleware class + one registration line; purely additive; well-understood asgiref threading model | Aiogram `outer_middleware` calling `await sync_to_async(close_old_connections)()` in `try/finally` |
| DB-002 | HIGH | BEST-PRACTICE | **Complex / High-risk** | Contract change: `set_published` raises new typed `MaxAdsExceeded`; ripples across 3 writer paths (bot, web-review, web-bulk) | Centralize `User.objects.select_for_update()` + authoritative re-count in `set_published` |
| DB-003 | MEDIUM | SPEC-DEVIATION | **Multiple-viable-routes** | Two approaches compete: A (lock+refresh) vs B (DB rowcount precondition); B rejected (bypasses post_save signals) | `select_for_update()` at fetch sites + `self.refresh_from_db()` chokepoint in `transition_to` |
| DB-004 | MEDIUM (advisory) | BEST-PRACTICE | **Simple / Low-risk** | Four mechanical line-edits + one one-line code change; no migration; no new model/daemon | Reconciliation sweep: fix `sweep_orphaned_media`, schedule hourly, route `os.remove`→`delete_photo`, add lock-structure tests |

---

## 2. Implementation Plan per Finding

### DB-001 — Bot never closes DB connections (HIGH)

**Selected approach:** New `DatabaseConnectionMiddleware` as `dp.update.outer_middleware()` calling `await sync_to_async(close_old_connections)()` in `try/finally`.

**Files:**
| File | Action | Detail |
|------|--------|--------|
| `src/telegram_bot/middlewares/connection.py` | **CREATE** | `DatabaseConnectionMiddleware(BaseMiddleware)` — `__call__` wraps `await handler(event, data)` in `try/finally`, `finally` calls `await sync_to_async(close_old_connections)()` |
| `src/telegram_bot/middlewares/__init__.py` | EDIT | Add `from .connection import DatabaseConnectionMiddleware` + `__all__` entry |
| `src/telegram_bot/main.py` | EDIT | Line 20: add `DatabaseConnectionMiddleware` to import; after line 55: add `dp.update.outer_middleware(DatabaseConnectionMiddleware())` |
| `src/telegram_bot/tests/conftest.py` | EDIT | In `dp` fixture (~line 72): register `dp.update.outer_middleware(DatabaseConnectionMiddleware())` |

**Design decisions (Tech Lead review):**
- MUST use `sync_to_async(close_old_connections)` — calling `close_old_connections()` directly from the async event-loop thread targets the wrong thread (event loop has no worker-thread connection → no-op) OR raises `SynchronousOnlyOperation` (BaseDatabaseWrapper.close is `@async_unsafe`). The `sync_to_async` dispatch lands the call on asgiref's single shared worker thread where the thread-local `BaseDatabaseWrapper` lives.
- MUST use `outer_middleware` (not inner) so the cleanup wraps ALL inner middlewares + all routers/handlers — fires after all sync ORM work.
- `try/finally` ensures cleanup even on handler exception (prevents abandoned transaction state).
- Reconnect wrapper around `run_polling` is DEFERRED (per audit) — Docker `restart: unless-stopped` covers process-level recovery.

**Tests:**
- **New:** `src/telegram_bot/tests/test_db_connection_middleware.py`
  - `test_connection_closed_after_update` — ORM work in handler, assert worker-thread connection is None after update
  - `test_connection_closed_after_handler_exception` — handler raises, assert close still ran (try/finally)
  - `test_no_error_when_no_orm` — no ORM work, close is safe no-op
  - `test_connection_refreshed_on_next_update` — two updates, assert fresh connection each (connection_created fires twice)
  - `test_uses_sync_to_async` — mock `close_old_connections`, assert dispatched via sync_to_async (guards against regression to direct call)
  - `test_registered_as_outer_middleware` — assert on `dp.update.outer_middleware`

**Quality gates:**
```bash
uv run ruff check src/telegram_bot/middlewares/connection.py src/telegram_bot/main.py src/telegram_bot/middlewares/__init__.py src/telegram_bot/tests/conftest.py src/telegram_bot/tests/test_db_connection_middleware.py
uv run basedpyright src/telegram_bot/middlewares/connection.py
$dc run --rm -e PYTEST_OPTS="-k test_db_connection_middleware" test
```

**Docs:** Module docstring in `connection.py`. Update `docs/99-agent/architecture.md` — add "Bot DB Connection Lifecycle" subsection. (See Step 5.)

---

### DB-002 — max_ads_per_user count-then-commit race (HIGH)

**Selected approach:** Centralize lock + authoritative re-count inside `set_published`'s existing `transaction.atomic()` via `User.objects.select_for_update().get(pk=ad.user_id)`, raise typed `MaxAdsExceeded` if `count >= max_ads`.

**Tech Lead decision (deviation from researcher's suggestion):** The researcher suggested catching `MaxAdsExceeded` inside `_pass_moderation`. This is **rejected** because `_pass_moderation` returns `None` — if it swallows the exception and calls `_fail_moderation`, `auto_moderate` would return `True` (line 164-165: `_pass_moderation(ad); return True`), falsely reporting publish success when the ad was actually failed. **Instead**, let `MaxAdsExceeded` propagate from `set_published` through `_pass_moderation`'s atomic (which rolls back, releasing the User lock), and catch it in `auto_moderate` which calls `_fail_moderation` and returns `False`. The User lock is released before `_fail_moderation` runs — this is safe because the failure path (`ON_MODERATION_FAILED` transition) does not touch the user's ad count.

**Files:**
| File | Action | Detail |
|------|--------|--------|
| `src/backend/apps/moderation/services/exceptions.py` | **CREATE** | `class MaxAdsExceeded(Exception)` carrying `user_id`, `active_count`, `max_ads` (mirrors `currencies/services/exceptions.py` pattern) |
| `src/backend/apps/moderation/services/__init__.py` | EDIT | (Optional) export `MaxAdsExceeded` |
| `src/backend/apps/moderation/services/moderation_log.py` | EDIT | Add imports (`User`, `ModerationCriteria`, `MaxAdsExceeded`); insert lock+recount+raise at top of `set_published`'s `transaction.atomic()` |
| `src/backend/apps/moderation/services/auto_moderation.py` | EDIT | In `auto_moderate`: wrap `_pass_moderation(ad)` (line 164) in `try/except MaxAdsExceeded` → `_fail_moderation(ad); return False` |
| `src/backend/apps/moderation/views/review.py` | EDIT | `approve_ad` view (line 51-68): catch `MaxAdsExceeded` → error response (see DB-003 for the `select_for_update` wrap applied on top) |
| `src/backend/apps/moderation/admin_actions.py` | EDIT | `bulk_approve` (line 114-129): catch `MaxAdsExceeded` per-ad, log + skip (do NOT abort the entire bulk) |

**Implementation detail — `set_published`:**
```python
with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]  (line 218, existing)
    # DB-002: lock User row + authoritative re-count (closes TOCTOU for all 3 writers)
    User.objects.select_for_update().get(pk=ad.user_id)
    max_ads = ModerationCriteria.get_singleton().max_ads_per_user
    active_count = Ad.objects.filter(
        user_id=ad.user_id,
        status__in=[AdStatus.PUBLISHED, AdStatus.ON_MODERATION],
    ).count()
    if active_count >= max_ads:
        raise MaxAdsExceeded(user_id=ad.user_id, active_count=active_count, max_ads=max_ads)
    ad.transition_to(AdStatus.PUBLISHED, moderator_id=moderator_id)  # unchanged
    ...  # logging unchanged
```

**Imports in moderation_log.py:**
- `from apps.moderation.models import ModeratorActionLog` → add `ModerationCriteria`
- `from apps.moderation.services.exceptions import MaxAdsExceeded`
- `from apps.ads.models import Ad` (module-level — safe: `auto_moderation.py` already imports Ad at module level in this same package)
- `from apps.users.models import User`

**Existing test impact (must remain green):**
- `test_auto_moderation.py::test_auto_moderate_pass_sets_published_and_analytics` — under default cap (10), passes
- `test_admin_actions.py::test_approve_ad_routes_through_set_published` — mocks `set_published`, so `MaxAdsExceeded` never fires
- `test_moderation_views.py::TestApproveAdView::test_approve_transitions_to_published` — under cap, succeeds

**New tests:**
- `test_auto_moderation.py` — `TestMaxAdsRaceCondition`: concurrent `auto_moderate` race (2 threads, `max_ads=2`, 1 PUBLISHED + 2 ON_MODERATION drafts) → exactly 1 PUBLISHED, 1 ON_MODERATION_FAILED
- `test_moderation_log.py` (new) — `test_set_published_raises_max_ads_exceeded`: direct `set_published` call when over cap → `MaxAdsExceeded` with correct attributes; lock released on rollback
- `test_admin_actions.py` — `test_bulk_approve_skips_over_cap`: bulk_approve with one ad over cap → 1 succeeds, 1 skipped, no abort
- `test_moderation_views.py` — `TestApproveAdView::test_approve_over_cap_returns_error`: web approve when user at cap → not PUBLISHED, error response

**Quality gates:**
```bash
uv run ruff check src/backend/apps/moderation/services/exceptions.py src/backend/apps/moderation/services/moderation_log.py src/backend/apps/moderation/services/auto_moderation.py src/backend/apps/moderation/views/review.py src/backend/apps/moderation/admin_actions.py
uv run ruff format --check src/backend/apps/moderation/
uv run basedpyright src/backend/apps/moderation/services/
# No migration (no schema change)
$dc run --rm -e PYTEST_OPTS="-k 'auto_moderation or admin_actions or moderation_views'" test
```

---

### DB-003 — Stale in-memory instance in transition_to (MEDIUM)

**Selected approach A:** `self.refresh_from_db()` at top of `Ad.transition_to` (single chokepoint) + `select_for_update()` at fetch sites inside `transaction.atomic()`.

**Files:**
| File | Action | Detail |
|------|--------|--------|
| `src/backend/apps/ads/models.py` | EDIT | `transition_to` (line 397): insert `self.refresh_from_db()` before `current = AdStatus(self.status)` |
| `src/backend/apps/moderation/views/review.py` | EDIT | `approve_ad` (64) + `reject_ad` (85-89): wrap fetch+action in `transaction.atomic()` + `Ad.objects.select_for_update()` |
| `src/backend/apps/ads/views/edit.py` | EDIT | `ad_archive` (257→269): wrap in atomic+lock; `ad_reactivate` (290→303): wrap in atomic+lock; POST path of `ad_edit` (100): re-fetch under lock |
| `src/backend/apps/ads/views/delete.py` | EDIT | `ad_delete` (38→49): wrap in atomic+lock |
| `src/backend/apps/moderation/admin_actions.py` | EDIT | `bulk_approve` (126), `bulk_reject` (145), `bulk_delete` (195): wrap loops in `transaction.atomic()` + `select_for_update()` |

**Tech Lead decision — DoesNotExist policy:** `refresh_from_db()` raises `Ad.DoesNotExist` if the row was hard-deleted by a concurrent sweep. For single-ad paths, let it propagate (fail-fast — better than silent corruption). For `bulk_*` paths, wrap per-ad `transition_to` in `try/except Ad.DoesNotExist` that logs + `continue`s (one vanished row shouldn't abort a bulk action). This keeps `transition_to` itself pure.

**Lock ordering (deadlock analysis — verified safe):**
- Web paths: fetch Ad with `select_for_update` → `set_published` locks User → consistent order (Ad→User)
- Bot path: no Ad fetch (in-memory) → `set_published` locks User only → no Ad lock, no conflict
- Sweeps: `queryset.update()/delete()` in PK order, no User lock → no circular wait
- Result: wait, not deadlock

**New tests:**
- `apps/ads/tests/test_transition_concurrency.py` (new)
  - T1: locked approve fires post_save signals (priority + alerts) — regression guard vs approach B
  - T2: stale-instance resurrection by concurrent sweep → refresh raises/fails-fast
  - T3: two concurrent moderator approves → one PUBLISHED, other raises ValueError (stale)
  - T4: delete-then-transition → `refresh_from_db` raises DoesNotExist
  - T5: select_for_update held across transition (structure assertion, mirroring test_sweep_lock_structure.py)
  - T6: bulk actions skip deleted rows

**Quality gates:**
```bash
uv run ruff check src/backend/apps/ads/models.py src/backend/apps/ads/views/edit.py src/backend/apps/ads/views/delete.py src/backend/apps/moderation/views/review.py src/backend/apps/moderation/admin_actions.py
uv run basedpyright src/backend/apps/ads/models.py
$dc run --rm -e PYTEST_OPTS="-k transition_concurrency" test
```

---

### DB-004 — Sweep media deletion outside transaction (MEDIUM, advisory)

**Selected approach:** Reconciliation sweep — fix `sweep_orphaned_media`, schedule hourly, route `os.remove`→`delete_photo`, add lock-structure tests. Outbox SUPERSEDED.

**Files:**
| File | Action | Detail |
|------|--------|--------|
| `src/backend/apps/core/enums.py` | EDIT | Add `SWEEP_ORPHANED_MEDIA = 103` after `BACKFILL_THUMBNAILS = 102` (line 37) |
| `src/backend/apps/media/services/filesystem.py` | EDIT | (Already correct — no change) |
| `src/backend/apps/media/management/commands/sweep_orphaned_media.py` | EDIT | Import `delete_photo`; replace `os.remove` loop (lines 107-131) with `delete_photo(key)` calls; drop `errors` counter (delete_photo never raises) |
| `docker/entrypoint-scheduler.sh` | EDIT | Add `'sweep_orphaned_media'` to `hourly_commands` (after `'sweep_drafts'`, line 32) |
| `src/backend/apps/core/tests/test_sweep_lock_structure.py` | EDIT | Add `("sweep_orphaned_media", AdvisoryLockId.SWEEP_ORPHANED_MEDIA)` to `SWEEP_COMMANDS` (line 48) + module path to `_LOCK_TARGET_MODULES` (line 66) |

**Tech Lead decision — `errors` counter:** `delete_photo` never raises (swallows FileNotFoundError + final OSError). Routing through it makes the per-key `try/except` + `errors` counter dead code. Decision: **drop `errors`**, use `delete_photo` for consistent retry/backoff (matching the 6 sibling sweeps). Failures still logged by `delete_photo` itself.

**Tests:**
- `test_sweep_lock_structure.py` — extended: `sweep_orphaned_media` acquires lock 103 inside `transaction.atomic()`, `session=False`
- `apps/media/tests/test_sweep_orphaned_media.py` (new) — T1-T5 from research: orphan deleted/ref kept, all 4 fields, seed/ excluded, dry-run, delete_photo routing verified
- `test_advisory_lock_ids.py` — add `test_advisory_lock_id_sweep_orphaned_media` asserts `== 103`
- New: scheduler-wiring test (static read of `entrypoint-scheduler.sh` asserting `'sweep_orphaned_media'` in hourly_commands)

**Quality gates:**
```bash
uv run ruff check src/backend/apps/core/enums.py src/backend/apps/media/management/commands/sweep_orphaned_media.py src/backend/apps/core/tests/test_sweep_lock_structure.py src/backend/apps/core/tests/test_advisory_lock_ids.py
uv run basedpyright src/backend/apps/media/management/commands/sweep_orphaned_media.py src/backend/apps/core/enums.py
# No migration confirmation:
$dc run --rm -e PYTEST_OPTS="" test sh -c "python src/backend/manage.py makemigrations --dry-run --check"
$dc run --rm -e PYTEST_OPTS="-k sweep_orphaned_media or test_all_sweep_commands_lock" test
bash -n docker/entrypoint-scheduler.sh
```

---

## 3. Execution Sequence & Dependencies

```
Batch A (parallel, no overlap):
  DB-001  →  bot connection middleware
  DB-004  →  reconciliation sweep            [no file overlap with DB-001]

Batch B (after DB-001 committed):
  DB-002  →  max_ads lock in set_published   [needs healthy connection from DB-001]
             + exception handling in auto_moderate / review view / bulk_approve

Batch C (after DB-002 committed):
  DB-003  →  refresh_from_db + select_for_update  [review.py overlaps with DB-002]
             + edit.py / delete.py / admin_actions.py fetch sites
```

**Ordering rationale:**
- DB-001 first: the `select_for_update` locks in DB-002/DB-003 need a healthy, refreshable connection. Without DB-001, a DB blip would strand the locks forever.
- DB-002 before DB-003: both modify `review.py` `approve_ad`. DB-002 adds `MaxAdsExceeded` handling; DB-003 wraps the same function in `transaction.atomic()` + `select_for_update()`. Sequential commits avoid merge conflicts.
- DB-004 independent: touches `.py` enums, management command, scheduler shell script, and test lists. No overlap with DB-001/002/003.

**Lock-ordering (deadlock) — verified safe across all findings:**
- DB-002 locks **User** row.
- DB-003 locks **Ad** row.
- Web paths lock Ad first (fetch) then User (in `set_published`) — consistent order.
- Bot path locks User only (no Ad fetch).
- Sweeps lock Ad rows in PK order (bulk), no User lock.
- No circular wait possible.

---

## 4. Test & Documentation Matrix

| Finding | Test file(s) | Doc updates | Migration? |
|---------|-------------|-------------|------------|
| DB-001 | `tests/test_db_connection_middleware.py` (new) | `connection.py` docstring; `docs/99-agent/architecture.md` (bot DB lifecycle section) | No |
| DB-002 | `test_auto_moderation.py` (race test), `test_moderation_log.py` (new, direct raise), `test_admin_actions.py` (bulk skip), `test_moderation_views.py` (web error) | `exceptions.py` docstring (internal) | No |
| DB-003 | `ads/tests/test_transition_concurrency.py` (new) | None (no doc drift per audit) | No |
| DB-004 | `test_sweep_lock_structure.py` (extended), `media/tests/test_sweep_orphaned_media.py` (new), `test_advisory_lock_ids.py` (extended), scheduler-wiring test (new) | None (audit says None) | No |

---

## 5. Quality Gates (consolidated)

```bash
# Per-finding lint + typecheck (see §2 per file lists)
uv run ruff check <affected>
uv run ruff format --check <affected>
uv run basedpyright <affected>

# Tests (Docker only — local uv run pytest fails without test DB)
$dc='docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml'
$dc up -d db
$dc run --rm --env PYTEST_SKIP_MARKERS=seed test            # fast gate
# No migration for any finding:
$dc run --rm -e PYTEST_OPTS="" test sh -c "python src/backend/manage.py makemigrations --dry-run --check"
```

**i18n:** DB-002's web approve_ad view adds a user-visible error message → wrap in `gettext_lazy` `{% trans %}`/gettext. Run `makemessages` if adding strings to templates. (DB-001/003/004 add no user-visible strings.)
