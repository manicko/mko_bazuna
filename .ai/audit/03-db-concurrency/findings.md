---
phase: "03"
phase_name: "Database & Concurrency Consistency"
date: "2026-09-28"
auditor: "Executor (subagent)"
mode: "problems-only"
id_prefix: "DB"
report_status: "draft"
severity_taxonomy: ".kilo/commands/audit/phases/03-audit-db-concurrency.md#severity-taxonomy"
---

# Audit Findings — Database & Concurrency Consistency

## Executive Summary

Two serious defects were confirmed in how the website and the Telegram bot share the
database. First, the safety net that is supposed to protect a seller from losing their
part-finished ad if two requests collide is itself broken: when the collision happens, the
code crashes instead of recovering, so the seller's ad is destroyed. Second, a routine
"analytics" write is deliberately designed never to fail, but it is called in the middle of
real business transactions — when it does fail, it silently destroys the whole business
operation it was only supposed to observe. Beyond these, four more situations were proven
where one part of the system quietly destroys work another part is doing right now: the
nightly clean-up deletes ads a seller is still typing, the media clean-up deletes photos
belonging to an ad that is being published at that exact moment, the delete sweep undoes a
just-completed reactivation, and any momentary database row lock freezes every Telegram user
out of the bot for as long as the lock is held. The most urgent business impact is loss of
seller-created ads and loss of listing photos.

## Scope & Methodology

**Scope:** All shared-database surfaces of the two-process system — the `Ad`/`AdImage`/
`LoginToken`/`SavedSearch` write paths in `src/backend/apps/*` and `src/telegram_bot/*`, the
eleven transaction-scoped and five session-scoped advisory-lock call sites in
`src/backend/apps/core/utils/advisory_lock.py` and every management command that takes a
lock, the transaction boundaries around all multi-row domain writes, the `sync_to_async`
dispatch surface of the bot, and the per-process connection configuration in
`src/backend/config/settings/`. Process startup and configuration *values* were left to
Phases 01/02; only the concurrency consequences of those values are reported here.

### Runtime Verification

| R# | Check | Method | Result |
|----|-------|--------|--------|
| R-01 | No connection leak / no exhaustion from either process | `.ai/audit/03-db-concurrency/verify_db.py` §I: 16 threads × 5 queries with `connections.close()` per iteration; `pg_stat_activity` read from an independent psycopg connection | PASS — 0 errors, 0 `idle in transaction`, 3 total connections, `max_connections=100` |
| R-02 | Effective per-process `CONN_MAX_AGE`; prepared statements disabled for a transaction-mode pooler | §A `connections["default"].settings_dict` under `config.settings.test`; `docker-compose.prod.yml:172-193` (`PGBOUNCER_POOL_MODE=transaction`); `src/backend/config/settings/base.py:245-266` | PASS — `CONN_MAX_AGE=0`, `OPTIONS={'prepare_threshold': None}` in **both** the `DATABASE_URL` and discrete-var branches; PgBouncer is `--profile`-gated and no app service points at it |
| R-03 | No bare synchronous ORM on the bot event loop | `.ai/audit/03-db-concurrency/scan_async_orm.py` — AST gate: the innermost enclosing frame of every `.objects` / `transaction.atomic` / `close_old_connections` call must be a `@sync_to_async` sync `def`; `sync_to_async(<orm callable>)` is treated as the dispatch itself | PASS — `TOTAL=0`, exit 0 across `src/telegram_bot` (an earlier coarser revision of the gate reported 6 hits, all of which were the *arguments* of `sync_to_async(...)` calls in `lifecycle.py` and `middlewares/connection.py` and were removed by making the gate frame- and dispatch-aware) |
| R-04 | Advisory lock serialises two simultaneous sweeps | §D: two barrier-synced threads, each `transaction.atomic()` + `advisory_lock(ARCHIVE_SWEEP)`, 2 s hold | PASS — thread B waited 2.01 s, thread A 4.02 s, zero overlap |
| R-05 | Lock is observable in `pg_locks` and released on commit **and** rollback | §E / §F with a second connection querying `pg_locks WHERE locktype='advisory'` | PASS — 1 advisory row while held, 0 after commit, 0 after a forced rollback |
| R-06 | Concurrent `LoginToken` claim yields exactly one claim | §G: 4 threads issuing the production `UPDATE … RETURNING` against one token | PASS — exactly 1 of 4 claimed |
| R-07 | `create_draft_ad` concurrency backstop | §B (direct) and §H2 (6 real threads running the exact function body) | **FAIL** → DB-001 |
| R-08 | `record_event` is transaction-transparent | §C (deferred FK violation) and §C2 (immediate statement error) | **FAIL** → DB-002 |
| R-09 | `copy_ad` respects the single-DRAFT invariant | §O and `.ai/audit/03-db-concurrency/verify_db.py §O` | **FAIL** → DB-009 (rollback itself is correct; the `IntegrityError` simply propagates) |
| R-10 | The two alert-delivery writers share a serialisation lock | §N: `find_matching_saved_searches` (immediate path) then `find_matching_ads` (daily path) against the same un-notified ad | **FAIL** → DB-007 |
| R-11 | Orphaned rows / media / lost work after normal operation | §J (`sweep_drafts` vs live dialog), §K (`delete_sweep` vs reactivation), §M (orphan sweep vs in-flight `submit_ad`), §L (row-lock stall) | **FAIL** → DB-003, DB-004, DB-005, DB-006 |
| R-12 | Linter + type-check + focused concurrency test suite | `uv run ruff check` on the advisory-lock, sweep, submission and analytics surface; `uv run basedpyright src/telegram_bot src/backend/apps/core/utils/advisory_lock.py src/backend/apps/core/services/analytics.py`; compose `test` service over 11 concurrency test files with the canonical `-n auto --dist loadgroup` args | PASS — ruff clean; basedpyright clean on the surface (4 pre-existing errors live only in `src/telegram_bot/tests/test_ad_create.py`); **86 passed in 61.48 s**, exit 0 |

> PASS results prove the audit was thorough; they are METHODOLOGY evidence, NOT findings.

**Tools used:** `uv run ruff check`, `uv run basedpyright`, a purpose-built AST static
gate (`.ai/audit/03-db-concurrency/scan_async_orm.py`), a purpose-built runtime harness
(`.ai/audit/03-db-concurrency/verify_db.py`) executed inside the `mko-bazuna-test` compose
project against PostgreSQL 18 with its full captured output retained at
`.ai/audit/03-db-concurrency/verification-output.txt`, `pg_stat_activity` / `pg_locks`
probes over a second psycopg connection, and the `test` compose service for the existing
suite.

**Assumptions:** "PostgreSQL 18" — verified at runtime; "Django 5.2 LTS, `CONN_MAX_AGE=0`"
— read from the live settings object, not from source; the two processes are `web`
(gunicorn, 3 sync workers, `gunicorn.conf.py:15`) and `bot` (aiogram polling, one asgiref
`thread_sensitive` worker thread) plus a `scheduler` process that shells out one management
command at a time; the test stack is the only running stack, so all runtime evidence is
produced against the `mko_bazuna-test` project database (sentinel rows were removed
afterwards — verified `0` leftover `audit%` users/ads/images).

**Not audited (out of scope / blocked):** the dev stack could not be used for
cross-process observation because `mko-bazuna-dev` web and bot are crash-looping on a
placeholder `BOT_TOKEN` in `.env.dev` (reported by Phase 02 as CFG-006); lock-hold
*durations* under production data volume could not be measured, so DB-008 is graded from
source structure plus the §L lock-hold simulation rather than from a real sweep timing.

## Findings Summary

