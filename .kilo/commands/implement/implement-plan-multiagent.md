---
name: implement-plan-multiagent
description: Execute the next semantic development plan safely and incrementally using a strict multi-agent chain per block
alwaysApply: false
---

# Task: Sequential Plan Implementation

## Objective

Execute the validated development plan safely and sequentially.

The Tech Lead acts only as an **orchestrator**:
- Understand the plan and codebase context
- Drive the required agent chain
- Ensure sequential completion
- Run final quality check
- Create the final commit

The Tech Lead **never implements code** and never performs implementation-level testing or validation.

---

# Workflow

## 1. Decompose the Plan

**Launch a `Planner` agent.**

Ask the Planner to:
- Read the plan file(s) provided at the end of this task
- Split the plan into logical **execution blocks**
- Provide a concise high-level description of each block (goal, scope, main outcomes)

Do not start implementation yet.  
Use the Planner’s block list as the single source of truth for the rest of the workflow.

---

## 2. Process Each Block (strict agent chain)

Process **only one block at a time**.  
Do not prepare or expand future blocks until the current block is finished.

For the **current block** run the following chain in order:

### 2.1 Auditor
Launch an `Auditor` agent.  
Ask it to study the **current code and architecture** relevant to this block only:
- Key modules, classes, functions, services, configs
- Existing patterns and constraints
- Current state of the related functionality

### 2.2 Researcher
Launch a `Researcher` agent.  
Ask it to study **modern best practices** for solving the block’s task, grounded in the current architecture.

Important:
- Treat any solution proposed in the plan/specification as **one possible option only**
- Do **not** treat the plan’s solution as the default until the Researcher confirms it is appropriate
- Prefer approaches that fit the existing architecture and minimize risk

### 2.3 Researcher (re-check) — only if needed
If the previous Researcher found **multiple viable options**:
- Launch a second `Researcher` to re-evaluate and select the best option
- If only one clear option exists, **skip this step**

### 2.4 Implementor
Launch an `Implementor` agent with the chosen approach and the concrete tasks for the block.

The Implementor owns the full local cycle:
- Implement the changes
- Add/update tests where required
- Run relevant tests, lint, and type checks
- Fix any issues found
- Return only when the block is implemented and locally validated

Never run Implementors in parallel.  
Keep tasks small enough for the Implementor’s context.

After the Implementor finishes the current block, move to the next block and repeat the full chain (2.1 → 2.4).

---

## 3. Final Quality Check

After **all blocks** are complete:

Launch an `Auditor` agent to perform a final quality review of the entire implementation:
- Completeness against the plan
- Architectural fit and project conventions
- Presence of regressions or unrelated changes
- Overall readiness

If problems are found:
1. Create the smallest necessary fix task
2. Launch an `Implementor` to fix and locally validate
3. Re-run the final Auditor

Do not proceed to commit until the final Auditor confirms readiness.

---

## 4. Commit

Only after the final Auditor passes, create a Conventional Commit:

```powershell
git add <task-related files>
git commit -m "{type}({scope}): {description}"
```

Rules:
- Use specific file paths with `git add`
- Never use `git add -A` or `git add .`
- Do not include unrelated changes

Optionally mark the plan as done (rename to `*_DONE.md` / move to `.ai/plans/done`).

---

# Constraints

- Do not redesign architecture or expand scope
- Do not perform unrelated refactors
- Prefer minimal, safe, incremental changes
- Follow existing project patterns
- Process one block at a time
- Tech Lead never implements code
- `Implementor` owns implementation + local validation
- Final `Auditor` owns repository-level quality check
- Tech Lead owns orchestration and the final commit only

---

# Expected Result

- Plan decomposed into clear execution blocks by Planner
- Complete implementation of the plan
- Per-block agent chain executed as specified
- Local validation by Implementors
- Final quality check by Auditor
- Conventional Git commit created only after final approval
- Architecture and conventions preserved

---

# Plan File
