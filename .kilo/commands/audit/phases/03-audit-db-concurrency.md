---
name: 03-db-concurrency
status: draft
validated: no
executor: auditor
problems-only: true
---

# Phase 03 — Database & Concurrency Consistency

## Purpose

Audits transaction boundaries, row-level locking, the cross-process serialisation
registry, idempotent background and one-shot operations, recomputation of derived
values, and cross-resource consistency in a dual-process Django system — a
synchronous web tier and an asynchronous event-driven tier — over one shared
PostgreSQL database.

This file names what to examine and under which angle; the executing auditor
discovers the concrete artifacts. Owned here: ORM-dispatch, transaction,
advisory-lock and connection-pool semantics. Owned elsewhere: process startup,
bootstrap ordering and the schema gate at the *process* level → 01; the event-loop
bridge mechanism → 09; pooler sizing and measurable latency consequences → 13; the
claim-guard race → 04. → 17: the arithmetic of a derived value — the scope of
numerator against denominator, what counts as one occurrence, the window it claims
to cover, and the range and rounding applied — is 17's; this phase owns only
whether the value is re-derived when its input moves, which recompute coverage
already claims here.

## Audit Blocks

Each block is independent — execute any one with no knowledge of the others.

Evidence is a class, not a check list: observed behaviour, reproduced output, or a
static proof that a stated property does not hold; the method is the auditor's. A
passing check is methodology, never a finding, and any sound evidence is admissible
— nothing here gates a finding on this phase's own checks. Judge a concurrency
guard by whether it would fail if the protection it names were removed.

### 1. Persistence access surface and configuration-path divergence

*Establish how the database is reached from every process and automation path, and where the ORM contract is bypassed by
hand-written SQL. Where alternative configuration branches are each selectable by a real environment, compare the
connection lifetime, pool and query options they yield. Establish what happens when a connection is lost mid-request.*
Evidence: effective settings per reachable configuration branch; non-ORM write paths; one induced connection loss.

### 2. Transaction boundaries of multi-row and multi-resource domain writes

*Establish which domain operations change more than one row, or a row and another row that only means something together, and
whether the boundary sits where the invariant is. A partial commit is reachable when writes straddle boundaries, when a boundary
is narrower than the invariant it protects, or when the failure it is built for never arrives.*
Evidence: boundary map per multi-row operation; one induced mid-write failure, all-or-nothing or not.

### 3. Error handling inside a transaction boundary

*Take the database errors the code intends to tolerate and ask what happens to the transaction around them. Is the failing
statement isolated in a savepoint so the enclosing transaction stays usable; is any helper promising never to affect its
caller invoked from inside another transaction; does a swallowed error leave the transaction abortable?*
Evidence: one induced failure per tolerant path; the enclosing transaction's state afterwards.

### 4. Constraint-enforced invariants and their recovery paths

*Where a database constraint carries a business invariant, treat it as an enforcement mechanism with callers. For every
writer that can reach it, is the outcome defined: a correct recovery, a defined no-op, or an error the end user sees? A
constraint that is both the last line of defence and an unhandled user-facing failure is a finding; so is one whose documented
recovery is unreachable.*
Evidence: constraint set mapped to the invariant each enforces; per writer, the observed outcome.

### 5. Read-modify-write, destructive operations, and derived values

*Establish every operation that reads state, decides, then writes or deletes, and every row value maintained away from the
write changing its input. Does the mutation re-assert the predicate the selection used, or act by identifier and ignore the
condition that justified those rows? Which paths take a row-level lock? A correctly serialised operation can still destroy
another writer's work.*
Evidence: selection predicate vs mutation filter per destructive path; a two-writer case per unlocked path.

### 6. Cross-process serialisation registry

*Treat every mutual-exclusion mechanism as one system: where identifiers are allocated, who owns each, and which operations
must be exclusive but have none. For each: the lifetime chosen — engine-released at commit, or released by the caller —
acquisition point, release path, and what it does not cover: work dispatched to a child process, a second identifier for one
resource, a nested acquisition. A caller-released lifetime holds only if the release runs and nothing recycles the connection.
Does each lifetime match the path the operation runs on, and is the split's stated motivation enforced anywhere?*
Evidence: registry mapped to lifetime, holder, acquisition point, release path, covered operations.

### 7. Background and one-shot operation execution safety

*Establish how a scheduled or one-shot operation is invoked, bounded and interrupted, and what an interrupted run leaves: an
open transaction, held row locks, a held long-lived lock, or an already-committed batch. Is an operation not atomic by design
safe to repeat, and does a half-applied run resume or double-apply? Hold duration is measurable: a lock that works and is
held too long is a finding.*
Evidence: per operation — bound, state left by a mid-run kill, repeat-run outcome, measured hold duration.

### 8. Schema and reference-data mutation under concurrent load

*Establish the windows in which database enforcement or index maintenance is absent or being replaced: a replace-then-recreate
sequence, a non-atomic drop-and-create pair, a backfill over a live table. Do concurrent writers observe such a window? Does a
lock held by a coordinating process cover the work it dispatches — a child process inherits nothing.*
Evidence: ordered mutating steps with the window each opens; lock holder vs the session doing the work.

### 9. Database work in the asynchronous process

*Establish the serialisation granularity of the event-driven tier's database work: how many operations can be in flight, on
how many connections, in how many threads. Where it funnels through one shared bounded worker, a single contended lock
delays every database operation the process performs, not only the blocked one — treat that granularity, not the call, as the
unit of risk. Is a wait for a lock or a statement bounded, and what happens when the bound is passed? Can any synchronous
database call reach the event loop unguarded?*
Evidence: effective database concurrency limit; a measured stall of unrelated work; the wait bound, or its absence.

### 10. Consistency across the shared-state boundary

*Establish the effects that span more than one resource — a row and a file it names, a row and a cached value, a row and
out-of-band marker state — where the resources commit at different times and are written by different subsystems. Which
writer assumes it is alone, which resource is the real unit of atomicity, and whether the intermediate state leaves a
dangling reference or an orphan nothing repairs. Include state outside the database treated as single-writer.*
Evidence: per multi-resource effect — the resources, the commit order, one observed intermediate state.

## Severity Taxonomy

Grade by **effect and blast radius**, not by mechanism name; rate what is true now, not the worst consequence if triggered.

- **CRITICAL** — a transaction that is neither all-or-nothing nor usable after a tolerated error: a domain write that can partially commit, an error-absorption path that aborts its caller's transaction, a race backstop whose advertised recovery can never execute.
- **HIGH** — availability loss or silently wrong results: database work serialised behind a single unbounded resource so one blocked operation degrades a whole process; live work destroyed by an operation that is correctly serialised but wrongly scoped; an invariant violated with nothing surfaced to anyone.
- **MEDIUM** — degraded operability or a bounded correctness gap: a mutation acting on rows its own selection predicate excluded; a lock that does not cover the work dispatched under it; a window in which concurrent writes go unmaintained; a multi-resource effect leaving a dangling reference or an orphan.
- **LOW** — observability and documentation drift with no runtime consequence today: a hold or release event an operator cannot see; work performed inside a lock only to log a count; a comment about locking that the code does not implement.

## Report Output

- Findings path: `.ai/audit/03-db-concurrency/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `DB-`
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence; empty state, exactly: `No problems found in this phase.`
- Verification-table entries are a methodology record, not a filter; file a finding a shipped test contradicts and record that test as a remediation blocker