| ID | Title | Severity | Status | Category |
|----|-------|----------|--------|----------|
| DB-001 | `create_draft_ad`'s race backstop always raises `TransactionManagementError` instead of recovering | CRITICAL | Open | Reliability / data integrity |
| DB-002 | `record_event` swallows database errors inside the caller's transaction, aborting the whole domain write | CRITICAL | Open | Correctness / transaction integrity |
| DB-003 | `sweep_drafts` reaps an ad the seller is still typing, destroying the whole listing | HIGH | Open | Cross-process consistency |
| DB-004 | A single blocked row lock stalls every database operation in the bot, with no lock timeout anywhere | HIGH | Open | Availability / async dispatch |
| DB-005 | `sweep_orphaned_media` deletes media belonging to `AdImage` rows that are still committing | MEDIUM | Open | Cross-process consistency |
| DB-006 | Delete and purge sweeps delete without a row lock, silently undoing a concurrent reactivation | MEDIUM | Open | Lost update |
| DB-007 | Immediate-alert and daily-alert writers share no lock and both select the same `(saved_search, ad)` pair | MEDIUM | Open | Cross-process consistency |
| DB-008 | Hourly and full-table sweeps hold `select_for_update()` row locks for their entire duration | MEDIUM | Open | Contention / isolation |
| DB-009 | `copy_ad` has no handling for the single-DRAFT invariant and 500s when the bot holds the draft | MEDIUM | Open | Cross-process consistency |
| DB-010 | The transaction-scoped lock's "released" log fires only on commit, never on the rollback operators need | LOW | Open | Observability |
| DB-011 | Five delete/purge sweeps pre-collect media keys inside the lock-held transaction only to log a count | LOW | Open | Maintainability |

## Distribution

**Severity counts**

| CRITICAL | HIGH | MEDIUM | LOW |
|----------|------|--------|-----|
| 2 | 2 | 5 | 2 |

**Status counts**

| Status | Count |
|--------|-------|
| Open | 11 |

## Findings by Severity

### CRITICAL

#### DB-001: [CRITICAL] — `create_draft_ad`'s race backstop always raises `TransactionManagementError` instead of recovering

| Field | Value |
|---|---|
| **ID** | DB-001 |
| **Title** | `create_draft_ad`'s race backstop always raises `TransactionManagementError` instead of recovering |
| **Severity** | CRITICAL |
| **Category** | Reliability / data integrity (ISO 25010) |
| **File(s)** | `src/telegram_bot/services/ad_data/orm.py:48-67` |
| **Status** | Open |
| **Problem** | `create_draft_ad` is the only place a seller's draft ad is created. It deletes any pre-existing DRAFT, creates a new one, and relies on the partial unique index `uq_ads_single_draft_per_user` to catch a concurrent creation. The `except IntegrityError:` recovery branch issues two more statements *inside the same outermost `transaction.atomic()` block that is the first statement of the function*. Because that is the outermost atomic block, Django creates no savepoint, so the transaction is already aborted when the recovery branch runs: its first `Ad.objects.filter(...).delete()` raises `TransactionManagementError` and the advertised "clean up and retry" never executes. |
| **Impact** | The exact scenario the backstop exists for — two `create_draft_ad` calls for one seller racing (bot FSM entry, bot `/copy`, web, or a second bot worker) — turns into an unhandled `TransactionManagementError` instead of a clean retry. The whole atomic block rolls back, so the pre-existing DRAFT the function had already deleted is *not* deleted either; the seller is left with a bot that raises on `/post`, and no new draft to continue. In the 6-thread reproduction 5 of 6 concurrent creations raised; the only survivor is whichever thread never hit the index. |
| **Root Cause** | `IntegrityError` recovery was written as if it were inside a savepoint. The project already demonstrates the correct pattern 150 lines away in `src/telegram_bot/handlers/login.py:227-240`, where `User.objects.get_or_create` is wrapped in a nested `transaction.atomic()` precisely so an `IntegrityError` can be caught and retried. `create_draft_ad` has no such nested block. |
| **Recommendation** | Wrap the `Ad.objects.create(...)` call in a nested `transaction.atomic()` (a savepoint) so the `except IntegrityError` branch runs against a usable transaction — mirroring `login.handle_login_orm`. Keep the existing cleanup-then-retry. Add a regression test that forces `uq_ads_single_draft_per_user` to fire and asserts a draft is returned, not a `TransactionManagementError`. |
| **Effort** | S (1 person-day) |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **Related Findings** | AD-005 (Phase 05 filed the FSM/DRAFT-persistence contract impact of the same defect) |

**Evidence — `src/telegram_bot/services/ad_data/orm.py:48`** *(supports: "the recovery branch issues its statements inside the outermost atomic block, where Django creates no savepoint")*:
```python
    @sync_to_async
    def _create() -> Ad:
        with transaction.atomic():                       # <-- outermost: no savepoint
            existing = Ad.objects.filter(user_id=user_id, status=AdStatus.DRAFT)
            if existing.exists():
                existing.delete()
            try:
                return Ad.objects.create(user_id=user_id, status=AdStatus.DRAFT)
            except IntegrityError:
                # Race: ... Clean up and retry.
                Ad.objects.filter(user_id=user_id, status=AdStatus.DRAFT).delete()   # <-- raises here
                return Ad.objects.create(user_id=user_id, status=AdStatus.DRAFT)      # <-- never reached
```

**Evidence — `.ai/audit/03-db-concurrency/verify_db.py` §B and §H2 output** *(supports: "the recovery branch raises `TransactionManagementError` in a real PostgreSQL 18 run, and 5 of 6 genuinely concurrent creations fail")*:
```text
=== B. create_draft_ad IntegrityError backstop (no inner savepoint) ===
recovery branch outcome -> TransactionManagementError: An error occurred in the
current transaction. You can't execute queries until the end of the 'atomic' block.
drafts left for user    -> 1

=== H2. create_draft_ad body raced from 6 real threads ===
   RAISED TransactionManagementError: An error occurred in the current transaction. You can't
   execute queries until the end of the 'atomic' block.
   RAISED TransactionManagementError: ... (x4 more, same error)
   ok ad_id=201
   drafts for user -> 1
```

**Evidence — `src/telegram_bot/handlers/login.py:226-240`** *(supports: "the codebase already uses the savepoint pattern this fix must adopt")*:
```python
            try:
                with transaction.atomic():      # <-- nested: creates a SAVEPOINT
                    user, created = User.objects.get_or_create(chat_id=telegram_id, ...)
            except IntegrityError:
                user = User.objects.get(chat_id=telegram_id)
                created = False
```

---

#### DB-002: [CRITICAL] — `record_event` swallows database errors inside the caller's transaction, aborting the whole domain write

| Field | Value |
|---|---|
| **ID** | DB-002 |
| **Title** | `record_event` swallows database errors inside the caller's transaction, aborting the whole domain write |
| **Severity** | CRITICAL |
| **Category** | Correctness / transaction integrity (ISO 25010) |
| **File(s)** | `src/backend/apps/core/services/analytics.py:45-60`; call sites `src/backend/apps/moderation/services/auto_moderation.py:251-255,268-278` and `src/telegram_bot/handlers/login.py:243-247` |
| **Status** | Open |
| **Problem** | `record_event` is documented as "never raising" and catches bare `Exception`, returning `None`. Its docstring states it "performs NO `transaction.atomic()` so it remains transparent to the caller's transaction boundary" — but every call site of interest is *inside* a caller's open transaction: `_pass_moderation` and `_fail_moderation` in `auto_moderation.py` wrap `record_event` in their own `atomic()`, and `login.handle_login_orm` calls it inside the token-claim transaction. When the INSERT itself fails at the database level, PostgreSQL has already put the surrounding transaction into an aborted state, and swallowing the exception lets the caller keep issuing statements against a dead transaction. |
| **Impact** | A best-effort analytics row becomes a hard, transaction-aborting failure of the operation it was only meant to observe. In the deferred-constraint case (`analytics_events` FKs are `DEFERRABLE INITIALLY DEFERRED`) the INSERT appears to succeed, every subsequent write in the transaction runs, and then **COMMIT** fails with `IntegrityError` — so the entire ad publish (`set_published` + `transition_to(PUBLISHED)` + the moderator action log) or the entire Telegram login (token claim + `get_or_create` user) is discarded, and the error surfaces at `transaction.atomic().__exit__` hundreds of lines away from the statement that caused it. In the immediate-error case the caller's very next statement raises `InternalError: current transaction is aborted, commands ignored until end of transaction block`. Either way the user-visible effect is a failed publish or a failed login traced to an "analytics" write that the code explicitly promised would never fail. |
| **Root Cause** | `except Exception` was applied to a database call that participates in a transaction the function does not own, without the savepoint the same file's sibling pattern uses. Note that `_pass_moderation` at `auto_moderation.py:280-288` *does* correctly wrap `TrustCalculator().calculate_and_save(...)` in a nested `atomic()` savepoint with a `try/except` — the codebase knows the rule, it was just not applied to `record_event`. |
| **Recommendation** | Make `record_event` transaction-safe in both directions: (a) if `connection.in_atomic_block`, wrap its own INSERT in a nested `transaction.atomic()` savepoint so a constraint failure cannot poison the caller's transaction; (b) if it cannot be made safe, mark it `transaction.atomic(using=..., savepoint=True)` or move its call sites outside the enclosing transaction, exactly as `TrustCalculator` already is. Add a regression test that makes the INSERT fail with a real `DataError` and asserts the caller's transaction still commits. |
| **Effort** | S (1 person-day) |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **Related Findings** | None |

