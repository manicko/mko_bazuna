---
name: 13-performance
status: draft
validated: no
executor: auditor
problems-only: true
---

# Phase 13 — Performance & Scalability

## Purpose

What the system costs per request, per event and per scheduled run; whether those costs are bounded; and whether the numbers the system believes
about itself are measured or asserted. This file names what to examine and under which angle — the executing auditor discovers the concrete artifacts.

Scope boundaries — this phase owns the measurable consequence of latency, throughput and capacity, and nothing else. Owned elsewhere: the connection pooler's configuration semantics (03), whether the
production path enables the pooler at all (12), its place in the process topology (01); plan stability, unbounded scans and missing indexes on the search path, and what a cached result set may still serve
(08); the language component of a key (14); ORM dispatch, transaction and wait-bound semantics in the event-driven process (03) and the bridge mechanism itself (09); whether a scheduled sweep is safe to run twice (03).

## Audit Blocks

Each block is independent — execute any one with no knowledge of the others, and each carries its own evidence. Evidence is a class, not a check list: observed behaviour, reproduced output, or a
static proof that a stated property does not hold. Two questions here cannot be settled in the environment at hand — a latency or load measurement against seeded production-volume data, and any
measurement under real traffic; establish each from what is observable (the declared constant, the configured worker count, the plan shape, statement and parameter counts, the per-request statement
inventory) and state plainly what could not be verified and why. A passing check is methodology, never a finding, and any sound evidence is admissible: nothing here gates a finding on this phase's own list.

### 1. Response budgets — what is declared, what is covered, what acts on it

*Establish which request paths carry real traffic and which carry a budget: a declared target no alert watches, an alert pinned to one path while a busier path has none, a constant written once and read in
more than one place. Establish whether any measurement behind a stated target is a distribution rather than a single sample, and whether the value a consumer compares against is the value the system declares.*
Evidence: the budget inventory with the path each covers against the paths carrying the traffic; per alert, the
series it queries and whether anything emits it; the declared constant against the value each consumer compares.

### 2. A gate that reports green and decides nothing

*Take every automated control that emits a pass/fail on latency, query shape or load, and separate three questions: does it exist, what scope does it declare, what did it actually
examine. Establish where the compared value comes from — the declared source, or a threshold restated beside it as a literal; whether a metric is read positionally from a result file
whose format a dependency can change; and whether a selector matching nothing yields a value a guard then accepts. A threshold not bound to the constant it names cannot drift with it,
and a control that passes on an empty result cannot fail. Establish separately whether a verdict holds while the component it checks is non-functional in the deployed configuration.*
Evidence: per control — existence, declared scope, the items it actually examined, the origin of the compared value, and one case where it reports success while its subject is bad.

### 3. What the performance discipline actually exercises

*Establish what the shipped performance instruments cover: which request shapes a load profile reaches and whether each target resolves to a route, what dataset
volume they require, and which production query shapes the profiling path builds and omits. A harness requiring a volume no shipped environment reaches, one
spending much of its journey on responses that return early, and one whose asserted targets cannot be met where it must run, are each a discipline in name only.*
Evidence: the load profile's target inventory with a resolves verdict each and the request share returning early; the profiling path's built
shapes against the shapes the production request path emits; the volume a harness requires against the volume any shipped environment creates.

### 4. What a cache key encodes and what a version token retires

*Establish what a key encodes and omits, and a version token's own lifetime against the lifetime of what it retires: a token expiring while the data it retired is still live restores a version already
left behind. Establish whether a key carrying caller-supplied segments varies wherever a caller can vary it, and whether two concurrent readers resolve one key differently. Claims that token-bumped
invalidation makes retired entries unreachable by expiry rather than by a global wipe, and that a single-flight stale-while-revalidate wrapper bounds the stale window, are claims to confirm or refute, not
the design to assume. Phase 13 owns the key's composition and lifetime: what a cache key encodes and omits, and a freshness/version token's lifetime against the lifetime of the data it
retires, and the key's behaviour under concurrent access. Phase 08 owns the cached result-set itself: staleness, whether a stored entry may still serve a buyer-facing result set, and whether a
content change propagates to every stored form. Phase 14 owns whether the language component of a key is correct and where that component's value comes from.*
Evidence: the key inventory with encoded and omitted components; the token's lifetime against the data's; one key two concurrent readers resolve differently.

### 5. Cache behaviour across processes and across backends

*Establish what the deployed cache backend provides that the environment the shipped guards run in does not. A shared store has primitives a per-process one lacks;
an invalidation utility behind a capability guard is a working invalidation in one environment and a logged no-op in the other; a single-flight lock is per-process
in one and shared in the other. Establish whether the invariants are regression-locked only under the backend the guards run with: a test's fidelity to the
deployed configuration is part of what it proves, and a guard's own description of a limitation it never exercises is evidence about the system, not a defence of it.*
Evidence: the deployed backend against the one the shipped cache guards run under, with the primitives each provides;
one invalidation path with a per-environment verdict; one guard asserting a behaviour the deployed backend cannot exhibit.

### 6. What a hit and a miss cost

