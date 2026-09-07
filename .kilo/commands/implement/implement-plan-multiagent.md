---
name: implement-plan-multiagent
description: Execute a validated development plan incrementally using a sequential multi-agent workflow per block
alwaysApply: false
---

# Task: Sequential Plan Implementation

## Objective

Execute the development plan safely, one block at a time.

The Tech Lead is **orchestrator only**:

* Coordinate agents
* Pass concise handoffs
* Ensure sequential execution
* Commit completed blocks
* Run final validation

The Tech Lead never implements code or performs implementation-level validation.

---

# Workflow

## 1. Decompose Plan

Launch a `Planner`.

Ask it to:

* Read the plan file(s)
* Split the plan into logical execution blocks
* Identify dependencies and execution order
* Describe each block briefly

Do not implement yet.

---

## 2. Process Blocks

Process **one block at a time**.

### 2.1 Auditor

Launch `Auditor` for the current block.

It analyzes only the relevant:

* Code and architecture
* Existing patterns and constraints
* Current implementation
* Risks

Return a concise handoff.

### 2.2 Planner

Launch `Planner` with the block and Auditor handoff.

It must:

* Convert the specification into concrete requirements
* Describe viable implementation options
* Note key trade-offs and open questions
* **Not choose the final implementation approach when technical uncertainty exists**
* Explicitly state when `Researcher` is required, especially for:

  * Modern/current best practices
  * Multiple viable approaches
  * Framework/library behavior
  * Significant architectural, security, performance, or compatibility decisions

Planner output is **decision input, not the final technical decision**.

### 2.3 Researcher — only when needed

Launch `Researcher` when Planner identifies unresolved technical questions or multiple viable approaches.

Researcher:

* Evaluates the proposed options
* Verifies relevant current best practices
* Assesses important risks and trade-offs
* Recommends the appropriate approach for the existing architecture

Skip only when the approach is clear and requires no meaningful research.

### 2.4 Implementor

Launch `Implementor` with the block, Auditor handoff, Planner output, and Researcher findings if applicable.

Implementor owns the local cycle:

* Implement
* Add/update tests
* Run relevant tests, lint, and type checks
* Fix failures
* Return only when locally validated

Never run Implementors in parallel.

### 2.5 Commit

After successful implementation:

* Commit only the current block
* Use a Conventional Commit
* Never include unrelated changes

```powershell
git add <task-related files>
git commit -m "{type}({scope}): {description}"
```

Then continue to the next block.

---

## 3. Final Validation

After all blocks are committed:

Launch `Validator` for repository-level validation:

* Completeness against the plan
* Integration between blocks
* Architectural consistency
* Regressions
* Unrelated changes
* Overall readiness

If issues are found:

1. Create the smallest fix task
2. Launch `Implementor`
3. Validate locally
4. Commit the fix
5. Re-run `Validator`

Finish only after `Validator` passes.

---

# Constraints

* One block at a time
* No parallel Implementors
* No unnecessary research
* No architecture redesign or unrelated refactoring
* Prefer minimal, safe changes
* Keep agent handoffs concise
* Commit after every block
* Planner proposes; Researcher evaluates when needed
* Tech Lead orchestrates only
* Implementor owns implementation and local validation
* Validator runs only at the end

---

# Expected Result

* Clear execution blocks
* Current architecture understood before detailed planning
* Research used only when necessary
* Each block implemented, validated, and committed separately
* Final repository validation completed
* Architecture and project conventions preserved

---

# Plan File