**Evidence — `src/backend/apps/core/services/analytics.py:45`** *(supports: "the bare `except Exception` is what hides the database failure")*:
```python
    try:
        return AnalyticsEvent.objects.create(
            event_type=event_type, user_id=user_id, ad_id=ad_id, source=source,
        )
    except Exception:  # noqa: BLE001 — analytics must never break the request
        logger.exception("Failed to record analytics event %s ...", event_type, ...)
        return None
```

**Evidence — `.ai/audit/03-db-concurrency/verify_db.py` §C2 output** *(supports: "an immediate statement error inside the caller's transaction is swallowed and the caller's next statement dies with the aborted-transaction error")*:
```text
=== C2. record_event: immediate statement error inside open transaction ===
psycopg.errors.StringDataRightTruncation: value too long for type character varying(30)
  ... File "/app/src/backend/apps/core/services/analytics.py", line 46, in record_event
record_event returned  -> None
caller state afterwards-> InternalError: current transaction is aborted, commands
                         ignored until end of transaction block
```

**Evidence — `.ai/audit/03-db-concurrency/verify_db.py` §C output** *(supports: "a deferred FK failure is invisible to the caller and detonates at COMMIT, destroying every write made in the same transaction")*:
```text
=== C. record_event inside an open transaction (real FK violation) ===
record_event returned  -> ad_published at 2026-09-28 07:25:16.105531+00:00   <-- caller sees SUCCESS
caller state afterwards-> IntegrityError: insert or update on table "analytics_events"
                         violates foreign key constraint "analytics_events_user_id_b21e3686_fk_users_id"
DETAIL:  Key (user_id)=(10000000) is not present in table "users".
needs_rollback flag    -> False
```

**Evidence — `src/backend/apps/moderation/services/auto_moderation.py:265-288`** *(supports: "both `record_event` calls sit inside a caller transaction, while the very next block shows the savepoint pattern that should have been used")*:
```python
    with transaction.atomic():
        set_published(ad, moderator_id=moderator_id)
        record_event(event_type=AnalyticsEventType.AD_PUBLISHED, user_id=ad.user_id, ad_id=ad.id)
        record_event(event_type=AnalyticsEventType.MODERATION_APPROVED, user_id=ad.user_id, ad_id=ad.id)

        try:
            with transaction.atomic():          # <-- correct: SAVEPOINT isolates the failure
                TrustCalculator().calculate_and_save(ad.user)
        except Exception:
            logger.warning("Trust score calculation failed for user %s; ad still PUBLISHED", ...)
```

---

### HIGH

#### DB-003: [HIGH] — `sweep_drafts` reaps an ad the seller is still typing, destroying the whole listing

| Field | Value |
|---|---|
| **ID** | DB-003 |
| **Title** | `sweep_drafts` reaps an ad the seller is still typing, destroying the whole listing |
| **Severity** | HIGH |
| **Category** | Cross-process consistency (ISO 25010) |
| **File(s)** | `src/backend/apps/core/management/commands/sweep_drafts.py:41-69`; `src/backend/apps/ads/models.py:182-183`; `src/telegram_bot/services/ad_data/orm.py:38-67`; `src/backend/apps/ads/services/submission.py:169-173` |
| **Status** | Open |
| **Problem** | The hourly `sweep_drafts` command (lock `SWEEP_DRAFTS` = 4) deletes every `DRAFT` ad whose `created_at` is older than **30 minutes**. `created_at` is `auto_now_add`, so it is stamped the instant the seller sends `/post` — the very beginning of the conversation. The bot writes nothing back to the `Ad` row for the whole dialog: title, description, price, category, city and photos all live in aiogram FSM state and in `staging/` files, and the `Ad` row is only touched again at `submit_ad`. The advisory lock serialises *sweeps against each other*; nothing coordinates the sweep with the bot's in-flight dialog, and neither the lock nor `select_for_update()` is used against the seller's row. |
| **Impact** | A seller who takes more than 30 minutes between starting the dialog and pressing publish — reading moderation rules, choosing a city, re-uploading photos, or simply walking away for a while — returns to a bot that can no longer submit: `submit_ad` does `Ad.objects.select_for_update().get(id=input.ad_id)`, hits `Ad.DoesNotExist` and returns `(False, ["Ad not found"])`. Everything the seller typed is lost with no draft to resume, and the photos that were successfully downloaded to `staging/` are silently reclaimed hours later by `_reclaim_stale_staging`. The buyer-facing effect is a seller who abandons the platform after losing typed work. |
| **Root Cause** | Draft lifetime is measured from creation rather than from last activity, and the bot never issues a heartbeat (`updated_at` refresh) while the FSM is populated. `Ad.updated_at` exists (`auto_now`) and is the natural signal, but nothing writes it until submission. |
| **Recommendation** | Make the retention window measure *inactivity*, not age: either (a) have the bot touch `Ad.updated_at` on every FSM step that changes the ad's inputs, and have `sweep_drafts` filter on `updated_at`; or (b) keep `created_at` but extend the window to a value that cannot be exceeded by a human conversation and add a per-user "resume draft" path. Whichever is chosen, `submit_ad` should return a seller-recoverable message ("your draft expired, start again") rather than a generic failure, and `sweep_drafts` should skip rows whose `AdImage` staging files are still inside the in-flight window. |
| **Effort** | M (2-3 person-days) |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Related Findings** | DB-001 (the same function creates the draft that is later reaped) |

**Evidence — `src/backend/apps/core/management/commands/sweep_drafts.py:44-69`** *(supports: "the 30-minute window is computed from `created_at` and no row lock or heartbeat is consulted")*:
```python
                cutoff_date = timezone.now() - timedelta(minutes=30)
                queryset = Ad.objects.filter(
                    status=AdStatus.DRAFT,
                    created_at__lt=cutoff_date,        # <-- dialog START, not last activity
                )
                count = queryset.count()
                ...
                ad_ids = list(queryset.values_list("id", flat=True))
                ...
                deleted_count, _ = queryset.delete()   # <-- no select_for_update()
```

**Evidence — `src/backend/apps/ads/models.py:182-183`** *(supports: "`created_at` is stamped once, at row creation, and `updated_at` is the field that tracks activity")*:
```python
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

**Evidence — `.ai/audit/03-db-concurrency/verify_db.py` §J output** *(supports: "a draft whose `updated_at` is 30 seconds old but whose `created_at` is 31 minutes old is destroyed, and the submit-time re-fetch then fails")*:
```text
=== J. sweep_drafts vs an in-flight bot dialog ===
   draft created_at -> 2026-09-28T06:54:28.072857+00:00
   ad.updated_at    -> 2026-09-28T07:25:28.052028+00:00
   row still present after sweep_drafts -> False
   submit_ad re-fetch -> Ad.DoesNotExist (seller loses the ad)
