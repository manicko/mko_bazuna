---
name: bugfix
description: Execute the next bugfix safely and incrementally following project standards and architecture constraints
agent: debug
alwaysApply: false
---

# Workflow

## Step 1 — Study the Bug

Summarize the debug info and problem description provided at the end of this prompt.
Do not argue on the workflow, just follow.

## Step 2 — Preparation (Researcher)

Use <task> tool to launch one or more <researcher> agents to:
1. Investigate the project architecture relevant to the bug
2. Research modern best practices for solving this class of problem within the current architecture

## Step 3 — Select Best Route (if multiple options)

If multiple viable approaches exist, launch a Researcher agent to choose the preferred path that:

- matches modern standards
- fits the existing architecture and project requirements
- is maintainable and supports long-term evolution

Prefer a solid, future-proof solution over a quick and dirty patch.

## Step 4 — Risk & Complexity Assessment (Researcher)
Use <task> tool to launch <researcher> agent to assess risks of the fix and potential architectural impact.

### If high risk or complex only

- **4.1** Use <task> tool to launch <researcher> to deepen analysis of risks and modern practices under the current architecture
- **4.2** Use <task> tool to launch <planner>  agent to produce a fix plan (including tests and docs) and save it to  
  `.ai/plans/{Number}_{problem_name}_fix_plan.md`
- **4.3** Use <task> tool to launch <validator>  agent to review the plan for modern practices, maintainability, and long-term quality (goal: solid foundation, not a quick patch)
- **4.4** Repeat 4.2 if the plan needs refinement

## Step 5 — Implementation (Implementor)

Use <task> tool to launch <implementor> agent to:

1. Implement the approved fix (or the selected route if no formal plan was required)
2. Run quality checks for changed code:

   **Python (`*.py`):**
   - Lint: `uv run ruff check <affected_files_or_dirs>`
   - Type check: `uv run mypy <affected_files_or_dirs>`
   - Type check: `uv run basedpyright <affected_files_or_dirs>`
   - Tests: `uv run python -m pytest pytest <relevant_path>`

   **TypeScript / React (`*.ts`, `*.tsx`):**
   - Type check: `npm run build` (from `frontend/`)
   - Lint: `npm run lint` (from `frontend/`)
   - Tests: `npm run test` (from `frontend/`)

   If tests conflict with current architecture → update or remove them.  
   Do not degrade architecture to satisfy outdated tests.

3. Create a conventional commit:

   ```bash
   git add <specific-files>
   # skip if git status --porcelain is empty
   git commit -m "{type}({scope}): {short_description}" -m "Task: {TASK_FILE_NAME}"
   ```

   Type: `fix` (preferred), `feat`, `refactor`, `test`, or `chore`  
   Scope: affected module (e.g. `auth`, `api`, `frontend`, `db`)

### Git Rules (strict)

**Always forbidden** (no exceptions):

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

- To undo something: edit files and commit a new fix. Never use git to “go back”.
- If a forbidden command is absolutely required → ask the user via `question` tool and **wait for explicit “yes”**.
- Move/rename task files with PowerShell only (`Rename-Item`, `Move-Item`). Never `git mv` / `git rm`.

---

# Expected Result

- Correct, minimal, architecture-preserving fix
- Follow existing project patterns and conventions
- Relevant tests updated/added and passing
- Lint and type checks passing for changed code
- Conventional commit created
- Prefer minimal, correct, future-proof fixes over quick patches


---

Task / debug info:
