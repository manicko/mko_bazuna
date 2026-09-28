---
name: 01-entry-architecture
status: draft
validated: no
executor: auditor
problems-only: true
---

# Phase 01 — Entry Points & Process Architecture

## Purpose

A reusable handbook for auditing the **entry surfaces and process topology** of a multi-process Django deployment that shares one project, one configuration surface, and one database.

The long-lived set is environment-dependent: a synchronous WSGI web tier, an asynchronous event-driven bot tier sharing the same persistence layer, and a conditionally-enabled background-job loop. Alongside them sit one-shot bootstrap services and a schema/reference-data gate that must complete before any long-lived process serves. A production tier may add infrastructure components (connection pooler, backup, edge proxy) that a development tier leaves disabled.

This file states *what* to examine and *under which angle*. Concrete artifacts — services, files, modules, commands, identifiers, values — are discovered by the executing auditor, never named here.

**Scope Boundaries** — owned here: entry surfaces, process topology, startup/stop lifecycle, and the schema/reference-data bootstrap guarantee. Not owned here: the health, liveness and readiness **endpoint** plus its probe/orchestration contract (12); async↔sync ORM dispatch, transaction, advisory-lock and connection-pool/pooler semantics (03), the event-loop bridge mechanism (09); secrets and settings **values** (02); media file-handling mechanics (07); test-suite adequacy (11), this phase keeping only the schema-mutating *entry path* angle.

Design deliberately asymmetric between processes, tiers or transports is not a defect on its own. Report it only where the code's own documentation or comments misstate it.

---

## Audit Blocks

Each block is independent — execute any one with no knowledge of the others.

Evidence is a class, not a check list: observed output, a reproduced behaviour, or a static proof that a stated property does not hold; the method is the auditor's. A passing check is methodology, never a finding, and any sound evidence is admissible — nothing here gates a finding on this phase's own checks. Skip a runtime check only when the environment makes it genuinely impossible, and record why.

### 1. Deployment Topology and Startup Dependencies

Establish, per environment/deployment tier, which components are long-lived, one-shot, or conditionally enabled, and which ordering and readiness edges are declared between them.
Compare tiers against one another rather than reading any single tier in isolation: a component enabled but used by nothing, a conditionally-enabled component nothing depends on or points at, and a declared ordering that does not match a component's real boot requirement are all findings.
Record what a supervisor observes when a dependency is unavailable at boot and again during steady state — clean exit, restart loop, or silent hang.

Evidence: the per-tier component inventory with its long-lived, one-shot or conditional role; each declared ordering edge against the component's real boot requirement; what a supervisor observes at boot and in steady state.

### 2. Entry-Surface Inventory and Import-Time Behaviour

Enumerate every entry surface — process bootstraps, the WSGI serving module, container and command-line entry scripts, background-loop entry points, management-command dispatch — and for each establish what work happens at import versus what is deferred.
Check whether importing a surface can reach the database, network, or filesystem; whether configuration load, application-registry initialisation, and first ORM use are ordered deliberately on every surface; and whether each surface's configuration source is explicit about which variant it selects and why.
Also establish what the automated lint and static-typing gates actually include — an entry surface the gates never analyse is invisible risk.

Evidence: the entry-surface inventory with import-time versus deferred work per surface; the database, network or filesystem an import can reach; the surfaces the lint and static-typing gates never analyse.

### 3. Web Serving Tier — Worker Model and Shutdown Contract

Establish the synchronous serving tier's worker/threading model, application preloading, request and graceful timeouts, worker recycling, and arbiter behaviour when a worker dies.
Verify every value the serving configuration depends on is actually supplied by the deployment definition; a dependency satisfied by only one tier is a real defect.
Measure drain/stop latency and exit code against the orchestrator's termination grace period, and look for state that leaks across worker generations on recycle or crash.

Evidence: the serving tier's worker, preload, timeout, recycle and arbiter settings against what each tier actually supplies; measured drain latency and exit code against the grace period; state observed to survive a recycle or crash.

### 4. Async Bot Runtime — Dispatch Chain and Per-Update Lifecycle

Establish the event-driven process's effective update-handling chain: the real ordering of its dispatch and registration layers and what each does per update, where work leaves the event loop, the connection lifecycle per update, and its error/retry registration.
Verify the ordering actually in effect at runtime rather than the order layers are registered; whether a layer can short-circuit the layers behind it and whether that is intended; and whether the hand-managed connection lifecycle is equivalent to what the synchronous tier receives for free.
Confirm the process does not claim readiness before it can actually serve work, and enumerate the failure surfaces of the chain and what each surfaces as.

