---
name: audit-findings
description: Phase 03 — Database & Concurrency Consistency findings
agent: audit-executor
alwaysApply: false
---

# Phase 03 Audit Findings — Database & Concurrency Consistency

**Executor:** audit-executor
**Template:** .kilo/commands/audit/phases/03-audit-db-concurrency.md
**Status:** complete
**Validated:** no

> Mode: problems-only. Only real deviations/bugs/risks with evidence are listed.
> Runtime note: PostgreSQL 18 is reachable (port 5432 open), but the pytest suite
> hangs on test-DB creation/migration in this environment (>120s), so R4/R6 runtime
> concurrency simulation could not be executed here. Findings below are supported by
> static evidence (exact source lines) and documented PostgreSQL semantics, which is
> admissible where the gap is structural and provable from code.

---

## Findings

### DB-001: Transaction-scoped advisory lock is NOT held for the whole sweep (released between count and mutate)

| Field | Value |
|-------|-------|
| **ID** | DB-001 |
| **Severity** | HIGH |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | `src/backend/apps/core/utils/advisory_lock.py`, all sweep commands (`archive_sweep.py`, `delete_sweep.py`, `sweep_drafts.py`, `purge_failed_ads.py`, `purge_rejected_ads.py`, `consent_hard_delete.py`) |
| **Classification** | mandatory |

**Description:** `advisory_lock(..., session=False)` uses `pg_advisory_xact_lock`
(`advisory_lock.py:46`). This lock is released automatically at the **end of the
current transaction**. Django's `call_command` runs the command body in **autocommit**
mode (no `transaction.atomic` is present anywhere in the codebase — grep for
`transaction.atomic`/`ATOMIC_REQUESTS` returns zero matches). Every sweep command
therefore issues its operations as separate autocommit statements:

```
with advisory_lock(LOCK_ID):          # opens txn A -> acquires xact lock
    count = queryset.count()          # txn A commits here -> LOCK RELEASED
    if dry_run: return
    queryset.delete() / .update()     # opens txn B -> re-acquires xact lock
```

The advisory lock is acquired, released (at the `count()` commit), and re-acquired
(at the `delete()`/`update()`). The phase requirement "Held for whole sweep"
(§d) is violated: a second concurrent sweep can acquire the same lock between the
first sweep's `count()` and its `delete()`, because the lock is not held across the
gap.

**Evidence:**
- `advisory_lock.py:46` → `cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_id])` (transaction-scoped).
- `archive_sweep.py:40` opens the lock, `:50` `queryset.count()` (separate statement), `:60` `queryset.update(...)` (separate statement) — no `transaction.atomic` wraps them.
- Identical structure in `delete_sweep.py:41/51/61`, `sweep_drafts.py:40/49/59`, `purge_failed_ads.py:40/50/60`, `purge_rejected_ads.py:41/51/62`, `consent_hard_delete.py:43/53/66-72`.
- `src/backend/config/settings/*.py`: no `ATOMIC_REQUESTS = True`; `grep "transaction.atomic"` across repo → 0 matches.
- PostgreSQL semantics: `pg_advisory_xact_lock` is released on transaction end; under autocommit each statement is its own transaction (documented behavior).

**Consequence:** Two simultaneously-triggered instances of the same sweep (the exact
edge case in the phase: "Two instances both trigger a sweep simultaneously") can
interleave between `count()` and the destructive `delete()`/`update()`. The second
instance observes the same candidate set and both proceed — defeating the
idempotency/serialization guarantee the lock is documented to provide. Data double-processing
or, in `consent_hard_delete`, contention over the same user set.

**Recommendation:** Wrap each sweep command body in `transaction.atomic()` (or set
`ATOMIC_REQUESTS` for the management-command path) so the transaction-scoped lock is
acquired once and held across `count()` → `delete()`/`update()`. Alternatively, switch
to a `session`-scoped lock (`advisory_lock(session=True)`) held for the whole `with`
block. Either guarantees the lock spans the entire sweep.

---

### DB-002: Multi-row domain writes are not atomic — no `transaction.atomic` anywhere

| Field | Value |
|-------|-------|
| **ID** | DB-002 |
| **Severity** | CRITICAL |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | `src/telegram_bot/handlers/ad_create.py` (`update_ad_and_moderate`), `src/backend/apps/core/management/commands/consent_hard_delete.py`, `src/backend/apps/core/services/contact.py`, `src/backend/apps/search/views/search.py` |
| **Classification** | mandatory |

**Description:** The phase requires every multi-row domain write to be wrapped in one
transaction boundary with full rollback on failure (§a). No code in the repo uses
`transaction.atomic` at all. Several operations perform multiple ORM writes that will
partially commit if one fails:

