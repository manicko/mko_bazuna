# Phase 03 Validate Report — Database & Concurrency Consistency

**Source Findings:** `.ai/audit/03-db-concurrency/findings.md`
**Validated by:** validator
**Date:** 2026-07-20

---

## Findings

### DB-001: Transaction-scoped advisory lock is NOT held for the whole sweep (released between count and mutate)

| Field | Value |
|-------|-------|
| **ID** | DB-001 |
| **Severity** | HIGH |
| **Type** | `SPEC-DEVIATION` |
| **Affected Modules** | `src/backend/apps/core/utils/advisory_lock.py`, `archive_sweep.py`, `delete_sweep.py`, `sweep_drafts.py`, `purge_failed_ads.py`, `purge_rejected_ads.py`, `consent_hard_delete.py`, `cleanup_login_tokens.py` |
| **Classification** | mandatory |

**Description:** `advisory_lock(..., session=False)` uses `pg_advisory_xact_lock` (`advisory_lock.py:46`). This lock is released automatically at the **end of the current transaction**. Django's `call_command` runs the command body in **autocommit** mode (no `transaction.atomic` is present anywhere in the codebase — grep for `transaction.atomic`/`ATOMIC_REQUESTS` returns zero matches). Every sweep command therefore issues its operations as separate autocommit statements.

**Evidence Verified:**
- `advisory_lock.py:46` → `cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_id])` (transaction-scoped) ✓
- `archive_sweep.py:49` `queryset.count()` and `:60` `queryset.update(...)` — no `transaction.atomic` wraps them ✓
- Identical structure in all other sweep commands (delete_sweep, sweep_drafts, purge_failed_ads, purge_rejected_ads, consent_hard_delete, cleanup_login_tokens) ✓
- `grep "transaction.atomic"` across `src/**` → 0 matches ✓

**Consequence:** Two simultaneously-triggered instances of the same sweep can interleave between `count()` and the destructive `delete()`/`update()`. The second instance observes the same candidate set and both proceed — defeating the idempotency/serialization guarantee the lock is documented to provide.

**Recommendation:** Wrap the body of each sweep command — the code inside the `with advisory_lock(..., session=False):` block from the first queryset operation to the final `count()`/`update()`/`delete()` — in `transaction.atomic()` so the `pg_advisory_xact_lock` spans the entire count→mutate sequence without autocommit releases. *(Alternative: use session-scoped lock with `session=True`, but this requires explicit unlock calls and is not the minimal fix.)*

*Resolved by research: 2026-07-20*

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Finding is technically correct and architecturally significant. The lock mechanism is sound, but the transaction-scope limitation is violated by the autocommit behavior of Django management commands. This is a spec deviation: code does not match documented lock guarantee.

---

### DB-002: Multi-row domain writes are not atomic — no `transaction.atomic` anywhere

| Field | Value |
|-------|-------|
| **ID** | DB-002 |
| **Severity** | CRITICAL |
| **Type** | `SPEC-DEVIATION` |
| **Affected Modules** | `src/telegram_bot/handlers/ad_create.py` (update_ad_and_moderate), `src/backend/apps/core/management/commands/consent_hard_delete.py` |
| **Classification** | mandatory |

**Description:** The phase requires every multi-row domain write to be wrapped in one transaction boundary with full rollback on failure (§a). No code in the repo uses `transaction.atomic` at all. Several operations perform multiple ORM writes that will partially commit on mid-write failure.

**Evidence Verified:**
- `grep -r "transaction.atomic|ATOMIC_REQUESTS|@transaction"` across `src/**` → 0 matches ✓
- `ad_create.py:548-566` — sequential ORM writes (AdImage.create ×N, ad.save, AnalyticsEvent.create) without atomic block ✓
- `consent_hard_delete.py:65,68,71` — three independent statements (AnalyticsEvent.update, ModeratorActionLog.update, queryset.delete) without atomic wrapper ✓

**Consequence:** On mid-write failure (the CRITICAL condition in the severity taxonomy: "Non-atomic domain write leaving partial data"), `consent_hard_delete` can leave orphaned `AnalyticsEvent`/`ModeratorActionLog` rows still referencing users that were hard-deleted → FK dangling references / audit-history corruption. For `update_ad_and_moderate`, a failure after `AdImage.create` but before `ad.save()` leaves orphaned `AdImage` rows pointing at a still-DRAFT ad, and a failure after `ad.save()` but before analytics event leaves the ad PUBLISHED with no `AD_PUBLISHED` event.

