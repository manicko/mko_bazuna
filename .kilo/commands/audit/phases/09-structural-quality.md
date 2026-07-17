---
name: 09-structural-quality
status: complete
validated: no
executor: auditor
problems-only: true
---

# Phase 09 Audit — Structural Code Quality

## Purpose

This is a **reusable, system-agnostic handbook** for auditing the structural code
quality of ANY codebase — the shape and complexity of functions, methods, and
control flow. It is not tied to a specific language or tool. Apply the discovery
steps and audit dimensions to whatever the system's source actually is, using the
language's equivalent complexity/length tooling where the handbook names a specific
utility.

[Adapt tool invocations to the language in use: where the handbook names a Python
tool (e.g., a complexity analyzer), substitute the equivalent for the target
language/framework. Keep the property being measured — complexity, maintainability,
length, nesting, control-flow patterns.]

## Output Mode

`problems-only: true` — **only problems, bugs, and deviations are documented.**

- **Do NOT** write sections that say "X is correct" or "no issues found in Y".
- **Do NOT** include checklist rows where the check passes — omit them entirely.
- If a dimension has zero findings after investigation, **omit the dimension entirely**.
- Every finding must be actionable: it describes a real problem, its evidence (code/logs/output), and its impact.

---

## Objective

Audit the codebase for **structural code quality** — the shape and complexity of functions, methods, and control flow. This phase targets the "arrow code" / "pyramid of doom" anti-pattern, excessive nesting, bloated functions, and other structural issues that degrade readability and maintainability.

---

## Discovery Stage

Before performing audit checks, discover the structural landscape:

1. **File Inventory** — List all source files with line counts. Identify files exceeding a high line threshold (potential god modules).
2. **Function/Method Inventory** — For each source file, list all functions and methods with their line counts. Identify any function exceeding a reasonable line budget.
3. **Nesting Depth Scan** — For each function/method, measure the maximum nesting depth of control-flow blocks. Identify any function with nesting depth beyond the project's limit.
4. **Control Flow Scan** — Identify confusing control-flow constructs, deeply nested conditional chains, and functions with multiple return points or excessive parameters.

---

## Mandatory Runtime Verification

**Before evaluating any checklist item, you MUST complete these steps. Skip only if a step is impossible — document why.**

### Step R1 — Run Complexity Analyzer

Run the project's cyclomatic-complexity tool across the source tree to get complexity for all functions and methods.

- Record every function above the project's acceptable complexity threshold.
- Record the total average complexity.

### Step R2 — Run Maintainability Index

Run the project's maintainability-index tool across the source tree.

- Record any file below the project's acceptable maintainability rank.
- Record the actual scores.

### Step R3 — Function Length Analysis

For each source file, count lines per function/method (excluding blank lines and comments). Identify any function/method exceeding the project's line budget.

### Step R4 — Nesting Depth Analysis

For each function/method, count the maximum indentation depth of control-flow statements. Identify any function with max nesting depth beyond the project's limit.

### Step R5 — Control Flow Pattern Search

Search for structural anti-patterns:
- confusing loop-else constructs
- conditional chains that could be guard clauses or lookup tables
- functions with excessive return points
- functions with excessive parameters

---

## Audit Scope

All source code files. Focus on structural properties: complexity, length, nesting, and control flow patterns.

---

## Audit Dimensions

### 1. Cyclomatic Complexity

| Check | Description |
|-------|-------------|
| Per-function CC within budget | No function/method should exceed the project's acceptable complexity threshold. |
| Average CC within budget | The average cyclomatic complexity across the project should be within a healthy range. |
| No extreme complexity | No function should have complexity far beyond the threshold (rank D/worst). |

**Evidence required:** Complexity tool output with scores and rankings.

### 2. Nesting Depth

| Check | Description |
|-------|-------------|
| Max nesting depth within limit | No function should have control flow nested more than the project's allowed depth. |
| Guard clauses preferred | Deeply nested conditionals should be replaced with early returns (guard clauses) where possible. |

**Evidence required:** File:line references with nesting depth measurement.

### 3. Function/Method Length

| Check | Description |
|-------|-------------|
| Max lines per function | No function or method should exceed the project's line budget (excluding blank lines and comments). |
| Max lines per file | No source file should exceed the project's file line budget. |

**Evidence required:** File:line references with line counts.

### 4. Control Flow Patterns

| Check | Description |
|-------|-------------|
| No confusing loop-else anti-pattern | Loop-else constructs are often confusing. Use explicit flags or guard variables instead. |
| No excessive return points | Functions should have a limited number of return statements. More indicates complex control flow. |
| No excessive parameters | Functions should have a limited number of parameters. More indicates the function does too much. |
| No arrow code | Deeply nested conditional chains (pyramid of doom) should be refactored using guard clauses, extraction, or polymorphism. |

**Evidence required:** File:line references with pattern description.

### 5. Cognitive Load Indicators

| Check | Description |
|-------|-------------|
| Single responsibility per function | Each function does one thing. If a function has multiple loops, multiple blocks, or multiple branches at the same level, it likely does too much. |
| Linear flow preferred | Functions should read top-to-bottom. Deeply nested trees that branch on multiple conditions are harder to follow than sequential guard clauses. |

**Evidence required:** File:line references with description of cognitive load.

---

## Report Output

Write findings to: `.ai/audit/09-structural-quality/findings.md` using template `.ai/audit/templates/audit-findings.md`.

Use prefix `STR-` for finding IDs.

**`problems-only: true` rules:**
- The report contains **only findings** — real problems discovered during investigation.
- Do NOT include sections, dimensions, or checklist rows where everything is correct.
- If after completing all Runtime Verification steps and all Audit Dimensions, no problems were found, write a single line: `No problems found in this phase.`
- Every finding MUST include:
  1. **Runtime evidence** — complexity tool output, file:line, nesting depth measurement, line counts.
  2. **Not just:** "function is too long" — show the exact function, its length, and the maintenance consequence (e.g., "hard to test in isolation", "multiple responsibilities").
  3. **Concrete refactoring recommendation** — what pattern to apply (extract method, guard clause, lookup table, etc.).

---

## Severity Classification Guide

| Severity | When to use |
|----------|-------------|
| CRITICAL | Function with extreme complexity AND extreme nesting depth — bug-prone, untestable |
| HIGH | Function with very high complexity OR extreme nesting depth OR very high length — hard to maintain |
| MEDIUM | Function above moderate complexity OR moderate nesting OR moderate length — should be refactored |
| LOW | Minor pattern violations (loop-else, many returns) — advisory |

---

## References

- Complexity rankings: A (lowest) through F (highest) as defined by the project's analyzer.
- Industry standard thresholds: function complexity within budget, nesting depth ≤ 3, function length ≤ ~50 lines, file length ≤ ~300 lines (adapt to project conventions).
- Refactoring.Guru: Arrow Code smell, Nested Conditionals smell.