```

---

#### DB-004: [HIGH] — A single blocked row lock stalls every database operation in the bot, with no lock timeout anywhere

| Field | Value |
|---|---|
| **ID** | DB-004 |
| **Title** | A single blocked row lock stalls every database operation in the bot, with no lock timeout anywhere |
| **Severity** | HIGH |
| **Category** | Availability / async dispatch (ISO 25010 availability) |
| **File(s)** | `src/telegram_bot/handlers/login.py:209-262` (dispatch shape); `src/backend/apps/ads/services/submission.py:171`; `src/backend/apps/ads/views/edit.py:117,284,322`; `src/telegram_bot/middlewares/connection.py:8-16`; `src/backend/config/settings/base.py:245-266` |
| **Status** | Open |
| **Problem** | Every ORM call in the bot is dispatched with `sync_to_async` at its default `thread_sensitive=True`, so all of them are serialised onto **one** asgiref worker thread that owns a single thread-local connection — exactly as `DatabaseConnectionMiddleware` documents. Any statement that waits on a row lock (the `Ad.objects.select_for_update()` in `submit_ad`, `handle_login_orm`, `ad_edit`, `ad_archive`, `ad_reactivate`) therefore blocks *every* other database operation in the whole bot, not just its own handler. Nothing bounds the wait: `CONN_MAX_AGE=0` and `CONN_HEALTH_CHECKS` are configured, but there is no `lock_timeout`, no `statement_timeout`, and no `OperationalError`/`DatabaseError` retry anywhere in `src/` or `docker/`, and the bot has no request-level timeout of its own. |
| **Impact** | One contended ad row produced a 15-second freeze in the reproduction: an *unrelated* read for a different seller could not even start until the blocked dispatch finished, and the blocked dispatch itself waited the full hold time with no timeout. In production the holder is a scheduled sweep (DB-008) or a concurrent web edit, so during that window the bot appears dead to every seller — no `/post`, no photo upload, no login, no `/alerts`. Because the wait is unbounded, a long sweep makes the outage last as long as the sweep. In the web tier the same wait is bounded only by gunicorn's `timeout = 60` (`gunicorn.conf.py:18`), at which point the worker is SIGKILLed mid-request, leaving the client with a 502 and the transaction to PostgreSQL's rollback. |
| **Root Cause** | The architecture assumes lock waits are short and rare, but a single `thread_sensitive` worker converts one long wait into a process-wide stall, and no timeout was configured at either the PostgreSQL or the application layer to convert a pathological wait into a fast, retryable failure. |
| **Recommendation** | Two independent changes, both small: (a) set a per-statement lock/statement timeout on the bot's connection (`OPTIONS: {"lock_timeout": ..., "statement_timeout": ...}` or `SET LOCAL` at the top of the `atomic()` blocks that take `select_for_update()`) and handle the resulting `OperationalError` with a bounded retry and a seller-facing message; (b) shorten the hold times that make the wait long (see DB-008). Do not "fix" this by raising asgiref's worker count — `thread_sensitive` exists so a transaction and its connection stay on one thread, and relaxing it would break the single-dispatch-per-transaction guarantee the project documents. |
| **Effort** | M (2-3 person-days) |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Related Findings** | DB-008 (the long lock holds that make this observable) |

**Evidence — `src/telegram_bot/middlewares/connection.py:8-16`** *(supports: "all ORM traffic is serialised onto one asgiref worker thread and one thread-local connection")*:
```python
asgiref's ``sync_to_async(thread_sensitive=True)`` (the default) parks all
ORM calls on a single shared worker thread that holds its own
``BaseDatabaseWrapper`` (thread-local,
``ConnectionHandler.thread_critical=True``).  Calling ``close_old_connections()``
from the async event-loop thread would target the wrong thread or raise
``SynchronousOnlyOperation`` ...
```

**Evidence — `src/backend/apps/ads/services/submission.py:169-173`** *(supports: "the bot's publish path opens a row lock with no timeout and no retry")*:
```python
    with transaction.atomic():
        try:
            ad = Ad.objects.select_for_update().get(id=input.ad_id)   # <-- unbounded wait
        except Ad.DoesNotExist:
            return False, ["Ad not found"]
```

**Evidence — `grep -rn "lock_timeout|statement_timeout|idle_in_transaction_session_timeout"` over `src/` and `docker/`** *(supports: "no timeout is configured anywhere in the codebase or the container entrypoints")*:
```text
(no matches — the only "deadlock" hits are code comments in
 src/backend/apps/core/management/commands/archive_sweep.py:51 and
 src/backend/apps/moderation/admin_actions.py:156)
```

**Evidence — `.ai/audit/03-db-concurrency/verify_db.py` §L output** *(supports: "a 15 s row-lock hold blocks an unrelated bot ORM call for 14.66 s of wall time, and the blocked call waits the full 15.05 s with no timeout")*:
```text
=== L. row lock held by sweep -> bot submit_ad + whole bot stall ===
   unrelated bot ORM read took 0.00s (blocked 14.66s wall)
   submit_ad-shaped lock acquired after 15.05s
```

---

### MEDIUM

#### DB-005: [MEDIUM] — `sweep_orphaned_media` deletes media belonging to `AdImage` rows that are still committing

| Field | Value |
|---|---|
| **ID** | DB-005 |
| **Title** | `sweep_orphaned_media` deletes media belonging to `AdImage` rows that are still committing |
| **Severity** | MEDIUM |
| **Category** | Cross-process consistency (ISO 25010) |
| **File(s)** | `src/backend/apps/media/management/commands/sweep_orphaned_media.py:41-50,128-181`; `src/backend/apps/ads/services/submission.py:161-169,218-227`; `src/backend/apps/media/services/filesystem.py` (`move_staging_to_permanent`) |
| **Status** | Open |
| **Problem** | `submit_ad` deliberately promotes the staged files to permanent `MEDIA_ROOT` **before** opening its `transaction.atomic()`, and only then inserts the `AdImage` rows inside that transaction (`submission.py:161-227`). The hourly `sweep_orphaned_media` (lock `SWEEP_ORPHANED_MEDIA` = 103) takes a *snapshot* of all referenced keys (`_collect_referenced_keys`) and then walks the whole `MEDIA_ROOT` to find files not in that snapshot. The advisory lock only excludes a second sweep; it does not exclude the bot or web process committing a new `AdImage` row. Any `AdImage` row created after the snapshot but whose file was already promoted is classified as an orphan and its bytes are unlinked from disk. |
| **Impact** | The committed `AdImage` row points at a file that no longer exists: a published listing loses one or all of its photos permanently, with no error anywhere in the submit path (the `submit_ad` transaction commits cleanly) and no repair path short of the seller re-uploading. The exposure window is not a millisecond race — it spans the entire `os.walk` of `MEDIA_ROOT`, which on a real media volume is minutes. Running as a full snapshot → walk → delete also means the command holds both the transaction and the sweep lock for the whole filesystem traversal. |
| **Root Cause** | Orphan detection is a stale point-in-time snapshot with no re-validation at delete time, and the promotion-then-insert ordering in `submit_ad` puts a permanently visible file in `MEDIA_ROOT` for a window in which no DB row references it. |
| **Recommendation** | Re-check before unlinking: for each candidate orphan, inside a short transaction, confirm the key is still unreferenced (`NOT EXISTS` on `AdImage.image` / `thumbnail_*`) and only then delete the file, tolerating a concurrent insert by skipping the file. Additionally, keep new files under a directory the sweep skips (mirroring the existing `staging/` exclusion) until the owning `AdImage` row is committed — that removes the window entirely rather than narrowing it. |
| **Effort** | M (2-3 person-days) |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Related Findings** | AD-003 (Phase 05: shared storage keys with no refcount — same "DB row and file can disagree" class) |

**Evidence — `src/backend/apps/ads/services/submission.py:161-169`** *(supports: "the permanent file exists on disk before the `AdImage` row is inserted, and the insert happens inside a still-open transaction")*:
```python
    # Promote staging files to permanent storage BEFORE the transaction.
    # ... On DB rollback the permanent files become unreferenced orphans
    #     reclaimed by the normal orphan sweep.
    move_staging_to_permanent(input.photos)

    # DB transaction: save + images + status transition
    with transaction.atomic():
        ...
        for photo in input.photos:
            AdImageService.create_or_skip(ad=ad, image=photo.storage_key, ...)
```

**Evidence — `src/backend/apps/media/management/commands/sweep_orphaned_media.py:137-161`** *(supports: "the referenced-key set is a snapshot and files are deleted on that stale basis, with the lock held across the walk")*:
```python
        with transaction.atomic():
            with advisory_lock(AdvisoryLockId.SWEEP_ORPHANED_MEDIA):
                referenced = _collect_referenced_keys()      # <-- point-in-time snapshot
                on_disk = set(_walk_media_files(media_root)) # <-- minutes on a real volume
                orphans = on_disk - referenced
                ...
                for key in sorted(orphans):
                    delete_photo(key)                       # <-- no re-check
