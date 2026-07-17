---
name: 05-data-flow
status: complete
validated: no
executor: auditor
problems-only: true
---

# Phase 06 Audit — End-to-End Data Flow

## Purpose

This is a **reusable, system-agnostic handbook** for auditing how data moves through
ANY system from entry point to final output. It is not tied to a specific pipeline,
domain, or set of stages. Apply the discovery steps and audit dimensions to whatever
the system's end-to-end flow actually is, adapting concrete names to the
implementation at hand.

## Output Mode

`problems-only: true` — **only problems, bugs, and deviations are documented.**

- **Do NOT** write sections that say "X is correct" or "no issues found in Y".
- **Do NOT** include checklist rows where the check passes — omit them entirely.
- If a dimension has zero findings after investigation, **omit the dimension entirely**.
- Every finding must be actionable: it describes a real problem, its evidence (code/logs/output), and its impact.

---

## Discovery Stage

Before performing audit checks, trace the complete data flow:

1. **Full Pipeline Mapping** — Trace the entire path: entry command → config loading → external auth/connection → per-source data fetching → matching/filtering → dispatch/output.
2. **Config Propagation Trace** — For each config section, trace exactly how it flows from source → typed model → function parameter. Identify every hop.
3. **Item Lifecycle** — Pick a single data item and trace it from source to final output. Document every transformation.
4. **Error Path Mapping** — For each stage in the pipeline, identify what happens on failure. Does the error propagate correctly? Is cleanup guaranteed?

---

## Mandatory Runtime Verification

**Before evaluating any checklist item, you MUST complete these steps. Use the commands provided in the project's commands file. Skip only if a step is impossible — document why.**

### Step R1 — Import Full Pipeline

Import the entry point, config reader, and all service modules. Verify the full chain is importable.

### Step R2 — Linter and Type Checker

Run the project's configured linter and type checker commands.

- Record exit codes and output.

### Step R3 — Run Test Suite

Run the complete test suite.

- Record pass/fail counts and failure output.

---

## Audit Scope

End-to-end data flow from entry invocation through config loading, external auth, data fetching, processing, and dispatch. Cross-layer interaction verification.

---

## Audit Dimensions

### 1. Config-to-Service Propagation

**Trace each config section from source to its final consumer. Document every hop.**

| Config Section | Expected Consumer | Verification |
|----------------|-------------------|--------------|
| connection/auth settings | client creation | Verify all credentials/connection params reach the client. |
| scheduling/interval settings | main loop | Verify the interval controls the processing frequency. |
| source/target settings | per-item task creation | Verify source names, targets, and filter criteria all reach the task. |

**For each field, document:** source key → model field → function parameter. If any hop is missing or broken, that is a finding.

### 2. Item Lifecycle Trace

**Trace a single data item from source to final output. Document every transformation.**

| Stage | Input | Output | Verification |
|-------|-------|--------|--------------|
| Source fetch | source identifier | raw items | Verify items are fetched correctly. |
| Matching/filtering | item content, criteria | match/no-match | Verify filter logic is correct. |
| Grouping | related items | grouped list | Verify grouping logic works. |
| State update | processed items | last-processed marker update | Verify state is persisted. |
| Dispatch | matched items, targets | external API call | Verify items are dispatched correctly. |

**If any transformation is incorrect, missing, or loses data, that is a finding.**

### 3. Multi-Source Flow Correctness

| Check | Description |
|-------|-------------|
| Each source gets its own data | Data from source A is not fetched for source B. |
| Source-specific delays | The interval is applied per source. |
| All sources are processed | Every source in the config list is processed, not just the first one. |
| Empty sources are handled | A source with no new data is skipped gracefully (no crash). |

**Evidence required:** Read the multi-source loop. Verify data is correctly scoped to each source.

### 4. Error Propagation & Cleanup

| Check | Description |
|-------|-------------|
| Config error stops before fetching | If config is invalid, the entry layer reports the error and exits without attempting to fetch. |
| External failure doesn't crash the app | If dispatch to one target fails, other targets are still processed. |
| State save failures handled | If state save fails, the error is logged but processing continues. |
| Cleanup runs on success | After all items are dispatched, resources are cleaned up. |
| Cleanup runs on failure | If dispatch fails mid-way, cleanup still runs. |
| Interrupt is handled | An interrupt during processing stops gracefully. |

**Evidence required:** Read error handling at each stage. Verify `try/finally` or context managers are used where needed.

### 5. Data Integrity

| Check | Description |
|-------|-------------|
| No item loss between stages | Every item that matches criteria is dispatched. No items are silently dropped. |
| Content is preserved | Item content is not truncated or modified incorrectly. |
| Duplicate prevention works | Items with the same identifier are not re-dispatched. |

**Evidence required:** Trace data through each transformation. Check for off-by-one errors or incorrect state management.

---

## Report Output

Write findings to: `.ai/audit/06-data-flow/findings.md` using template `.ai/audit/templates/audit-findings.md`.

**Write the file incrementally — append blocks of ≤100 lines each. Never write the entire report in a single call.**

Use prefix `DF-` for finding IDs.

**`problems-only: true` rules:**
- The report contains **only findings** — real problems discovered during investigation.
- Do NOT include sections, dimensions, or checklist rows where everything is correct.
- If after completing all Runtime Verification steps and all Audit Dimensions, no problems were found, write a single line: `No problems found in this phase.`
- Every finding MUST include:
  1. **Runtime evidence** — traced data flow showing where the break occurs, test failures, missing error handlers.
  2. **Not just:** "violates invariant X" — show the exact stage, the exact data, and the exact consequence (lost item, wrong target, orphaned file).