1. **Bot publish path** `ad_create.py:498-568` — inside a single `sync_to_async`
   function it runs: `AdImage.objects.create()` ×N (lines 548-554), then
   `ad.save()` (561), then `AnalyticsEvent.objects.create()` (564-566). Under
   autocommit each is a separate commit. A failure after `AdImage.create` but before
   `ad.save()` leaves **orphaned `AdImage` rows pointing at a still-DRAFT ad**, and a
   failure after `ad.save()` but before the analytics event leaves the ad PUBLISHED
   with no `AD_PUBLISHED` event (silent analytics loss / inconsistent state).
2. **`consent_hard_delete.py:66-72`** — three independent statements:
   `AnalyticsEvent.update(user_id=None)` (66), `ModeratorActionLog.update(user_id=None)`
   (69), `queryset.delete()` (72). A crash between step 1 and step 3 leaves orphaned
   `AnalyticsEvent`/`ModeratorActionLog` rows still referencing users that were
   hard-deleted → FK dangling references / audit-history corruption.
3. **Web `search.py:46-49`** records a `SEARCH_PERFORMED` event on the hot read path
   with no surrounding transaction (lower severity, but same non-atomic pattern).

**Evidence:**
- `grep -r "transaction.atomic|ATOMIC_REQUESTS|@transaction"` across `src/**` → 0 matches.
- `ad_create.py:548-566` — sequential ORM writes with no atomic block.
- `consent_hard_delete.py:66,69,72` — three separate write statements.
- `contact.py:124` / `search.py:46` — single writes lacking a transactional context
  (acceptable individually, listed to show the systemic absence of atomic discipline).

**Consequence:** Partial commits / orphaned rows on mid-write failure (the CRITICAL
condition in the severity taxonomy: "Non-atomic domain write leaving partial data").
Data-integrity loss on the ad-publish and consent-erasure paths — the two most
sensitive write paths in the system.

**Recommendation:** Wrap multi-statement write sequences in `transaction.atomic()`:
the body of `update_ad_and_moderate`'s inner function, and the mutate section of
`consent_hard_delete` (all three statements inside one atomic block). Keep each
`atomic()` block as small and focused as possible to avoid holding row locks longer
than necessary.

---

### DB-003: `sync_to_async` + `CONN_MAX_AGE=0` → per-call connection churn in the bot