```

**Evidence — `.ai/audit/03-db-concurrency/verify_db.py` §M output** *(supports: "a permanent file promoted for a not-yet-committed `AdImage` row is deleted, and the subsequently committed row points at a missing file")*:
```text
=== M. sweep_orphaned_media vs an in-flight submit_ad file move ===
   planted permanent file -> /app/media/59d7cb2e96-a1b2c3d4.jpg True
Deleted 1 orphaned media files.
   file after sweep        -> False
   AdImage row committed   -> id=46 key=59d7cb2e96-a1b2c3d4.jpg
   file on disk for row    -> False
   => live ad row points at a deleted file: True
```

---

#### DB-006: [MEDIUM] — Delete and purge sweeps delete without a row lock, silently undoing a concurrent reactivation

| Field | Value |
|---|---|
| **ID** | DB-006 |
| **Title** | Delete and purge sweeps delete without a row lock, silently undoing a concurrent reactivation |
| **Severity** | MEDIUM |
| **Category** | Lost update (ISO 25010 functional suitability) |
| **File(s)** | `src/backend/apps/core/management/commands/delete_sweep.py:42-71`; `src/backend/apps/core/management/commands/sweep_drafts.py:46-69`; `src/backend/apps/core/management/commands/purge_failed_ads.py:47-70`; `purge_rejected_ads.py:46-69`; `purge_deleted_ads.py:46-69`; contrast `src/backend/apps/core/management/commands/archive_sweep.py:47-55` |
| **Status** | Open |
| **Problem** | `archive_sweep` was hardened for DB-010: it fetches with `.select_for_update().order_by("pk")` so a concurrent write serialises and the row is re-evaluated (its own comment says "archive_sweep was the sole exception"). The other five destructive sweeps still run the unguarded `queryset.count()` → `queryset.delete()` sequence, and Django's `QuerySet.delete()` issues its `DELETE` filtered on primary key only — not on the status/timestamp predicate it selected with. A row whose state changed between the `SELECT` and the `DELETE` is therefore deleted regardless of its new state. |
| **Impact** | A seller who reactivates an archived ad (or a moderator who rescues a failed one) in the seconds between the sweep's `SELECT` and `DELETE` watches the reactivation silently disappear: `ad_reactivate` commits, the sweep then deletes the row, and the user is redirected to a dashboard with no ad and no error. The reproduction shows the final state is `GONE` even though the reactivation committed first. Because the destructive sweeps are hourly and the window is the query round-trip plus the delete, the frequency is low — but when it fires it is silent data loss of a completed user action, and the sweep's own log line reports a normal, successful deletion. |
| **Root Cause** | The DB-010 hardening was applied to one sweep instead of being extracted into a shared, lock-then-mutate helper, so the pattern diverged across the six destructive commands. |
| **Recommendation** | Apply the same `select_for_update().order_by("pk")` treatment used by `archive_sweep` to the five remaining sweeps, and make the `DELETE` predicate re-check the sweep condition (or re-verify per row inside the loop, as `archive_sweep` does via `transition_to` + `Ad.DoesNotExist` handling). Extracting one shared `locked_sweep_queryset()` helper keeps the six commands consistent and prevents the next command from repeating the omission. |
| **Effort** | S (1 person-day) |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Related Findings** | DB-008 (same commands, different aspect: hold duration) |

**Evidence — `src/backend/apps/core/management/commands/delete_sweep.py:48-71`** *(supports: "no row lock is taken and the delete is filtered on PK only")*:
```python
                queryset = Ad.objects.filter(
                    status=AdStatus.ARCHIVED,
                    archived_at__lt=cutoff_date,
                )
                count = queryset.count()
                ...
                ad_ids = list(queryset.values_list("id", flat=True))
                ...
                deleted_count, _ = queryset.delete()   # DELETE ... WHERE id IN (ad_ids)
```

**Evidence — `src/backend/apps/core/management/commands/archive_sweep.py:47-55`** *(supports: "the correct pattern already exists in the sibling command and was deliberately applied only there")*:
```python
                # DB-010: acquire row-level lock via select_for_update() to prevent
                # lost-update race between archive_sweep and concurrent web/bot writes.
                # All other Ad-mutating paths use select_for_update(); archive_sweep
                # was the sole exception. .order_by("pk") ensures deterministic lock
                # ordering to prevent deadlock under concurrent access.
                queryset = Ad.objects.filter(
                    status=AdStatus.PUBLISHED, published_at__lt=cutoff_date,
                ).select_for_update().order_by("pk")
```

**Evidence — `.ai/audit/03-db-concurrency/verify_db.py` §K output** *(supports: "a reactivation that commits between the sweep's SELECT and its DELETE is still deleted")*:
```text
=== K. delete_sweep (no row lock) vs concurrent reactivation ===
   sweep selected ids=[208]
   reactivation committed status=ON_MODERATION
   sweep deleted n=1
   final row -> GONE
```

---

#### DB-007: [MEDIUM] — Immediate-alert and daily-alert writers share no lock and both select the same `(saved_search, ad)` pair

| Field | Value |
|---|---|
| **ID** | DB-007 |
| **Title** | Immediate-alert and daily-alert writers share no lock and both select the same `(saved_search, ad)` pair |
| **Severity** | MEDIUM |
| **Category** | Cross-process consistency (ISO 25010) |
| **File(s)** | `src/backend/apps/search/services/immediate_alerts.py:67-112`; `src/backend/apps/search/management/commands/send_alerts.py:54-76`; `src/backend/apps/search/services/alert_query.py:27-132`; `src/backend/apps/moderation/signals.py:56-77` |
| **Status** | Open |
| **Problem** | Two independent writers can decide to alert the same `(saved_search, ad)` pair. The daily `send_alerts` command serialises its whole collect + persist under `AdvisoryLockId.ALERT_DELIVERY_TASK` (9). `deliver_immediate_alerts` — fired from the `Ad.post_save` signal via `transaction.on_commit`, so from whichever process published the ad — takes **no** advisory lock and runs in autocommit, one `bulk_create` per saved search. Deduplication rests entirely on the `SavedSearchNotification` row, and `find_matching_ads` excludes previously notified ads with a `NOT EXISTS` subquery evaluated at read time. Between the daily command's read and its insert, the immediate path can select the same ad; the immediate path's `ignore_conflicts=True` insert then becomes a no-op and both writers proceed to send. The ordering is the second half of the problem: the immediate path records the notification *before* handing off to `_executor.submit(_run_send, ...)`, so a failed send (two retries exhausted, or a process restart) leaves a notification row that permanently suppresses the daily "backfill" the docstrings promise. |
| **Impact** | When `IMMEDIATE_ALERTS_ENABLED` is turned on, a subscriber can receive the same listing twice — once as a per-ad message and once inside the daily digest — which is the behaviour `alert_query.py:34-35` and `immediate_alerts.py:97` both claim is impossible. And any transient Telegram failure during an immediate send silently drops that alert forever, because the row that would have triggered the backfill already exists. Today the feature ships **off** (`IMMEDIATE_ALERTS_ENABLED` default `False`, verified `False` at runtime), so the double-send path is latent rather than live; the notification-before-send ordering is live in intent but dormant. |
| **Root Cause** | Two delivery mechanisms were added for the same job without a shared serialisation primitive: the advisory lock that the batch path uses was not extended to the publish-time path, and "recorded" is being used as a proxy for "delivered" when it only means "selected". |
| **Recommendation** | Have `deliver_immediate_alerts` take `AdvisoryLockId.ALERT_DELIVERY_TASK` around its match + record step so the two writers serialise, and split "selected" from "delivered" — record the notification only after a successful send (or add an explicit delivery-state column) so a failed send is retried by the daily backfill as the module docstrings already promise. Because this path is gated off by default, schedule it together with the `IMMEDIATE_ALERTS_ENABLED` rollout rather than blocking it. |
| **Effort** | M (2-3 person-days) |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Related Findings** | None |

**Evidence — `src/backend/apps/search/services/immediate_alerts.py:93-101`** *(supports: "the immediate writer takes no lock and records the notification before the send is attempted")*:
```python
    searches = find_matching_saved_searches(ad)      # no advisory_lock anywhere in this module
    ...
    # Record notifications idempotently so the daily command never double-sends.
    for saved_search in searches:
        record_notifications(saved_search, [ad])     # <-- recorded FIRST
        saved_search.last_notified_at = timezone.now()
        saved_search.save(update_fields=["last_notified_at", "updated_at"])
    ...
    _executor.submit(_run_send, payloads)            # <-- sent LATER, failures are only logged
