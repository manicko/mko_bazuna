---
name: 03-db-concurrency
status: draft
validated: no
executor: auditor
problems-only: true
---

# Phase 03 — Database & Concurrency Consistency

## Purpose

Reusable handbook for auditing **database concurrency and transaction consistency** of a
dual-process Django system (a synchronous web process + an asynchronous bot process) that
share **one PostgreSQL database**.

Structural context (do not re-audit here — see Phases 01/02):
- Each process owns its **own connection pool**; per-process **connection-max-age = 0**
  yields a fresh connection per request (Phase 02 owns the *value*; this phase assumes it).
- An optional **transaction-mode external pooler** may sit in front of the DB and requires
  **prepared-statement use disabled**.
- The **synchronous ORM** is reached from the async bot only through an **async/sync bridge
  wrapper**.
- **Multi-row domain writes** must be atomic.
- **Scheduled sweep jobs** must serialize via a **transaction-scoped advisory lock**.

This phase audits **CONCURRENCY**, **TRANSACTION ATOMICITY**, **ADVISORY-LOCK correctness**,
and **CROSS-PROCESS CONSISTENCY** — not process startup (Phase 01) or config values (Phase 02).

## Output Mode — problems-only

- Report **only real deviations, bugs, or risks** with **runtime evidence**.
- **Omit passing rows / passing checks entirely.**
- If nothing is found, emit a single line: **`No problems found in this phase.`**
- Every finding MUST include: **runtime evidence** + **exact consequence**.

## Scope Boundaries (do NOT duplicate)

| Do NOT re-audit (other phase) | Belongs to |
|---|---|
| Migration-once, process startup, per-process pool *existence*, async/sync boundary in the broad | Phase 01 |
| connection-max-age *value*, external pooler *configuration* | Phase 02 |
| Concurrency, atomicity, advisory-lock behavior, cross-process consistency | **This phase** |

---

## Architectural Layers

| Layer | Zone of responsibility | Key risks |
|---|---|---|
| Persistence / ORM layer | Shared single source of truth; uniform ORM access | Divergent ORM access patterns; raw SQL bypassing ORM guarantees |
| Connection management | Per-process pool, connection-max-age=0, pooler compatibility | Connection exhaustion; prepared-statement errors under transaction-mode pooler |
| Transaction-boundary zone | Atomic multi-row domain writes | Partial commits; orphaned rows on mid-write failure |
| Async/sync bridge zone | ORM reached from the async event loop | Event-loop blocking; unguarded synchronous ORM in async context |
| Advisory-lock / scheduled-job zone | Single-instance sweeps via transaction-scoped lock | Concurrent sweeps; lock not held for whole sweep |
| Cross-process consistency zone | Shared domain entities touched by web + bot | Lost updates; read-modify-write race conditions |

---

## Discovery Stage (map roles, never names)

1. **Persistence / ORM mapping** — locate connection-lifecycle config, shared ORM access
   patterns, the advisory-lock ID scheme, and transaction boundaries around multi-row
   domain writes.
2. **Connection-pool mapping** — per-process pool config, presence/mode of an external
   pooler, and the prepared-statement compatibility setting.
3. **Transaction-boundary mapping** — identify domain-write operations that span multiple
   rows; verify explicit atomic demarcation; find any partial-commit patterns.
4. **Async/sync bridge mapping** — locate the bridge wrapper; verify **all** ORM access from
   async is wrapped; find any direct synchronous ORM inside async context.
5. **Advisory-lock / sweep mapping** — trace scheduled-sweep jobs; verify the lock is
   acquired for the *whole* sweep; confirm dry-run mode does not bypass the lock.
6. **Cross-process contention mapping** — identify shared domain entities (e.g. login
   tokens, ad rows) accessed by both processes; map isolation for concurrent
   read-modify-write.

---

## Mandatory Runtime Verification (run BEFORE the checklist; capture evidence)

| ID | Verification | Method | Evidence to capture |
|---|---|---|---|
| R1 | Connection-exhaustion simulation | Drive both processes concurrently; watch connection acquisition/release via DB activity queries | No connection held beyond request lifecycle; DB max-connections not exceeded; no leak from the async process after a prolonged run |
| R2 | Per-process connection-max-age value | Inspect effective runtime value in every environment | Value is **0** (not None / not positive); prepared-statement use is **disabled** when a transaction-mode pooler is present |
| R3 | Async/sync boundary type + static check | Type-check bot handlers; grep for ORM calls in async context lacking the bridge wrapper | List of unwrapped ORM calls; any blocking IO flagged in async context |
| R4 | Concurrency / transaction tests | Simulate concurrent writes to one shared row from both processes; run duplicate-sweep attempt | Lost-update prevented (row-level lock or atomic single-statement UPDATE); advisory lock blocks the duplicate sweep |
| R5 | Orphaned connections / locks | Inspect DB for idle leaked connections and ungranted advisory locks after normal operation | No leaked idle connections; no dangling locks; lock released on process crash |
| R6 | Linter + type-check + focused test-suite | Run over the persistence/concurrency surface | Command output; failures on the concurrency surface |

