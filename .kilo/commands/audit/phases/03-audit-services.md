---
name: 03-services
status: complete
validated: no
executor: auditor
problems-only: true
---

# Phase 03 Audit — Service Layer & Business Logic

## Purpose

This is a **reusable, system-agnostic handbook** for auditing the service/business
logic layer of ANY application. It is not tied to a specific framework, library, or
set of domain modules. Apply the discovery steps and audit dimensions to whatever
the system's service layer actually contains (services, use cases, processors,
clients), adapting concrete names to the implementation at hand.

## Output Mode

`problems-only: true` — **only problems, bugs, and deviations are documented.**

- **Do NOT** write sections that say "X is correct" or "no issues found in Y".
- **Do NOT** include checklist rows where the check passes — omit them entirely.
- If a dimension has zero findings after investigation, **omit the dimension entirely**.
- Every finding must be actionable: it describes a real problem, its evidence (code/logs/output), and its impact.

---

## Discovery Stage

Before performing audit checks, discover the service layer architecture:

1. **Service Discovery** — Locate all service modules. Map their responsibilities: what does each module do? What are its dependencies?
2. **Module Responsibility Mapping** — For each module: what is its purpose? Does it have a focused, single responsibility?
3. **Dependency Graph** — Map how modules depend on each other. Identify the composition root (where components are instantiated and wired together).
4. **Processing Chain Discovery** — Trace how the system's core data is processed end-to-end: input acquisition, matching/filtering, transformation/grouping, and output dispatch. Identify each transformation step.

[Adapt these steps to the domain the system actually implements — e.g., a message pipeline, a data ingestion pipeline, a request handler.]

---

## Mandatory Runtime Verification

**Before evaluating any checklist item, you MUST complete these steps. Use the commands provided in the project's commands file. Skip only if a step is impossible — document why.**

### Step R1 — Import Verification

Import all service modules. Verify no import errors or missing dependencies.

### Step R2 — Linter and Type Checker

Run the project's configured linter and type checker commands.

- Record exit codes and output.

### Step R3 — Run Test Suite

Run the project's test suite, focusing on service-layer tests.

- Record pass/fail counts and failure output.

### Step R4 — Dead Code Search

Search for functions/methods defined but never called outside tests.

- Record each instance with file path and line number.

---

## Audit Scope

Service classes/modules, domain models, business logic, and the core processing pipeline.

---

## Audit Dimensions

### 1. Single Responsibility

| Check | Description |
|-------|-------------|
| Each module has focused responsibilities | Modules are organized by a clear, single purpose (e.g., one handles processing/forwarding, another wraps the external client). |
| Models combine related state | Domain models hold configuration together with the methods that operate on that configuration. |

**Evidence required:** Read each module. Verify the design follows its documented purpose.

### 2. Dependency Direction

| Check | Description |
|-------|-------------|
| Services depend on abstractions/models | Services receive typed models, not raw parsed data. |
| No circular dependencies | Import chains between modules are acyclic. |
| Composition root is clear | A single coordinator wires components together and runs the main loop/flow. |

**Evidence required:** Trace import chains between modules. Verify the dependency graph is acyclic.

### 3. Processing Correctness

| Check | Description |
|-------|-------------|
| Filtering/matching is correct | Inputs are filtered/matched by configured criteria using the matcher/parser module. |
| Grouping works | Related items (e.g., grouped media) are correctly grouped before dispatch. |
| Duplicate prevention | State (e.g., last-processed marker) prevents re-processing already-seen items. |
| Dispatch handles errors | The dispatch step retries on transient/rate-limit errors and handles other API errors. |

**Evidence required:** Read the processing module. Trace the pipeline. Check for matching/grouping and error-handling logic.

---

## Report Output

Write findings to: `.ai/audit/03-services/findings.md` using template `.ai/audit/templates/audit-findings.md`.

**Write the file incrementally — append blocks of ≤100 lines each. Never write the entire report in a single call.**

Use prefix `SRV-` for finding IDs.

**`problems-only: true` rules:**
- The report contains **only findings** — real problems discovered during investigation.
- Do NOT include sections, dimensions, or checklist rows where everything is correct.
- If after completing all Runtime Verification steps and all Audit Dimensions, no problems were found, write a single line: `No problems found in this phase.`
- Every finding MUST include:
  1. **Runtime evidence** — import errors, test failures, dead code proof (file:line), logic bugs.
  2. **Not just:** "violates invariant X" — show the exact code that violates it and the exact consequence.
