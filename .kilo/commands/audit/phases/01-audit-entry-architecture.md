---
name: 01-entry-architecture
status: draft
validated: no
executor: auditor
problems-only: true
---

# Phase 01 Audit — Entry Points & Process Architecture

## Purpose

Reusable handbook for auditing the entry points and process architecture of a
**dual-process Django system**:

- **Web process** — synchronous gunicorn WSGI serving a server-rendered HTMX MPA.
- **Bot process** — asynchronous aiogram event loop that calls `django.setup()`
  and shares the persistence layer.

Both share one Django project + one PostgreSQL database. Migrations run exactly
once before both start. An nginx reverse proxy fronts both (TLS termination,
media serving).

Audit through **architectural layers**, **zones of responsibility**, **key
risks**, and **goals**. Never reference concrete file/module/class names — refer
to the *roles* (the web WSGI entrypoint, the bot process entrypoint, the
migration runner, the settings module, the URL router / route registry, the
shared ORM / persistence layer, the async/sync boundary wrapper).

## Output Mode

`problems-only: true` — **only problems, bugs, and deviations are documented.**

- Do NOT write sections that say "X is correct" or "no issues found in Y".
- Do NOT include checklist rows where the check passes — omit them entirely.
- If a dimension has zero findings after investigation, **omit the dimension entirely**.
- Every finding must be actionable: real problem + runtime evidence + exact consequence.

---

## Architectural Layers (zones of responsibility)

| Layer | Zone of responsibility | Key risks |
|-------|------------------------|-----------|
| Bootstrap / entry | Load settings once; `django.setup()`; establish DB connectivity; start serving. | Import-time side effects; ORM access before setup; divergent settings. |
| Migration orchestration | Run schema migrations exactly once under an advisory lock before either process boots. | Double migrations; concurrent runs; no dependency on completion. |
| Web transport | Accept HTTP; route to thin views; delegate to service/core. | Business logic in views; blocking loops; missing pooling. |
| Bot transport | Receive updates on the event loop; route to thin handlers; delegate. | Unwrapped ORM in async; blocking IO; no reconnect/shutdown handling. |
| Service / core | Business logic, isolated from transport. | Reverse imports from entry layer; shared mutable local state. |
| Persistence | Shared ORM over PostgreSQL; transactions; media filesystem. | Cross-process state assumptions; connection leaks; uncoordinated media writes. |

---

## Discovery Stage

Map the architecture before checking anything. Use roles, not names.

1. **Entry point discovery** — Locate the web WSGI entrypoint and the bot
   process entrypoint. Trace the Django bootstrap in each. Verify both reference
   the **same settings module**. Verify the bot calls `django.setup()` **before**
   any ORM/model import.
2. **Migration orchestration discovery** — Locate the one-shot migration runner.
   Verify it takes an **advisory lock** to prevent concurrent runs. Verify **both**
   processes depend on migration completion before starting.
3. **Web↔Bot boundary mapping** — Enumerate all entry handlers (HTTP routes +
   bot handlers). Trace their imports into service/core layers. Verify **no
   reverse imports** (entry layer must not be imported by lower layers). Identify
   shared-state assumptions (database, media filesystem).
4. **Async/sync boundary mapping** — Find where the async bot loop touches the
   synchronous ORM. Identify the sync-to-async (or equivalent) wrapping around
   every ORM call. Identify blocking IO in async handlers.

---

## Mandatory Runtime Verification

**Run before evaluating any dimension. Skip only if impossible — document why.**

### R1 — Import Verification
Import both entry modules in isolation. Verify **no import-time side effects**
(no DB access, no model queries, no network) and **no circular imports**.
Capture `python -c "import ..."` output and tracebacks.

### R2 — Process Boot Test
Boot each process in isolation. Capture the init sequence (logs). Confirm:
- DB connectivity check precedes request/handler handling.
- Migration completes before boot starts (or boot is gated on migration).
Record the exact boot order; anomalies are evidence.

### R3 — Linter + Type Checker
Run the project linter and type checker (`ruff`, `basedpyright`). Record exit
codes. Focus on **async/sync boundary type errors**.

### R4 — Test-Suite Run
Run the test suite. Record pass/fail. Note any failure touching entry/process
layers.

### R5 — Migration Guard Verification
Start both processes near-simultaneously; confirm migrations execute **exactly
once** and that concurrent starts cannot trigger duplicate/parallel migrations.
Inspect advisory-lock acquisition and release on failure.

### R6 — Process Isolation Verification
Confirm neither process assumes **process-local mutable state** persists across
the two processes. Confirm shared state lives only in the DB / media FS.

---

## Audit Dimensions

Each dimension is a table of `Check | Description`. **Evidence required** per
dimension: runtime output (boot logs, import errors, lint/type exit codes, test
results, lock traces) or static analysis proving the deviation.

### (a) Process Initialization Correctness

| Check | Description |
|-------|-------------|
| Both processes boot | Each entrypoint starts and reaches ready state independently. |
| Settings loaded once | Exactly one settings module; no per-process divergent config. |
| `django.setup()` before ORM (bot) | Bot entrypoint calls setup before any ORM/model import. |
| No import-time Django access | Entry modules perform no DB/ORM access at import time. |