> Findings without R1–R6 evidence are not admissible under `problems-only`.

---

## Audit Dimensions

### (a) Transaction atomicity

| Check | Description |
|---|---|
| Single transaction | Every multi-row domain write is wrapped in one transaction boundary |
| No intermediate commits | No commit occurs partway through a multi-row write |
| Full rollback on failure | Partial failure rolls back entirely — no orphaned draft / images / events |

**Evidence required:** runtime trace of a mid-write failure showing complete rollback (zero
orphaned rows), plus transaction-boundary demarcation around each multi-row write.

### (b) Lost-update & race prevention

| Check | Description |
|---|---|
| Contested-row protection | Contested shared rows use row-level locking or an atomic single-statement UPDATE |
| No unguarded read-modify-write | No read-modify-write without locking — especially atomic token-claim and concurrent ad edits |
| Web/bot non-corruption | Web reads and bot writes do not corrupt each other |

**Evidence required:** concurrent-process simulation showing the second writer serializes or
fails cleanly; token-claim exercised twice concurrently yields exactly one claim.

### (c) Async/sync bridge correctness

| Check | Description |
|---|---|
| All ORM wrapped | Every ORM call from async goes through the bridge wrapper |
| No direct sync ORM in async | No synchronous ORM call executes directly in an async handler |
| No blocking IO in async | No blocking IO in async context |
| No unintended multi-tx spans | Bridge invocations do not accidentally span multiple DB transactions |

**Evidence required:** static + type-check output listing violations; runtime trace showing a
single bridge invocation maps to a single transaction.

### (d) Advisory-lock / scheduled-sweep safety

| Check | Description |
|---|---|
| Acquired before any DB op | Transaction-scoped lock is acquired before the sweep's first DB operation |
| Held for whole sweep | Lock is held for the entire sweep |
| Released on commit/rollback | Lock releases on both commit and rollback |
| Dry-run respects lock | Dry-run mode does NOT bypass the lock |
| No lock-ID collision | The advisory-lock ID does not collide with any other lock |

**Evidence required:** two simultaneous sweep attempts — only one proceeds; DB shows the
lock held for the sweep duration and released afterward; dry-run observed acquiring the lock.

### (e) Cross-process consistency

| Check | Description |
|---|---|
| Uniform ORM conventions | Both processes use identical ORM access conventions |
| No process-local assumptions | No code assumes a process-local / persistent connection |
| Appropriate isolation level | Isolation is set so concurrent web reads do not block excessively on sweep locks, and vice-versa |

**Evidence required:** side-by-side access-pattern comparison across both processes; runtime
observation that live requests are not starved during a sweep.

---

## Cross-Cutting Concerns (this phase)

- **Shared-DB contention under load:** two processes competing for the same DB — connection
  exhaustion cascades to *both* processes at once.
- **Sweep vs. live traffic:** lock contention between scheduled sweeps and live requests — a
  sweep must not block hot-row live traffic.
- **Isolation-level reach:** the chosen transaction isolation affects both web reads and bot
  writes simultaneously.

---

## Severity Taxonomy

| Severity | Conditions |
|---|---|
| **CRITICAL** | Non-atomic domain write leaving partial data; lost update on a shared row between processes; connection leak exhausting the DB; blocking ORM call freezing the async loop; advisory lock not held → duplicate sweeps corrupt data; prepared-statement incompatibility with a transaction-mode pooler |
| **HIGH** | Unguarded blocking IO in async; sweep executed without the lock; pooler prepared-statement not disabled; pool sizing that exhausts under load |
| **MEDIUM** | Transaction scope too narrow; missing retry on transient DB error; no connection cleanup on shutdown |
| **LOW** | Missing type hints on bridge wrappers; non-standard pool-config naming |

---

## Edge-Case Checklist

- DB unavailable after both processes started — verify fresh-connection behavior with no
  stale pooled connection reused.
- A bot handler runs a long ORM transaction that blocks the event loop.
- Two instances both trigger a sweep simultaneously.
- Prepared statements fail under a transaction-mode pooler.
- A domain write partially commits due to a crash mid-transaction.
- High concurrency on a single hot row (an ad edited while it is viewed / searched).

---

## Isolation / Test Note

- Transaction and concurrency tests MUST be isolated from other processes.
- Prefer **concurrent-process simulation** as evidence over single-process assertions.
- Explicitly verify the advisory lock prevents double-processing of a sweep.

## Dead-Code Note

- Bridge wrappers or lock utilities that are **defined but never used** are findings.

---

## Report Output

- Write findings to: `.ai/audit/03-db-concurrency/findings.md`
- Use template: `.ai/audit/templates/audit-findings.md`
- **Incremental append**, ≤ 100 lines per append.
- Prefix every finding ID with **`DB-`**.

**Restated problems-only rules for the report:**
- Only findings; omit passing rows.
- If none → single line: **`No problems found in this phase.`**
- Each finding MUST carry **runtime evidence** + the **exact consequence**.
