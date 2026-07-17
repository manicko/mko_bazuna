---
name: implement-task
description: Execute the next semantic development task safely and incrementally following project standards and architecture constraints
agent: implementor
alwaysApply: false
---


## Objective

Execute validated semantic development tasks safely while:
- preserving architecture
- following project standards
- maintaining code quality
- minimizing unrelated changes

## Constraints

- DO NOT redesign architecture
- DO NOT change task scope
- DO NOT perform unrelated refactors
- DO NOT introduce speculative abstractions
- Prefer minimal safe implementation
- Follow existing project patterns and conventions

---

# Workflow


## Step 1 — Study  Task Goals

Take the first task-file by execution order from:
- `.ai/tasks/todo`


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


## Step 3 — Task Validation

Validate:
- all `depends_on` tasks are completed
- task is still applicable
- semantic targets still exist
- anchors are still stable
- functionality is NOT already implemented
- task assumptions are still valid
- inspect surrounding code and existing patterns

If already implemented:
- mark task as completed
- move task to `done`
- do not reimplement

---

## Step 4 — Implement Task

Implement ONLY:
- approved task scope
- intended semantic changes
- validated modifications

Rules:
- preserve architecture boundaries
- preserve backward compatibility
- preserve dependency integrity
- use semantic targets from task specification
- follow existing project conventions

Avoid:
- unrelated cleanup
- broad rewrites
- hidden side effects
- speculative improvements

---

## Step 5 — Validate Code Quality

Run checks depending on what was changed:

**Python files** (`*.py`):
- Lint: `uv run ruff check <affected_files_or_dirs>`
- Type check: `uv run mypy <affected_files_or_dirs>`
- Type check (basedpyright): `uv run basedpyright <affected_files_or_dirs>`

**TypeScript / React files** (`*.ts`, `*.tsx`):
- Type check: `npm run build` (runs `tsc -b`) — from `frontend/` directory
- Lint: `npm run lint` — from `frontend/` directory

Fix only issues directly related to the task.

---

## Step 6 — Validate Tests

**Python:** Run `uv run pytest <path>` for relevant test files.
**Frontend:** Run `npm run test` — from `frontend/` directory.

If tests conflict with current architecture → update or remove tests.
Do not degrade architecture to satisfy outdated tests.

---

## Step 7 — Completion
- Mark task file name as done (`*_DONE.yaml`)
- Move file to `.ai/tasks/done`
- Ensure the file is no more presented in `.ai/tasks/todo`

---

## Step 8 — If unrelated problems are discovered

1. Check `.ai/audit/problems/`
2. If matching problem exists extend/update existing problem description if needed
3. If problem does NOT exist create a new detailed problem report

Include:
- description
- affected modules
- risk
- root cause
- architectural impact
- suggested direction

Do NOT fix unrelated problems during current task execution unless:
- they directly block task execution
- they create correctness or safety risks for current task

---

## ⛔ GIT RULES — FORBIDDEN FOREVER

**These git commands are ALWAYS forbidden. No exceptions. Ever.**

```
git reset
git checkout
git clean
git stash
git rebase
git push --force / git push -f
git branch -D
git tag -d
git commit --amend
git revert
git mv
git rm
git cherry-pick
```

**If you need to undo something — just edit the files and commit a fix. Never use git to "go back".**

**If you absolutely must use a forbidden command — ask the user first via `question` tool. WAIT for "yes".**

Task files are moved with PowerShell only: `Rename-Item`, `Move-Item`. Never `git mv`/`git rm`.

---

## Step 9 — Commit Changes

1. `git add -A` (or `git add <specific-files>`)
2. Check `git status --porcelain` — if empty, skip commit
3. Determine commit type from task content: `feat` (new feature), `fix` (bug fix), `refactor` (restructure), `test` (tests only), `chore` (other)
4. Determine scope from affected module (e.g. `auth`, `api`, `frontend`, `db`)
5. `git commit -m "{type}({scope}): {short_description}" -m "Task: {TASK_FILE_NAME}"`

**FORBIDDEN in this step:** `git reset`, `git commit --amend`, `git stash`, `git checkout --`, `git clean`

---
# Expected Result

Result must include:
- completed task implementation
- validated code changes
- passing relevant tests
- passing relevant lint/type checks
- preserved architecture consistency
- Mark task file name as done (`*_DONE.yaml`)
- Ensure file task in `.ai/tasks/done`
- Ensure the file is no more presented in `.ai/tasks/todo`
- Git commit created (conventional commit format)

Result must NOT include:
- unrelated refactors
- speculative architecture changes
- broad rewrites
- undocumented behavior changes