| Field | Value |
|-------|-------|
| **ID** | DB-003 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/telegram_bot/handlers/*.py`, `src/backend/config/settings/base.py` |
| **Classification** | advisory |

**Description:** The bot reaches the sync ORM exclusively through `sync_to_async`
(e.g. `ad_create.py:363,376,387,...`, `login.py:109,140`, `contact.py:128,170`).
`asgiref.sync.sync_to_async` (default `thread_sensitive=True`) executes the wrapped
function in a threadpool. Because `CONN_MAX_AGE=0` (base.py:118/130) yields a fresh
connection per request/operation, **every** `sync_to_async` call that touches the DB
opens and closes its own PostgreSQL connection. This churn is acceptable for
correctness but amplifies connection acquisition under bursty bot traffic, increasing
pressure on the shared DB connection budget (cross-cutting concern: "two processes
competing for the same DB").

**Evidence:**
- `base.py:118` and `:130` → `CONN_MAX_AGE = 0` (per-process fresh connection per request).
- Bot handlers wrap each ORM helper in `@sync_to_async` (`ad_create.py:361-498`,
  `login.py:100-158`, `contact.py:108-186`) — many fine-grained calls per handler.
- `asgiref` `sync_to_async` default executor is a `ThreadPoolExecutor`; each invocation
  re-acquires a connection from the pool when `CONN_MAX_AGE=0`.

**Consequence:** Under high bot load, the async process opens/closes connections at a
high rate, raising the risk of exhausting the shared DB's `max_connections` (which
cascades to the web process — the exact cross-process exhaustion risk called out in the
phase). Not a correctness bug, but an operational reliability factor.

**Recommendation:** Coalesce adjacent ORM operations inside a single `sync_to_async`
call rather than one wrapper per statement (the bot already does this for
`update_ad_and_moderate`; apply the same pattern to login/contact flows). This reduces
connection turnover without changing the async/sync boundary contract. Do **not** raise
`CONN_MAX_AGE` in the bot, as that would reintroduce the pooler-prepared-statement
incompatibility risk (Phase 02 owns that value).

---

### DB-004: `User.objects.get_or_create` in bot login is a read-modify-write race

| Field | Value |
|-------|-------|
| **ID** | DB-004 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/telegram_bot/handlers/login.py` (`get_or_create_user`, lines 129-158) |
| **Classification** | advisory |

**Description:** `get_or_create_user` (`login.py:140-156`) uses
`User.objects.get_or_create(telegram_id=...)`. Django's `get_or_create` performs a
SELECT then an INSERT inside a (default) transaction; under concurrent identical logins
from the same `telegram_id` it can raise `IntegrityError` on the duplicate INSERT
(because `telegram_id` is presumably unique). The exception is currently unhandled in
the caller path. `claim_login_token` (lines 109-126) is correctly written as an atomic
single-statement `UPDATE … .update()` (good), but `get_or_create_user` is not
equivalently race-safe.

**Evidence:**
- `login.py:142` `User.objects.get_or_create(telegram_id=telegram_id, defaults={...})`.
- No surrounding `try/except IntegrityError` / retry around it.
- Contrast: `login.py:114-119` `LoginToken.objects.filter(...).update(...)` — atomic
  claim pattern done correctly.

**Consequence:** Two near-simultaneous `/start` logins for a brand-new user can hit the
`IntegrityError` branch and surface as an unhandled error to the user (lost login
attempt), rather than a clean idempotent grab. Low likelihood (same user double-starting)
and low blast radius, but it is the classic unguarded read-modify-write the phase flags
in §b.

**Recommendation:** Adopt the same atomic single-statement claim pattern used in
`claim_login_token`, or wrap `get_or_create` in `transaction.atomic()` with an
`IntegrityError` retry/get on conflict. Low effort; aligns the login path with the
already-correct token-claim path.

---

### DB-005: Bot `update_ad_and_moderate` mutates shared `Ad` rows without row-level locking under concurrent web reads

| Field | Value |
|-------|-------|
| **ID** | DB-005 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/telegram_bot/handlers/ad_create.py`, `src/backend/apps/search/views/search.py`, `src/backend/apps/core/services/contact.py` |
| **Classification** | advisory |

**Description:** The bot publishes/edits an `Ad` (status DRAFT→PUBLISHED, search_vector
recomputed by trigger) while the web process reads the same `Ad` rows in
`search.py:42` (`filter(status=PUBLISHED)`) and `contact.py:81`
(`get_seller_for_contact`). Both processes use the default READ COMMITTED isolation.
The web only ever filters on `status=PUBLISHED`, so a mid-edit ad (still DRAFT or
ON_MODERATION_FAILED) is naturally excluded — no corruption occurs. However, the
phase's "Web/bot non-corruption" check (§b) is satisfied only by convention (status
filtering), not by explicit locking, and the bot's multi-statement edit (DB-002) is not
atomic, so a web reader could briefly observe an ad whose `search_vector`/images are
inconsistent mid-write.

**Evidence:**
- `search.py:42` reads `Ad.objects.filter(status=AdStatus.PUBLISHED)`.
- `contact.py:81` reads `Ad.objects.select_related("user").get(id=ad_id)`.
- `ad_create.py:498-566` edits the same `Ad` across multiple statements (see DB-002).
- No `select_for_update()` / explicit locking on the contested `Ad` row anywhere.

**Consequence:** No data corruption today (status filter isolates web readers), but the
consistency of `search_vector` vs. published images during a non-atomic bot edit is
best-effort. Acceptable under current load; documented as forward-looking.

**Recommendation:** Once DB-002 is fixed (atomic edit), the bot edit becomes a single
transaction and web readers under READ COMMITTED will only ever see the fully-committed
state — this finding is largely resolved as a side effect. No separate locking needed
for the current read pattern; revisit only if web writes to the same `Ad` are added.

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1 |
| HIGH | 1 |
| MEDIUM | 1 |
| LOW | 2 |

## Mandatory Fixes

- **DB-001** (HIGH): transaction-scoped advisory lock released between `count()` and
  `delete()`/`update()` under autocommit — wrap sweep bodies in `transaction.atomic()`
  or use a session-scoped lock so the lock spans the whole sweep.
- **DB-002** (CRITICAL): no `transaction.atomic` anywhere — multi-row writes in the bot
  publish path and `consent_hard_delete` can partially commit, leaving orphaned
  `AdImage` rows and dangling analytics/moderation references.

## Advisory Recommendations

- **DB-003** (MEDIUM): coalesce ORM calls inside single `sync_to_async` wrappers to
  reduce per-call connection churn under `CONN_MAX_AGE=0`.
- **DB-004** (LOW): make bot `get_or_create_user` race-safe (atomic claim or
  IntegrityError retry) to match the already-correct `claim_login_token` pattern.
- **DB-005** (LOW): web/bot consistency currently relies on status filtering, not
  locking; largely resolved once DB-002 atomicity is in place.

## Doc Updates Needed

- `[DOC-UPDATE]` `apps/core/utils/advisory_lock.py` docstring (lines 1-7) states the
  lock is "transaction-scoped … safe under PgBouncer" and implies it is held for the
  whole locked operation. The source comments on every sweep command ("Uses advisory
  lock N for idempotent, safe concurrent execution") overstate the guarantee given the
  autocommit gap in DB-001. Docs should be corrected to state the lock only serializes
  at the per-statement granularity unless the command body is wrapped in
  `transaction.atomic()`.