**Recommendation:** Wrap multi-statement write sequences in `transaction.atomic()`: the body of `update_ad_and_moderate`'s inner function, and the mutate section of `consent_hard_delete` (all three statements inside one atomic block). Keep each `atomic()` block as small and focused as possible.

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Finding is technically correct and represents a CRITICAL data-integrity risk. The `consent_hard_delete` path and the bot publish path both have multi-statement writes that are not transactional. This is a spec deviation: code violates the phase requirement §a.

---

### DB-003: `sync_to_async` + `CONN_MAX_AGE=0` → per-call connection churn in the bot

| Field | Value |
|-------|-------|
| **ID** | DB-003 |
| **Severity** | MEDIUM |
| **Type** | `BEST-PRACTICE` |
| **Affected Modules** | `src/telegram_bot/handlers/*.py`, `src/backend/config/settings/base.py` |
| **Classification** | advisory |

**Description:** The bot reaches the sync ORM exclusively through `sync_to_async`. Because `CONN_MAX_AGE=0` (base.py:118/130) yields a fresh connection per request/operation, **every** `sync_to_async` call that touches the DB opens and closes its own PostgreSQL connection. This churn is acceptable for correctness but amplifies connection acquisition under bursty bot traffic, increasing pressure on the shared DB connection budget.

**Evidence Verified:**
- `base.py:118` and `:130` → `CONN_MAX_AGE = 0` (per-process fresh connection per request) ✓
- Bot handlers wrap each ORM helper in `@sync_to_async` (`ad_create.py:361-498`, `login.py:100-158`, `contact.py:108-186`) — many fine-grained calls per handler ✓
- `asgiref.sync.sync_to_async` default executor is a `ThreadPoolExecutor` ✓

**Consequence:** Under high bot load, the async process opens/closes connections at a high rate, raising the risk of exhausting the shared DB's `max_connections` (which cascades to the web process). Not a correctness bug, but an operational reliability factor.

**Recommendation:** Coalesce adjacent ORM operations inside a single `sync_to_async` call rather than one wrapper per statement (the bot already does this for `update_ad_and_moderate`; apply the same pattern to login/contact flows). Do **not** raise `CONN_MAX_AGE` in the bot, as that would reintroduce the pooler-prepared-statement incompatibility risk.

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Finding is correct and represents a measurable operational risk. The recommendation is conservative and follows existing patterns in the codebase. ROI is medium-high for a production deployment.

---

### DB-004: `User.objects.get_or_create` in bot login is a read-modify-write race

| Field | Value |
|-------|-------|
| **ID** | DB-004 |
| **Severity** | LOW |
| **Type** | `BEST-PRACTICE` |
| **Affected Modules** | `src/telegram_bot/handlers/login.py` (`get_or_create_user`, lines 129-158) |
| **Classification** | advisory |

**Description:** `get_or_create_user` (`login.py:142`) uses `User.objects.get_or_create(telegram_id=...)`. Django's `get_or_create` performs a SELECT then an INSERT inside a (default) transaction; under concurrent identical logins from the same `telegram_id` it can raise `IntegrityError` on the duplicate INSERT (because `telegram_id` is unique). The exception is currently unhandled.

**Evidence Verified:**
- `login.py:142` `User.objects.get_or_create(telegram_id=telegram_id, defaults={...})` ✓
- No surrounding `try/except IntegrityError` / retry around it ✓
- `login.py:114-119` `LoginToken.objects.filter(...).update(...)` — atomic claim pattern done correctly ✓

**Consequence:** Two near-simultaneous `/start` logins for a brand-new user can hit the `IntegrityError` branch and surface as an unhandled error to the user (lost login attempt), rather than a clean idempotent grab. Low likelihood and low blast radius.

**Recommendation:** Wrap `_get_or_create()` in `transaction.atomic()` and on `IntegrityError`, perform a `User.objects.get(telegram_id=telegram_id)` to return the existing user — mirroring the retry-on-conflict pattern used in similar atomic claim logic elsewhere in the codebase.

*Resolved by research: 2026-07-20*

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Finding is technically correct. While the risk is low, the fix aligns with existing correct patterns in the codebase (`claim_login_token`). This is a valid best-practice finding.

---

### DB-005: Bot `update_ad_and_moderate` mutates shared `Ad` rows without row-level locking under concurrent web reads

| Field | Value |
|-------|-------|
| **ID** | DB-005 |
| **Severity** | LOW |
| **Type** | `BEST-PRACTICE` |
| **Affected Modules** | `src/telegram_bot/handlers/ad_create.py`, `src/backend/apps/search/views/search.py`, `src/backend/apps/core/services/contact.py` |
| **Classification** | advisory |