### (b) Migration-Once Guarantee

| Check | Description |
|-------|-------------|
| Advisory lock held | Migration runner takes a DB advisory lock; concurrent runs blocked. |
| Compose/lifetime dependency | Both processes depend on migration completion before starting. |
| No migration calls in entrypoints | Entrypoints never run migrations themselves. |
| Lock released on failure | Lock is released if migration fails, allowing a clean retry. |

### (c) Entry-Handler Thinness

| Check | Description |
|-------|-------------|
| Thin handlers | Entry handlers parse → delegate → respond only. |
| No business logic in entry | No domain rules/sanitization/stateful logic in views/handlers. |
| No ORM loops in entry | No query loops or bulk persistence in the entry layer. |

### (d) Layer Boundary & Dependency Direction

| Check | Description |
|-------|-------------|
| Entry imports only service/core | Entry layer imports only service/core, never the reverse. |
| Acyclic dependencies | No cycles across layers. |
| Consistent ORM access patterns | Both processes use the same ORM access conventions. |

### (e) Process Isolation & Shared State

| Check | Description |
|-------|-------------|
| Media writes coordinated | Media filesystem writes are safe under concurrent web/bot writes. |
| No process-local state assumed | No in-memory state assumed persistent across processes. |
| Transactions scoped correctly | Transactions are correctly scoped across async/sync boundaries. |

### (f) Async/Sync Boundary

| Check | Description |
|-------|-------------|
| Single event loop | Bot uses one event loop; no stray loops/threads. |
| ORM access wrapped/guarded | Every ORM call from async is wrapped (sync-to-async or equivalent). |
| No blocking IO in async | No blocking FS/network in async handlers. |
| Graceful shutdown | Both processes handle interrupt/signal and release resources. |
| DB connections released | Connections returned/closed on shutdown. |

---

## Cross-Cutting Concerns

Checks + evidence, not duplicated elsewhere:

- **Startup ordering / races** — web and bot race at boot; verify a defined
  start order or independent safe boot.
- **Shared secret source at boot** — secrets loaded once; no secret leakage in
  logs/tracebacks.
- **Environment separation** — dev vs prod entry behavior: `DEBUG`, TLS, secure
  cookies differ correctly.
- **Graceful degradation on DB-down** — boot with DB unavailable yields
  non-zero exit + restart policy (not silent hang).
- **Restart-policy expectations** — long-lived processes have defined restart
  semantics (crash → restart, no duplicate migration).

---

## Dead-Code / Orphan-Entry Detection

Registered routes/handlers/entry branches that are unreachable or never wired.

**How to evidence:**
- Static analysis: enumerate all registered routes/handlers and trace each to a
  reachable trigger (HTTP path, bot command/callback).
- Reachability: confirm no dead registration with zero inbound route.
- Report any entry branch with no wiring as a finding (`ENT-` prefix).

---

## Edge-Case Checklist

| Scenario | What to verify |
|----------|----------------|
| Migration fails mid-way | Lock released; partial state recoverable; clean retry. |
| One process starts before migration done | Boot fails fast or waits, never serves stale schema. |
| Bot reconnects while web down | Bot reconnect logic independent of web; no shared lock held. |
| Settings import side effects | Importing settings performs no IO/queries. |
| DB down after both started | Both detect and exit/restart; no stuck threads. |
| Missing env/secrets | Boot fails with clear error, non-zero exit. |
| Multiple migration containers simultaneously | Advisory lock prevents parallel runs. |
| Missing TLS cert | nginx/entry fails fast with clear error. |
| Missing bot token | Bot boot fails fast with clear error, non-zero exit. |

---

## Severity Taxonomy

- **CRITICAL** — migrations run twice/concurrently; business logic in entry
  layer; import-time ORM side effects; unwrapped ORM in async handler; missing
  migration lock.
- **HIGH** — no connection-pool limits; blocking IO in async; no graceful
  shutdown; reverse imports from entry layer.
- **MEDIUM** — uncoordinated media writes; divergent dev/prod behavior; unclear
  restart policy; missing env fails silently.
- **LOW** — cosmetic boot logs; minor unreachable entry branches; non-blocking
  lint warnings.

---

## Report Output

Write findings to: `.ai/audit/01-entry-architecture/findings.md` using template
`.ai/audit/templates/audit-findings.md`.

**Write the file incrementally — append blocks of ≤100 lines each. Never write
the entire report in a single call.**

Use prefix `ENT-` for finding IDs.

**`problems-only: true` rules:**
- The report contains **only findings** — real problems discovered during
  investigation.
- Do NOT include sections, dimensions, or checklist rows where everything is
  correct.
- If after completing all Runtime Verification steps and all Audit Dimensions,
  no problems were found, write a single line: `No problems found in this phase.`
- Every finding MUST include:
  1. **Runtime evidence** — boot logs, import errors, lock traces, lint/type
     exit codes, test failures, reachability output.
  2. **Not just** "violates invariant X" — show the exact layer/role that
     violates it and the exact consequence (e.g., duplicate schema migration,
     ORM accessed before setup, unwrapped async DB call).