```

**Evidence — `src/backend/apps/search/management/commands/send_alerts.py:64-74`** *(supports: "the daily writer holds the advisory lock across collect + persist, but releases it before sending")*:
```python
        with transaction.atomic():
            with advisory_lock(AdvisoryLockId.ALERT_DELIVERY_TASK):
                user_ads, notifications_to_create, analytics_events = self._collect_alerts()
                self._persist_alerts(notifications_to_create, analytics_events)
        # Send messages outside the transaction (network I/O)
        asyncio.run(self._send_user_digests(settings.BOT_TOKEN, user_ads))
```

**Evidence — `.ai/audit/03-db-concurrency/verify_db.py` §N output** *(supports: "both writers select the same pair because exclusion depends solely on a notification row that the immediate path had not yet written")*:
```text
=== N. immediate-alert writer vs daily send_alerts writer ===
   IMMEDIATE_ALERTS_ENABLED = False
   A: find_matching_saved_searches -> [3]
   B: find_matching_ads (no lock, no notif yet) -> [211]
   notification rows for (ss, ad) -> 1
   => A sends and B sends the SAME (saved_search, ad) pair: True
```

---

#### DB-008: [MEDIUM] — Hourly and full-table sweeps hold `select_for_update()` row locks for their entire duration

| Field | Value |
|---|---|
| **ID** | DB-008 |
| **Title** | Hourly and full-table sweeps hold `select_for_update()` row locks for their entire duration |
| **Severity** | MEDIUM |
| **Category** | Contention / isolation (ISO 25010 efficiency) |
| **File(s)** | `src/backend/apps/core/management/commands/archive_sweep.py:41-91`; `src/backend/apps/currencies/management/commands/recompute_normalized_prices.py:51-100,113-117`; `src/backend/apps/core/utils/scheduler.py:55-65` |
| **Status** | Open |
| **Problem** | Both commands wrap their *entire* sweep in one `transaction.atomic()`. `archive_sweep` runs hourly (dispatched by `scheduler.py:HOURLY_COMMANDS`) and, inside that single transaction, iterates every eligible ad calling `transition_to()`, which itself does a `refresh_from_db()` plus a `save()` plus the `post_save` search-cache invalidation — so the row lock is held for two round-trips per ad, plus the signals, for as long as the whole population takes. `recompute_normalized_prices` is worse in shape: `_recompute` walks the entire non-draft ad table in 500-row batches, taking `select_for_update()` on each batch, but all inside the one outer transaction — so the locks accumulate rather than release. The scheduler also runs the nine hourly commands strictly sequentially in a single process, so the lock-holding windows stack. |
| **Impact** | No live *reader* is starved (READ COMMITTED + MVCC — verified `isolation_level = read committed` at runtime), but any live *writer* touching a locked ad blocks: the bot's `submit_ad`, the web's `ad_edit` / `ad_archive` / `ad_reactivate`, and moderation's approve/reject all open `select_for_update()` on the same row. Per DB-004 that wait lands on the bot's single shared worker thread, so the blast radius is the entire Telegram bot for the duration of the sweep, and the web requests that hit the same row are killed by gunicorn's 60 s timeout. The long transaction also pins dead row versions for its whole life, feeding autovacuum lag on the hottest table in the system. |
| **Root Cause** | All-or-nothing atomicity was applied to the whole sweep for simplicity, without noticing that the atomicity that matters is per-batch (or per-row); only `backfill_thumbnails` in the same codebase already uses the correct "short transaction + lock for the count-to-mutate sequence" split. |
| **Recommendation** | Reduce the transaction to the unit of work: take the advisory lock once, but commit every batch (or every N rows) so row locks are released promptly, and re-derive the queryset at the start of each batch. For `archive_sweep`, batching the per-row `transition_to()` calls (e.g. 100–500 per transaction) keeps the per-row transition semantics while bounding the lock window. Add a `lock_timeout` (see DB-004) so a contended batch fails fast instead of queueing behind the sweep. |
| **Effort** | M (2-3 person-days) |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Related Findings** | DB-004 (this finding is what makes the bot-wide stall in DB-004 long enough to matter) |

**Evidence — `src/backend/apps/currencies/management/commands/recompute_normalized_prices.py:51-53,113-117`** *(supports: "one transaction wraps a full-table pass, and row locks are taken per batch but never released until the end")*:
```python
        with transaction.atomic():
            with advisory_lock(AdvisoryLockId.RECOMPUTE_NORMALIZED_PRICES):
                total_checked, total_changed = self._recompute(dry_run)   # whole table

    ...
        ads = list(
            Ad.objects.select_for_update().filter(pk__in=batch_ids).only(...)   # lock retained
        )                                                                       # until the outer commit
```

**Evidence — `src/backend/apps/core/management/commands/archive_sweep.py:77-87`** *(supports: "the hourly sweep performs two round-trips plus signals per ad while holding the row lock")*:
```python
                updated_count = 0
                for ad in queryset:                     # queryset is .select_for_update()
                    try:
                        ad.transition_to(AdStatus.ARCHIVED)   # refresh_from_db() + save() + post_save
                    except (ValueError, Ad.DoesNotExist):
                        logger.warning("Skipping ad %s: no longer eligible for ARCHIVE transition", ad.id)
                        continue
                    updated_count += 1
```

**Evidence — `src/backend/apps/core/utils/scheduler.py:55-65`** *(supports: "`archive_sweep` is dispatched hourly and sequentially with the other destructive sweeps")*:
```python
HOURLY_COMMANDS: list[str] = [
    "archive_sweep",
    "delete_sweep",
    "consent_hard_delete",
    "sweep_drafts",
    "sweep_orphaned_media",
    "cleanup_login_tokens",
    "purge_failed_ads",
    "purge_rejected_ads",
    "purge_deleted_ads",
]
```

**Evidence — `.ai/audit/03-db-concurrency/verify_db.py` §A and §L output** *(supports: "reads are not blocked at READ COMMITTED, but a writer blocked for the full hold time is the observed behaviour")*:
```text
isolation_level : read committed
=== L. row lock held by sweep -> bot submit_ad + whole bot stall ===
   unrelated bot ORM read took 0.00s (blocked 14.66s wall)
   submit_ad-shaped lock acquired after 15.05s
```

---

#### DB-009: [MEDIUM] — `copy_ad` has no handling for the single-DRAFT invariant and 500s when the bot holds the draft

| Field | Value |
|---|---|
| **ID** | DB-009 |
| **Title** | `copy_ad` has no handling for the single-DRAFT invariant and 500s when the bot holds the draft |
| **Severity** | MEDIUM |
| **Category** | Cross-process consistency (ISO 25010) |
| **File(s)** | `src/backend/apps/ads/services/copy_service.py:28-68`; `src/backend/apps/ads/models.py:353-357`; `src/telegram_bot/handlers/ad_copy.py:54` |
| **Status** | Open |
| **Problem** | `copy_ad` creates a second `DRAFT` row for the seller while the partial unique constraint `uq_ads_single_draft_per_user` guarantees at most one. It does not delete or reuse the existing draft (unlike `create_draft_ad`, which deliberately does "delete + recreate") and it does not catch the resulting `IntegrityError` — the exception escapes the `transaction.atomic()` block to the caller. The transaction itself is correct: the failed insert is rolled back and no partial copy survives. |
| **Impact** | Any seller who starts a new ad in the Telegram bot and then presses "copy" on the website (or `/copy` in the bot) gets an unhandled `IntegrityError` — a 500 on the web route, an unhandled exception in the bot handler — instead of a clear message. The two features are wired to the same constraint from opposite directions with opposite strategies, and only one of them handles the collision. |
| **Root Cause** | The single-draft invariant is enforced solely by a database constraint with no shared service-level policy for "what happens when a second draft is requested", and only one of the two creators implements the policy. |
| **Recommendation** | Decide the product rule once and apply it in both creators: either "a new draft replaces the current one" (the `create_draft_ad` behaviour — copy should delete the existing DRAFT and its images inside the same transaction, matching the documented "Option D" pattern) or "a second draft is rejected with a message" (copy should catch the `IntegrityError` at a savepoint and raise a domain error the views can render). Add a test that seeds an in-flight DRAFT and asserts the chosen behaviour. |
| **Effort** | S (1 person-day) |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Related Findings** | DB-001 (the sibling creator of the same invariant) |

**Evidence — `src/backend/apps/ads/services/copy_service.py:38-53`** *(supports: "a second DRAFT is inserted with no delete-first step and no `IntegrityError` handling")*:
```python
        new_ad = Ad(
            user_id=seller_user_id,
            category=source.category,
            ...
        )
        new_ad.save()          # <-- violates uq_ads_single_draft_per_user; nothing catches it
