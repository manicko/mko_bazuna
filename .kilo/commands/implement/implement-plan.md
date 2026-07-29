---
name: implement-plan
description: Execute the next semantic development plan safely and incrementally following project standards and architecture constraints
agent: implementor
alwaysApply: false
---

## Objective

Execute validated semantic development plan safely while:

- preserving architecture
- following project standards
- maintaining code quality
- minimizing unrelated changes

## Constraints

- DO NOT redesign architecture
- DO NOT change plan scope
- DO NOT perform unrelated refactors
- DO NOT introduce speculative abstractions
- Prefer minimal safe implementation
- Follow existing project patterns and conventions

---

# Workflow

## Step 1 — Study Plan Goals

Study the plan file following the path at the end of this message.

## Step 2 — Preparation

Before implementation study:

- IMPORTANT: `.ai/context/commands.md`
- Semantic structure: `.ai/structure/*`
- `AGENTS.md`
- project architecture
- existing module patterns
- coding conventions
- typing conventions
- testing conventions
- dependency boundaries

Understand:

- project stack
- framework usage patterns
- module responsibilities
- existing abstractions
- validation patterns
- logging/error handling patterns

## Step 3 — Plan Validation

Validate:

- all `depends_on` plans are completed
- plan is still applicable
- semantic targets still exist
- anchors are still stable
- functionality is NOT already implemented
- plan assumptions are still valid
- inspect surrounding code and existing patterns

If already implemented:

- mark plan as completed
- move plan to `done`
- do not reimplement

## Step 4 — Implement Plan

Implement ONLY:

- approved plan scope
- intended semantic changes
- validated modifications

Rules:

- preserve architecture boundaries
- preserve backward compatibility
- preserve dependency integrity
- use semantic targets from plan specification
- follow existing project conventions

Avoid:

- unrelated cleanup
- broad rewrites
- hidden side effects
- speculative improvements

## Step 5 — Write Tests (Non-Trivial Features Only)

Write tests **only** for non-trivial features introduced or significantly changed by the plan.

Tests must:

- validate user-visible behavior
- exercise real workflows (happy path + key edge/error cases)
- detect regressions

Do NOT write tests for:

- trivial getters/setters
- pure plumbing / wiring
- one-liners without meaningful logic
- internal implementation details that have no user-facing effect

Prefer:

- integration / workflow tests over pure unit tests of internals
- assertions on observable outcomes
- existing project test patterns and fixtures

## Step 6 — Validate Code Quality

Run checks depending on what was changed:

**Python files** (`*.py`):

- Lint: `uv run ruff check <affected_files_or_dirs>`
- Type check: `uv run mypy <affected_files_or_dirs>`
- Type check (basedpyright): `uv run basedpyright <affected_files_or_dirs>`

**TypeScript / React files** (`*.ts`, `*.tsx`):

- Type check: `npm run build` (runs `tsc -b`) — from `frontend/` directory
- Lint: `npm run lint` — from `frontend/` directory

Fix only issues directly related to the plan.

## Step 7 — Validate Tests

**Python:** Run `uv run pytest <path>` for relevant test files.

**Frontend:** Run `npm run test` — from `frontend/` directory.

If tests conflict with current architecture → update or remove tests.  
Do not degrade architecture to satisfy outdated tests.

## Step 8 — Completion

- Mark plan file name as done (`*_DONE.md`)

## Step 9 — If Unrelated Problems Are Discovered

1. Check `.ai/audit/problems/`
2. If matching problem exists — extend/update existing problem description if needed
3. If problem does NOT exist — create a new detailed problem report

Include:

- description
- affected modules
- risk
- root cause
- architectural impact
- suggested direction

Do NOT fix unrelated problems during current plan execution unless:

- they directly block plan execution
- they create correctness or safety risks for current plan

## Step 10 — Commit Changes (Conventional Commit)

-  validate related to the task files changes (ignore file changes not related to the task) 
   ```powershell
   git diff HEAD --stat   
   ```
Determine scope from affected module (e.g. `auth`, `api`, `frontend`, `db`)

   ```powershell
   git add <task-related files>
   git commit -m "{type}({scope}): {description}" 
   ```
   **Rules:**
   - Always `git add <specific files>` — never `-A` or `.

### ⛔ GIT RULES
Do not execute any Git command that modifies the repository state beyond the allowed `git add` + `git commit`.  
You are working on the same files and project with other agents.

---

# Expected Result

Result must include:

- completed plan implementation
- validated code changes
- tests for non-trivial features (user-visible behavior, workflows, regression detection)
- passing relevant tests
- passing relevant lint/type checks
- preserved architecture consistency
- plan file marked as done (`*_DONE.md` / `*_DONE.yaml`)
- plan file moved to `.ai/plans/done`
- plan file no longer present in `.ai/plans/todo`
- Git commit created in conventional commit format

Result must NOT include:

- unrelated refactors
- speculative architecture changes
- broad rewrites
- undocumented behavior changes
- tests for trivial code without user-visible effect

---

Plan file path: 