*Establish the cost of the served-from-cache path, not only of the miss: statement size, bind-parameter count, conditional-branch count, and which part of the plan
scales with the stored set rather than with the page. Establish what N concurrent first-hitters each pay on a cold miss, whether a lock serialises the writers or the
callers, and what a caller that loses the race is told to do next. A lock that stops duplicate writes while every loser recomputes anyway is not a stampede guard.*
Evidence: on the hit path — statement bytes, bind count, branch count, and the plan element that scales with the
stored set; on a cold miss — the work each of N concurrent first-hitters performs and the loser's documented instruction.

### 7. Query cost under caller-controlled input

*Establish what a plan does as the caller widens a filter: a multi-value selection becoming one join per value, a repeated value set, a tree expansion following more than one parent relation. Establish whether a
bound exists on what a caller may supply, and whether growth is additive or multiplicative — a join tree whose inner scan stays constant while the rows above it multiply is not readable from any single plan node.*
Evidence: the cost curve against a widening filter with the item count at each point; the bound in force on the caller-supplied value, or its absence; one filter whose join count grows with input.

### 8. Per-object and per-event work outside the main query

*Establish what one page view or one event costs beyond its main query: related-object lookups, per-object existence probes, and prefetch detection that cannot fire for the relation shape it tests. Establish
whether a per-object cost is paid once per rendered row, whether it disappears when the row is present and returns when it is absent, and what one event costs in the event-driven process — round trips,
statements, and what that count scales with. The mechanism carrying work across the loop boundary and the semantics of the wait are another phase's; the consequence in round trips and statements is this one's.*
Evidence: per-page statement counts attributed to their call sites; one per-object path that fires only when the row is absent; one event's round-trip and statement count and what it scales with.

### 9. Serialisation and materialisation per request

*Establish what is pulled regardless of page size: a reference set materialised into every request by shared context, the same set fetched twice on one path, a
hierarchy rebuilt per request where a cached rendering of the same tree already exists. Establish what a request transfers per page view — payload, element
count, repeated records — and whether a cost negligible at a shipped fixture's scale is bounded by design or bounded only by an assumption that will not hold.*
Evidence: per-request materialisation volume with the row count each set carries; a set fetched more than once on one request; per-page-view payload and element counts; the fixture's scale against the bound, if any.

### 10. Background and batch work: cost, transaction width, lock hold

*Establish what a scheduled or one-shot run costs against production data volume rather than a fixture's: the work performed per unit of data, whether it is expressible as a
set operation or issued per row, and whether the resulting statement count scales linearly with the table. Establish how wide the transaction it runs in is, what it holds
for its duration, and what a concurrent run or a live request does while it holds it. Whether such a sweep is safe to run twice is another phase's; its cost is this one's.*
Evidence: per run — statements issued, wall time, and the item count the cost scales with; the transaction's width and the locks held; one run whose duration competes with a live request.

### 11. The ceiling each tier imposes

*Establish, per long-lived tier, what bounds concurrent work. In the synchronous serving tier: the worker model, whether the worker count derives from the deployment target's declared CPU and memory allocation or
is hard-coded, and what a representative request's cost implies for the ceiling — and whether that request is CPU-bound or I/O-bound, because only one answer responds to more workers. Establish the same for the
event-driven process, where all persistence work may funnel through one shared bounded worker thread; establish whether anything bounds how long work waits for it, since an unbounded wait is a latency property
rather than a mechanism question. Establish the measurable consequence of the connection pooler's presence or absence for the traffic in front of it — not how it is configured, and not whether production enables it.*
Evidence: per tier — worker model, the ceiling it implies, and the source of the worker count against the deployment target's declared allocation; the CPU/I-O split of a
representative request; the serialisation point in the event-driven process and any bound on the wait there; the connection count the serving tier actually reaches against the store's.

## Severity Taxonomy

Grade by **effect and blast radius**, not by mechanism name; rate what is true now, not the worst consequence if triggered. The bands are effect classes, not a closed list of mechanisms, so a defect
whose mechanism is not named here still lands by the consequence it is producing.

- **CRITICAL** — a control believed to be active that is not, on the path that decides whether a performance risk is caught before it ships: nothing distinguishes a checked subject
  from an unchecked one, and a reviewer cannot tell the difference. An empty band is a valid outcome — do not populate it with a hypothetical, and do not promote an item for sounding alarming.
- **HIGH** — cost that is real now and scales with a quantity the caller or the data controls, on a path that is on: one input able to exhaust a shared resource the whole system depends
  on, or a cost linear in a production table that runs unattended against live traffic.
- **MEDIUM** — a cost demonstrated but conditional on volume, catalogue size, or a configuration not yet in effect, where the design is unbounded rather than the present value being large;
  a cache or query path whose correctness holds only in the environment its guards run in.
- **LOW** — a stated objective with nothing that measures it; a guard, comment or runbook line that no longer describes the behaviour beside it; a discipline whose declared scope is wider
  than its coverage.

## Report Output

- Findings path: `.ai/audit/13-performance/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `PERF-` — **already in use** in shipped source, tests, workflows and reports from a prior cycle, with at least one identifier already resolving to two different
  findings; check for a collision before minting an ID and report it rather than creating a second namespace
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence
- Empty state, exactly: `No problems found in this phase.`