```

**Evidence — `src/backend/apps/ads/models.py:353-357`** *(supports: "the invariant is a partial unique constraint on the seller, so the collision is guaranteed when a draft already exists")*:
```python
            models.UniqueConstraint(
                fields=["user_id"],
                name="uq_ads_single_draft_per_user",
                condition=Q(status=AdStatus.DRAFT),
            ),
```

**Evidence — `.ai/audit/03-db-concurrency/verify_db.py` §O output** *(supports: "the `IntegrityError` propagates out of `copy_ad`; the rollback is correct so no partial copy survives")*:
```text
=== O. copy_ad (web /copy) while the bot FSM holds a DRAFT ===
   before copy_ad: drafts = 1
   copy_ad -> IntegrityError: duplicate key value violates unique constraint "uq_ads_single_draft_per_user"
DETAIL:  Key (user_id)=(91) already exists.
   rows after copy_ad -> [(212, 'source listing', 'published'), (213, 'bot fsm draft', 'draft')]
   source ad intact -> True
```

---

### LOW

#### DB-010: [LOW] — The transaction-scoped lock's "released" log fires only on commit, never on the rollback operators need

| Field | Value |
|---|---|
| **ID** | DB-010 |
| **Title** | The transaction-scoped lock's "released" log fires only on commit, never on the rollback operators need |
| **Severity** | LOW |
| **Category** | Observability (ISO 25010) |
| **File(s)** | `src/backend/apps/core/utils/advisory_lock.py:81-87` |
| **Status** | Open |
| **Problem** | The transaction-scoped branch registers its "Released transaction advisory lock N" message with `transaction.on_commit(...)`. PostgreSQL releases `pg_advisory_xact_lock` at both COMMIT and ROLLBACK, but an `on_commit` callback runs only on commit, so the release log line is emitted exactly when nothing went wrong and omitted precisely when the sweep failed. The message that reads "released" is therefore a proxy for "the sweep succeeded", not for "the lock is free". |
| **Impact** | When a scheduled sweep aborts, the operator sees the "Acquired transaction advisory lock N" line with no matching release and cannot tell from the log whether the lock is still held (it is not) or whether the process died holding it (it cannot — that is the point of the xact-scoped variant). The lock's *behaviour* is correct and was verified at runtime; only the diagnostic is misleading. |
| **Root Cause** | `on_commit` was used as a convenient hook for "after the lock is gone" without distinguishing the commit path from the rollback path. |
| **Recommendation** | Wrap the body in a `try/finally` and log the release from the `finally` (or use `connection.run_on_commit` plus an explicit `except` branch), so the release is logged on both paths. The behaviour of the lock itself must not change — the runtime check that the lock is gone after a rollback (§F) must continue to pass. |
| **Effort** | S (< 1 person-day) |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Related Findings** | None |

**Evidence — `src/backend/apps/core/utils/advisory_lock.py:81-87`** *(supports: "the release log is registered on `on_commit` and therefore cannot fire on rollback")*:
```python
        else:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_id])
            logger.info("Acquired transaction advisory lock %s", lock_id)
            transaction.on_commit(
                lambda: logger.info("Released transaction advisory lock %s", lock_id)
            )
            yield
```

**Evidence — `.ai/audit/03-db-concurrency/verify_db.py` §F output** *(supports: "the lock itself is released correctly on rollback — only the log line is missing, so the fix must not alter lock behaviour")*:
```text
=== F. advisory lock released on ROLLBACK (process-crash proxy) ===
   advisory rows after rollback -> 0
```

---

#### DB-011: [LOW] — Five delete/purge sweeps pre-collect media keys inside the lock-held transaction only to log a count

| Field | Value |
|---|---|
| **ID** | DB-011 |
| **Title** | Five delete/purge sweeps pre-collect media keys inside the lock-held transaction only to log a count |
| **Severity** | LOW |
| **Category** | Maintainability (ISO 25010) |
| **File(s)** | `src/backend/apps/core/management/commands/delete_sweep.py:62-81`; `sweep_drafts.py:60-78`; `purge_failed_ads.py:61-80`; `purge_rejected_ads.py`; `purge_deleted_ads.py`; `consent_hard_delete.py:67-97` |
| **Status** | Open |
| **Problem** | Each of these commands builds `storage_keys` — a full scan of `AdImage` rows for every doomed ad, expanding every thumbnail variant — inside the `transaction.atomic()` + advisory-lock block, immediately before the cascade delete. The files themselves are deleted by the `AdImage` `pre_delete` signal via `transaction.on_commit()` (correctly, and documented as such a few lines below). The only consumer of `storage_keys` is `len(storage_keys)` inside the closing `logger.info(...)`. |
| **Impact** | One redundant `AdImage` scan per sweep executed while the sweep's advisory lock and transaction are held, whose sole purpose is a log number, plus a comment ("Collect storage keys for physical media cleanup before ORM cascade") that tells a future maintainer the loop performs the deletion when it does not. On the `consent_hard_delete` path the scan is over every image of every hard-deleted user, which is the largest of the six. |
| **Root Cause** | The pre-collection was written before the `pre_delete` + `on_commit` mechanism existed and was never removed when the mechanism was added; the explanatory comment was added at the deletion site but not at the collection site. |
| **Recommendation** | Delete the `storage_keys` collection from the five (six, with `consent_hard_delete`) commands and drop `len(storage_keys)` from their log lines, or keep the number by counting `AdImage` rows in the same `bulk`-style statement the delete already needs. This is a pure simplification — no behaviour change, no test change. |
| **Effort** | S (< 1 person-day) |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Related Findings** | None |

**Evidence — `src/backend/apps/core/management/commands/delete_sweep.py:62-81`** *(supports: "the key list is computed under the lock and consumed only by a log line")*:
```python
                # Collect storage keys for physical media cleanup before ORM cascade
                ad_ids = list(queryset.values_list("id", flat=True))
                storage_keys = [
                    key
                    for img in AdImage.objects.filter(ad_id__in=ad_ids)
                    for key in img.storage_keys()
                ]
                deleted_count, _ = queryset.delete()

        # Physical media deletion is handled by the AdImage pre_delete signal
        # via transaction.on_commit(), which runs after this transaction commits.
        logger.info(
            "Deleted %d ads with ARCHIVED status older than 60 days. "
            "Removed %d media files.",
            deleted_count,
            len(storage_keys),      # <-- the only consumer
        )