**Description:** The bot publishes/edits an `Ad` while the web process reads the same `Ad` rows. Both processes use READ COMMITTED isolation. The web only ever filters on `status=PUBLISHED`, so a mid-edit ad (still DRAFT or ON_MODERATION_FAILED) is naturally excluded — no corruption occurs. However, the bot's multi-statement edit (DB-002) is not atomic.

**Evidence Verified:**
- `search.py:42` reads `Ad.objects.filter(status=AdStatus.PUBLISHED)` ✓
- `contact.py:81` reads `Ad.objects.select_related("user").get(id=ad_id)` ✓
- `ad_create.py:498-566` edits the same `Ad` across multiple statements (see DB-002) ✓
- No `select_for_update()` / explicit locking on the contested `Ad` row ✓

**Consequence:** No data corruption today (status filter isolates web readers), but the consistency of `search_vector` vs. published images during a non-atomic bot edit is best-effort. Acceptable under current load; documented as forward-looking.

**Recommendation:** Once DB-002 is fixed (atomic edit), the bot edit becomes a single transaction and web readers under READ COMMITTED will only ever see the fully-committed state — this finding is largely resolved as a side effect.

> **Validation Note:**
> - **Action:** merged into DB-002
> - **Detail:** Root cause is identical to DB-002 (lack of atomicity). Once DB-002 is resolved with `transaction.atomic()`, concurrent consistency is guaranteed by PostgreSQL READ COMMITTED semantics. No separate locking is needed.
> - **See also:** DB-002

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 4 | DB-001, DB-002, DB-003, DB-004 |
| Reclassified | 0 | — |
| Merged | 1 | DB-005 → DB-002 |
| Rejected | 0 | — |

### Merged Findings

| Original ID | Merged Into | Rationale |
|-------------|-----------|----------|
| DB-005 | DB-002 | Same root cause: non-atomic multi-statement writes. Once DB-002 is fixed with `transaction.atomic()`, DB-005's consistency concern is resolved as a side effect. |

---

## Rollout Analysis

### Risks & Dependencies

1. **DB-001 and DB-002 are independent fixes** — neither depends on the other, but both involve transaction boundaries.
2. **Sweep commands share the same advisory-lock utility** — any fix (atomic wrapper or session-scoped lock) applies uniformly.
3. **Bot atomicity affects the shared Ad entity** — must be tested with concurrent web reads to verify consistency.

### Sequencing Concerns

1. **Recommended order:**
   - Fix DB-002 first (bot atomicity) — smaller scope, critical for data integrity
   - Fix DB-001 second (sweep atomicity) — ensures sweep operations don't double-process under concurrent triggers
   - DB-003 and DB-004 are independent and can follow

---

## Warnings

- **Architectural risk:** The advisory lock docstring (`advisory_lock.py:1-7`) states the lock is "transaction-scoped … safe under PgBouncer" and implies it is held for the whole locked operation. However, without `transaction.atomic()` wrapping the sweep bodies, the lock only spans per-statement under autocommit. Documentation should clarify this limitation.
- **Rollout risk:** Adding `transaction.atomic()` to long-running sweeps (consent_hard_delete, archive_sweep) may increase row-lock duration. Monitor for lock contention under production load.
- **Dependency risk:** None detected — these changes are localized to the sweep commands and bot handlers.

---

## Required Fixes

| ID | Description |
|----|-------------|
| DB-001 | Wrap the body of each sweep command — the code inside `with advisory_lock(..., session=False):` — in `transaction.atomic()` so `pg_advisory_xact_lock` spans count→mutate. |
| DB-002 | Wrap `update_ad_and_moderate`'s inner function and `consent_hard_delete`'s mutate section in `transaction.atomic()`. |

---

## Advisory Recommendations

| ID | Description |
|----|-------------|
| DB-003 | Coalesce ORM operations inside single `sync_to_async` wrappers in login/contact flows. |
| DB-004 | Wrap `_get_or_create()` in `transaction.atomic()`; on `IntegrityError`, re-`get(telegram_id)` to return existing user. |

---

## Doc Updates Needed

- `advisory_lock.py` docstring (lines 1-7) should clarify: "Transaction-scoped locks release on commit/rollback. For long-running operations, wrap the operation body in `transaction.atomic()` or use session-scoped locks."
- All sweep command docstrings (e.g., `archive_sweep.py:5`, `delete_sweep.py:5`, etc.) should be updated to remove the implication that the lock guarantees whole-sweep atomicity without explicit transaction wrapping.