Evidence: the dispatch chain in the order it runs at runtime; per layer, its per-update work, whether it short-circuits what follows, and its failure surface; the hand-managed connection lifecycle against the synchronous tier's.

### 5. Background Job Loop — Cadence, Dispatch and Restart Safety

Establish the long-lived periodic loop: its cadence model, its job registry, per-job execution and timeout, failure isolation between jobs, and the liveness signal it publishes about itself.
Is every registered job reachable from a dispatcher, and every guarded or idempotent operation reachable from a job? Does per-job dedupe or idempotency state survive a restart, a clock re-alignment, or a skipped tick?
Can a stuck loop be distinguished from a failing one, and a healthy idle loop from a dead one, by an observer outside the process?

Evidence: the cadence, registry, per-job bound and failure isolation; the registered jobs and guarded operations no dispatcher reaches; dedupe or idempotency state across a restart, a clock re-alignment and a skipped tick; the liveness signal as an outside observer sees it.

### 6. Schema and Reference-Bootstrap Gate

Enumerate every path that can mutate schema or reference data — the orchestrated one-shot bootstrap services, ad-hoc command-line invocation, automation pipelines, and the test harness.
Which guard does each path take, and does it take one at all? What are the guard's acquisition semantics — blocking or skip, bounded or unbounded, observable to an operator?
Does the once-only guarantee come from declared ordering, from the guard, or from neither — and does the guard's own documented semantics match what it actually does?

Evidence: every schema- or reference-mutating path with the guard it takes, or none; that guard's acquisition semantics; where the once-only guarantee actually comes from; the guard's documented semantics against what it does.

### 7. Cross-Process Shared State and Side-Effect Coordination

Establish everything the processes coordinate through: the shared database, the media filesystem, the shared cache, and any out-of-band marker or state files.
Separate what is genuinely shared from what is per-process or per-restart. Which multi-resource side effects can interleave between processes, between tiers, or across a restart? Where does a single-writer assumption exist that nothing enforces?
Treat any in-memory dedupe or idempotency marker as a finding candidate until its persistence across restart is demonstrated.

Evidence: the shared-state inventory, marked genuinely shared against per-process or per-restart; the multi-resource side effects that can interleave; the single-writer assumptions nothing enforces; the in-memory marker whose persistence across restart is unproven.

### 8. Entry-Layer Discipline and Dependency Direction

Establish the transport modules — HTTP views, bot handlers, entry scripts — and the layers they are meant to delegate to.
Parse → delegate → respond, nothing more: no domain rules, no multi-step persistence, no stateful sanitisation. Does any lower layer import back from the entry layer? Does the import graph stay acyclic across layers?
Where two transports implement the same protocol, is the implementation shared or duplicated? Duplication is the question — deliberate asymmetry between transports is not itself a defect.

Evidence: the transport-module to layer map; the domain or persistence work found inside an entry module; every back-import and import cycle; each protocol implemented more than once.

### 9. Route Surface Wiring and Entry-Point Reachability

Establish the URL surface as assembled at project and per-app level, plus non-HTTP entry registrations: admin, monitoring endpoints, handler routers, registered periodic operations.
Check namespacing and collisions across includes, each route's downstream path, endpoints mounted outside the normal view → service → persistence path, and aliases retained for compatibility.
Any registered route, handler, router, or operation with no inbound trigger is a finding.

Evidence: the assembled route and registration surface with each entry's downstream path; collisions and namespacing across includes; endpoints mounted outside the view → service → persistence path; every entry with no inbound trigger.

---

## Severity Taxonomy

Grade by **effect and blast radius**, not by mechanism name; rate what is true now, not the worst consequence if triggered.

- **CRITICAL** — data loss or corruption; a once-only guarantee that is not actually guaranteed; concurrent or duplicate schema mutation; a process that serves work before it can safely do so.
- **HIGH** — service unavailability, or silently wrong results that a user or a seller would act on; a documented startup, stop, or liveness contract that does not hold.
- **MEDIUM** — degraded operability: a defect an operator cannot distinguish from normal behaviour, or environment-tier divergence that is not intentional.
- **LOW** — cosmetic or documentation-only drift with no runtime consequence.

An empty band is a valid outcome — do not populate it with a hypothetical, and do not promote an item for sounding alarming.

---

## Report Output

- Findings path: `.ai/audit/01-entry-architecture/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `ENT-`
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence
- "Violates invariant X" is not a finding: name the exact role that violates the property and the exact consequence; evidence fences are captioned, tied to a specific claim, and overflow to the Appendices
- Empty state, exactly: `No problems found in this phase.`