```

## Cross-Finding Analysis

- **Merge candidates:** None. DB-001 and DB-009 both concern `uq_ads_single_draft_per_user`, but they are different code paths with different fixes (a savepoint versus a product decision plus handling), and DB-001 is already cross-referenced from Phase 05's AD-005 — merging would blur that hand-off.
- **Conflicting evidence:** None. The one apparent conflict is DB-002 versus the existing unit test `src/backend/apps/core/tests/test_analytics_service.py:75-100`, which patches `AnalyticsEvent.objects.create` to raise a plain `RuntimeError` *before* any statement reaches the server. That test passes and does not contradict DB-002; it simply cannot reach the failure mode, because a Python-level exception leaves the PostgreSQL transaction usable. The runtime harness uses real server-side errors for exactly that reason.
- **Dependency chains:** DB-008 → DB-004 (shortening the sweep transactions is what makes the bot-wide stall tolerable; setting `lock_timeout` without shortening the holds just converts a stall into a burst of failures). DB-004 → DB-003/DB-005/DB-006 only in the sense that those three are the *producers* of the rows and the locks involved. DB-010 must land after DB-001/DB-004 are fixed, because its fix touches the same `advisory_lock` helper whose rollback behaviour R-05 verifies.

## Remediation Roadmap

| Order | ID | Severity | Effort | Priority | Recommendation (summary) |
|-------|----|----------|--------|----------|--------------------------|
| 1 | DB-001 | CRITICAL | S | P0 | Wrap the draft INSERT in a nested `transaction.atomic()` savepoint so the `IntegrityError` recovery branch runs against a usable transaction |
| 2 | DB-002 | CRITICAL | S | P0 | Make `record_event` failure-safe: savepoint its own INSERT, or move its call sites outside the enclosing transaction |
| 3 | DB-003 | HIGH | M | P1 | Base draft retention on `updated_at` (with a bot heartbeat) instead of `created_at`, and make the expiry message seller-recoverable |
| 4 | DB-004 | HIGH | M | P1 | Add `lock_timeout` / `statement_timeout` and a bounded `OperationalError` retry so one blocked row cannot stall the whole bot |
| 5 | DB-008 | MEDIUM | M | P2 | Commit `archive_sweep` / `recompute_normalized_prices` per batch so row locks release promptly |
| 6 | DB-005 | MEDIUM | M | P1 | Re-check `AdImage` reference inside a short transaction before unlinking, and keep new files in a sweep-exempt directory until their row commits |
| 7 | DB-006 | MEDIUM | S | P2 | Apply `select_for_update().order_by("pk")` + a re-validating delete to the five remaining destructive sweeps |
| 8 | DB-009 | MEDIUM | S | P2 | Give `copy_ad` the same single-draft policy (delete-and-recreate, or a caught domain error) |
| 9 | DB-007 | MEDIUM | M | P2 | Take `ALERT_DELIVERY_TASK` in `deliver_immediate_alerts` and record the notification only after a successful send |
| 10 | DB-011 | LOW | S | P2 | Remove the `storage_keys` pre-collection and the misleading comment from the six sweep commands |
| 11 | DB-010 | LOW | S | P2 | Log the advisory-lock release from a `finally` so it also appears on rollback |

## Rollout Safety

| ID | Risk | Backward-compatible? | Test gap (must cover) |
|----|------|----------------------|-----------------------|
| DB-001 | Med — the retry path is currently unreachable, so nothing depends on its broken behaviour; but the fix changes a hot bot path | Yes | No test forces `uq_ads_single_draft_per_user` to fire in `create_draft_ad`; add one asserting a draft is returned |
| DB-002 | Med — savepointing `record_event` changes when constraint errors surface (earlier, and as a logged warning instead of a swallowed `None`) | Yes | `test_analytics_service.py` only mocks a Python-level `RuntimeError`; add a case with a real server-side error asserting the caller's transaction still commits |
| DB-003 | High — changes retention semantics; a wrong `updated_at` choice either reaps live drafts or keeps junk forever | Yes | No test exercises a long dialog across the sweep boundary; add one that back-dates `updated_at` and asserts the draft survives |
| DB-004 | Med — a `lock_timeout` converts hangs into errors, so callers must handle the new exception path or they surface as 500s | Yes | No test asserts a bounded wait; add one that holds a row lock and asserts the bot-side call fails fast rather than hanging |
| DB-005 | Med — re-checking before unlink can skip a file that a racing insert just claimed, deferring it to the next hourly run | Yes | No test covers "orphan file whose `AdImage` row appears during the sweep"; add one |
| DB-006 | Low — locks make the destructive sweeps wait on live writers; with a long hold (DB-008) this could serialise badly until the timeouts land | Yes | `test_transition_concurrency.py` and `test_edit_views_locking.py` cover the *locked* direction only; add the sweep-vs-reactivate direction |
| DB-007 | Low — taking the shared lock serialises the two alert writers; must not deadlock with `send_alerts`, which holds it across network-free work only | Yes | `test_alert_query.py` covers idempotency of a single writer; add a two-writer case |
| DB-008 | Med — batching changes the all-or-nothing guarantee of a sweep: a mid-sweep failure now leaves earlier batches applied | Yes | `test_sweep_archive.py` asserts the lock structure, not batch boundaries; add a failure-in-batch-N assertion |
| DB-009 | Low — a behavioural decision (replace vs reject) may change what sellers see | Depends on the chosen rule | `test_copy_ad.py` documents the constraint; needs a case with a pre-existing DRAFT asserting the chosen rule |
| DB-010 | Low — log-only change; must not alter lock acquisition or release | Yes | `test_advisory_lock_release_log.py` asserts the `on_commit` registration — it must be updated to assert the `finally` path instead |
| DB-011 | Low — removal only; the log line loses a number | Yes | `test_sweep_delete.py` asserts the deletion path, not the key collection; no new test needed |

## Appendices

### Appendix A — Runtime verification harness

**Artifacts (both re-runnable, both read-only w.r.t. production code):**

| File | Role |
|---|---|
| `.ai/audit/03-db-concurrency/verify_db.py` | Runtime harness — sections A–O below |
| `.ai/audit/03-db-concurrency/scan_async_orm.py` | Static gate for check (c) — no bare ORM in `async def` |
| `.ai/audit/03-db-concurrency/verification-output.txt` | Full captured output of the last successful harness run (exit 0) |

Sections and what each proves:

| Section | What it proves | Result |
|---|---|---|
| A | Effective `CONN_MAX_AGE`, `OPTIONS`, isolation level, `max_connections` | `CONN_MAX_AGE=0`, `prepare_threshold=None`, `read committed`, `max_connections=100` |
| B / H2 | The `create_draft_ad` recovery branch and a 6-thread race | `TransactionManagementError` ×5 of 6 → **DB-001** |
| C / C2 | `record_event` swallowing a deferred FK violation and an immediate `DataError` | COMMIT-time `IntegrityError`; `InternalError: current transaction is aborted` → **DB-002** |
| D / E / F | Advisory-lock mutual exclusion, `pg_locks` visibility, release on rollback | 2.01 s / 4.02 s serialisation; 1 row held → 0 after commit and rollback |
| G | 4-way concurrent `LoginToken` claim | exactly 1 claim (PASS) |
| H | Concurrent `create_draft_ad` through the real bot coroutine | serialised by asgiref's single `thread_sensitive` worker (PASS) |
| I | 16-thread connection churn | 0 errors, 0 idle-in-transaction, 3 connections (PASS) |
| J | `sweep_drafts` vs an in-flight dialog | draft destroyed, `submit_ad` re-fetch → `Ad.DoesNotExist` → **DB-003** |
| K | `delete_sweep` vs a concurrent reactivation | reactivation committed then row deleted anyway → **DB-006** |
| L | A row lock held by a sweep | 15.05 s unbounded wait; unrelated bot read stalled 14.66 s of wall time → **DB-004** |
| M | `sweep_orphaned_media` vs an in-flight `submit_ad` file promotion | file deleted, `AdImage` row committed pointing at nothing → **DB-005** |
| N | Immediate-alert writer vs daily `send_alerts` writer | both select the same `(saved_search, ad)` → **DB-007** |
| O | `copy_ad` with a pre-existing DRAFT | `IntegrityError` propagates, rollback correct → **DB-009** |

*.supports the claim: "every finding in this report is reproducible by re-running this
single script; the sentinel rows it creates are removed by the closing `cleanup` block and
were confirmed absent afterwards (0 `audit%` ads, 0 `audit%` users, 0 advisory locks in
`pg_locks`). Both artefacts live beside this report and are also retained verbatim in
`verification-output.txt`."*

Reproduce:

```powershell
$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'
$dc run --rm --no-deps test python /app/.ai/audit/03-db-concurrency/verify_db.py
uv run python .ai/audit/03-db-concurrency/scan_async_orm.py   # expect TOTAL=0, exit 0
```












