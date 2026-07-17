---
name: 07-quality
status: complete
validated: no
executor: auditor
problems-only: true
---

# Phase 08 Audit — Code Quality, Security & Maintainability

## Purpose

This is a **reusable, system-agnostic handbook** for auditing code quality,
security, and maintainability across the source of ANY project. It is not tied to a
specific language feature set or project convention. Apply the discovery steps and
audit dimensions to whatever the system's conventions and source actually are,
adapting concrete names to the implementation at hand.

## Output Mode

`problems-only: true` — **only problems, bugs, and deviations are documented.**

- **Do NOT** write sections that say "X is correct" or "no issues found in Y".
- **Do NOT** include checklist rows where the check passes — omit them entirely.
- If a dimension has zero findings after investigation, **omit the dimension entirely**.
- Every finding must be actionable: it describes a real problem, its evidence (code/logs/output), and its impact.

---

## Discovery Stage

Before performing audit checks, discover the codebase quality landscape:

1. **Codebase Structure** — Map all source files, their sizes, and responsibilities. Identify any files that are unusually large (potential god modules).
2. **Import Graph** — Map all imports. Identify circular imports, unused imports, and cross-layer imports.
3. **Quality Patterns** — Search for forbidden output calls, bare exception catches, leftover `TODO`/`FIXME` comments, and other code smells.
4. **Security Surface** — Identify all places where external input is processed (config values, API responses, file paths).

---

## Mandatory Runtime Verification

**Before evaluating any checklist item, you MUST complete these steps. Use the commands provided in the project's commands file. Skip only if a step is impossible — document why.**

### Step R1 — Linter and Type Checker

Run the project's configured linter and type checker commands.

- Record all errors and warnings. Each is evidence.

### Step R2 — Run Test Suite

Run the complete test suite.

- Record pass/fail counts and failure output.

### Step R3 — Dead Code Search

Search for unreachable or unused code:

- Functions/methods defined but never called outside tests.
- Imported modules that are never used.
- Variables assigned but never read.
- Conditional branches that are always true/false.

Record each instance with file:line.

### Step R4 — Security Search

Search the codebase for:

- Hardcoded secrets (API keys, tokens, passwords).
- Forbidden output calls (e.g., raw `print()` where a logger is mandated).
- Bare `except:` clauses.
- Logging calls that might log sensitive data (credentials, tokens).

---

## Audit Scope

All source code files. Code quality, type safety, security, maintainability, project convention compliance.

---

## Audit Dimensions

### 1. Code Quality

| Check | Description |
|-------|-------------|
| No forbidden output calls | All output uses the project's logging mechanism. Raw console output is forbidden in production code. |
| No bare `except:` | All exceptions are caught with specific types. |
| Type hints everywhere | All public functions and methods have type hints on parameters and return values. |
| No `any`/untyped types | Type annotations are specific, not generic `Any`. |
| Small functions | Functions are focused and short. No function exceeds a reasonable line budget without clear justification. |
| Clear naming | Variable, function, and class names are descriptive and consistent. |
| Single language for text | All comments, docstrings, logs, and error messages use one consistent language. |

**Evidence required:** Linter output. Manual code review. Search for forbidden output, bare excepts, and missing type hints.

### 2. Security

| Check | Description |
|-------|-------------|
| No hardcoded secrets | No API keys, tokens, passwords, or credentials in source code. |
| Credentials not logged | Sensitive values are never logged. |
| Path traversal prevention | File paths from config/user input are validated before use. |
| Error messages don't leak internals | Error messages to users don't include stack traces, file paths, or internal details. |
| Config file permissions | Credential files are stored in the user's private config directory. |

**Evidence required:** Search for hardcoded secrets. Read error-handling code. Check logger calls near sensitive data.

### 3. Maintainability

| Check | Description |
|-------|-------------|
| No dead code | Every function and class is used. No orphaned modules. |
| No overengineering | Abstractions match the project's complexity. No unnecessary design patterns. |
| Consistent conventions | Naming, formatting, and architectural patterns are consistent across the codebase. |
| Docstrings on public APIs | All public classes and functions have docstrings. |
| Comments for non-trivial logic | Complex logic is explained with comments. Obvious code is not over-commented. |

**Evidence required:** Dead code search results. Code review for overengineering. Check docstring coverage.

### 4. Project Convention Compliance

| Check | Description |
|-------|-------------|
| Typed models for all data | Configuration and data structures use typed models, not raw dicts. |
| Enum for fixed values | Fixed-value fields use enums, not plain strings. |
| Standard logger pattern | Every module uses the standard logger pattern. |
| Path resolution via utilities | No hardcoded paths. All paths use the project's path resolution utilities. |
| Layer separation | Entry → Service → Core. No cross-layer imports. |

**Evidence required:** Search for raw dict usage, plain string constants, forbidden output, hardcoded paths, and cross-layer imports.

### 5. Dependency Hygiene

| Check | Description |
|-------|-------------|
| No unused imports | Every import is used. |
| No circular imports | The import graph is acyclic. |
| Dependencies are justified | Every dependency in the manifest is actually used in the code. |
| No cross-package leakage | The project does not import from unrelated packages. |

**Evidence required:** Linter output for unused imports. Import graph analysis. Compare manifest dependencies against actual imports.

---

## Report Output

Write findings to: `.ai/audit/08-quality/findings.md` using template `.ai/audit/templates/audit-findings.md`.

Use prefix `QLT-` for finding IDs.

**`problems-only: true` rules:**
- The report contains **only findings** — real problems discovered during investigation.
- Do NOT include sections, dimensions, or checklist rows where everything is correct.
- If after completing all Runtime Verification steps and all Audit Dimensions, no problems were found, write a single line: `No problems found in this phase.`
- Every finding MUST include:
  1. **Runtime evidence** — linter output, grep results, file:line of problematic code.
  2. **Not just:** "violates invariant X" — show the exact code and the exact maintenance/security consequence.
