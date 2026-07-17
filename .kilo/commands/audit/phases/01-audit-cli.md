---
name: 01-cli
status: complete
validated: no
executor: auditor
problems-only: true
---

# Phase 01 Audit — CLI Entry Point & Command Layer

## Purpose

This is a **reusable, system-agnostic handbook** for auditing the command-line
interface (or equivalent front-end entry layer) of ANY application. It is not tied
to a specific framework, language, or library. Apply the discovery steps and audit
dimensions to whatever entry-point mechanism the system actually uses (argument
parser, command bus, web controller, etc.), adapting concrete names to the
implementation at hand.

## Output Mode

`problems-only: true` — **only problems, bugs, and deviations are documented.**

- **Do NOT** write sections that say "X is correct" or "no issues found in Y".
- **Do NOT** include checklist rows where the check passes — omit them entirely.
- If a dimension has zero findings after investigation, **omit the dimension entirely**.
- Every finding must be actionable: it describes a real problem, its evidence (code/logs/output), and its impact.

---

## Discovery Stage

Before performing audit checks, discover the entry layer's structure in ANY system:

1. **Entry Point Discovery** — Locate the application entry point and its framework (argument parser, CLI framework, route controller, etc.). Identify all registered commands/operations, their options/flags/parameters, and map the entry-to-service call chain.
2. **Command Layer Mapping** — For each command/operation: what service does it invoke? What configuration does it require? How are errors caught and presented to the user?
3. **Dependency Flow** — Trace how the entry layer imports from the service/core layer. Verify no reverse imports (core importing from the entry layer).
4. **Runtime Behavior** — How does the application start? How are asynchronous operations (if any) bridged to the entry context? How is the runtime loop or request lifecycle managed?

---

## Mandatory Runtime Verification

**Before evaluating any checklist item, you MUST complete these steps. Use the commands provided in the project's commands file. Skip only if a step is impossible — document why.**

### Step R1 — Import Verification

Attempt to import the entry-point module and its immediate dependencies. Verify no dependency is missing or broken.

- Capture traceback on failure. A broken import is CRITICAL.
- Verify the entry layer and all modules it depends on are importable.

### Step R2 — Help / Usage Verification

Run each command/operation with its help or usage flag. Verify:

- All commands produce usage output without errors.
- All options/flags/parameters are documented.
- No crashes on usage display.

### Step R3 — Linter and Type Checker

Run the project's configured linter and type checker commands.

- Record exit codes and output.
- Any errors or warnings are direct evidence.

### Step R4 — Run Test Suite

Run the project's test suite, focusing on entry-layer tests.

- Record pass/fail counts, skipped tests, and failure output.
- Any failing test is evidence of a real bug.

---

## Audit Scope

Entry point, command/operation definitions, option/parameter parsing, error presentation, and the boundary between the entry layer and the service/core layers.

---

## Audit Dimensions

### 1. Command Layer Integrity

| Check | Description |
|-------|-------------|
| Handlers are thin | Entry handlers contain only argument parsing, service invocation, and error display — no business logic. |
| No business logic in entry layer | Calculations, data transformations, and external calls live in the service layer, not in handlers. |
| Consistent error handling | Every command catches exceptions and presents user-friendly messages. No raw tracebacks leak to the user. |
| All commands functional | Every registered command can be invoked (with usage/help at minimum) without crashing. |
| Options validation | Invalid options/flags are rejected with clear error messages, not silent defaults. |

**Evidence required:** Read each handler. Verify it delegates to a service/core function rather than implementing logic inline. Run usage/help for each command.

### 2. Layer Boundary Enforcement

| Check | Description |
|-------|-------------|
| Entry imports only from core/service | The entry layer never imports from unrelated modules or implements its own business logic. |
| No reverse imports | Core/service modules do not import from the entry layer. |
| Dependency direction | Dependencies flow: Entry → Service → Core (models, utils, readers). No circular imports. |

**Evidence required:** Trace import chains. Search for any imports of the entry layer inside core/service modules.

### 3. Async/Sync Bridge Correctness

| Check | Description |
|-------|-------------|
| Async operations properly bridged | If the service layer uses asynchronous operations, the entry layer manages the runtime loop correctly (e.g., a single top-level runner). |
| No runtime loop conflicts | No nested loops, no re-entry into an already-running loop. |
| Graceful interruption | Interrupt signals (e.g., Ctrl+C) are caught and handled cleanly without stack traces. |

**Evidence required:** Read the entry point and the service's synchronous wrapper. Trace how the runtime loop is used. Check for interrupt handling.

### 4. User Experience

| Check | Description |
|-------|-------------|
| Progress feedback | Long-running operations show progress indicators or status messages. |
| Error messages are actionable | Messages tell the user what went wrong and what to do next. |
| Exit codes are meaningful | Success returns a success code, errors return non-zero. Different error types use distinct codes where appropriate. |

**Evidence required:** Read error-handling code. Trigger error conditions (e.g., missing config) and verify the output is helpful.

---

## Report Output

Write findings to: `.ai/audit/01-cli/findings.md` using template `.ai/audit/templates/audit-findings.md`.

**Write the file incrementally — append blocks of ≤100 lines each. Never write the entire report in a single call.**

Use prefix `CLI-` for finding IDs.

**`problems-only: true` rules:**
- The report contains **only findings** — real problems discovered during investigation.
- Do NOT include sections, dimensions, or checklist rows where everything is correct.
- If after completing all Runtime Verification steps and all Audit Dimensions, no problems were found, write a single line: `No problems found in this phase.`
- Every finding MUST include:
  1. **Runtime evidence** — import errors, CLI output, linter errors, test failures.
  2. **Not just:** "violates invariant X" — show the exact code that violates it and the exact consequence.
