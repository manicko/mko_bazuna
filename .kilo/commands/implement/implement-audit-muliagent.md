---
name: implement-audit-multiagent
description: Execute validated audit findings safely — assess remediation paths, implement incrementally, define test/docs coverage, and perform final validation
alwaysApply: false
---

# Workflow

Do not argue on the workflow, just follow.

## Step 1 — Decompose Findings

Launch a `Planner` agent.

Ask it to:
- Read the validated audit report
- Group findings into logical **work items** / execution blocks
- Identify dependencies and execution order
- Keep each work item small and coherent
- Describe each block briefly
- **Do not choose implementation approaches**

The Planner output is the execution plan `ai\plans\{next-free-num}-{plan_name}.md`

## 2. Process Blocks

Process **one block at a time**.

### 2.1 — Resolve Remediation Path

Launch a `Researcher` with:

- The finding and audit recommendation
- The Planner  **work item** / execution block

Ask it to:

- Inspect the relevant current architecture and implementation
- Assess implementation, rollout, regression, and compatibility risks
- Critically evaluate the audit recommendation
- Identify viable alternatives when relevant
- Verify current and modern best practices
- Select the **best implementation path** for maintainability, future evolution, and project conventions
- Keep the scope minimal and avoid speculative redesign

Return a concise implementation decision for the `Implementor`.

### 2.2 — Implementation

Launch Implementor` for the current work item.
Never run Implementors in parallel.

Provide:

- Exact scope
- Researcher's selected implementation path
- Relevant constraints and risks

Implementor owns the local cycle:

- Implement the fix
- Add obvious regression tests
- Run relevant tests, lint, and type checks
- Fix failures
- Return only when locally validated
- Commit only the current work item. 

```bash
git add <specific-files>
git commit -m "fix({scope}): {short_description}" -m "Task: {TASK_FILE_NAME}"
```
You are working with other agents in parallel if you see changes not done by you - it is normal.
Never ran `git reset`, `git checkout`

To undo: edit and create a new commit. Never rewrite history.

## Step 3 — Test & Documentation Plan

After **all remediation paths are resolved**, launch a `Researcher`.

Ask it to create a consolidated matrix:

`.ai/plans/{Number}_{audit_phase}_fix_matrix.md`

For every work item, define:

* **Tests required** — happy path, key edge/error cases; prefer integration over pure unit tests
* **Docs required** — exact files/sections, or `none`

Base the matrix on the selected remediation paths and the actual repository structure.

## Step 4 — Test & Documentation Implementation

Launch **one `Implementor`** to execute the matrix.

It must:

* Add or complete all required tests
* Update all required documentation
* Run relevant tests, lint, and type checks
* Fix failures
* Return only when locally validated

Then commit the test/documentation changes separately.

## Step 5 — Final Validation

Launch a `Validator` after all implementation and documentation changes.

Check:

* All validated findings addressed
* Implementation matches selected remediation paths
* Tests and quality gates
* Integration and regressions
* Documentation completeness
* No unrelated changes

## Step 6 If issues are found:

1. Create the smallest fix task
2. Launch `Implementor`
3. Validate locally
4. Commit the fix



---

# Constraints

* Planner decomposes; it does not choose technical solutions
* Researcher evaluates audit recommendations and selects remediation paths
* Research only when useful to resolve technical uncertainty
* One work item at a time
* Never run Implementors in parallel
* Prefer minimal, maintainable, future-proof fixes
* No unrelated refactors or speculative redesign
* Keep agent handoffs concise
* Tech Lead only orchestrates and commits

---

# Expected Result

* Validated findings decomposed into coherent work items
* Each remediation path reviewed against current architecture and modern practices
* One appropriate implementation path selected per work item
* Each fix implemented, locally validated, and committed separately
* Consolidated test/documentation matrix created
* Required tests and documentation implemented and committed
* Final repository validation passed
* No unrelated changes

---

# Audit Report

Path / content provided at the end of this task.

