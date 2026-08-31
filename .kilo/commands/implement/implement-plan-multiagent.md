---
name: implement-plan-multiagent
description: Execute the next semantic development plan safely and incrementally following project standards and architecture constraints
alwaysApply: false
---

# Task: Sequential Plan Implementation

## Objective

Execute the validated development plan safely and sequentially.

The Tech Lead acts only as an **orchestrator**:

* Understand the plan and current codebase context.
* Split the plan into execution blocks and atomic tasks.
* Assign implementation work to `Implementor` agents.
* Ensure blocks are completed sequentially.
* Run a final `Validator`.
* Commit the final changes.

The Tech Lead **never implements code and never performs implementation-level testing or validation**.

---

# Workflow

## Step 1 — Read the Plan

Read the plan file(s) provided at the end of this task.

Understand:

* Overall goal.
* Planned blocks.
* Scope.
* Constraints.
* Dependencies.

Do not start implementation yet.

---

## Step 2 — Collect Architecture Context

**Launch a `Researcher` agent.**

Ask the Researcher to provide a concise overview of the current codebase relevant to the plan:

* Relevant architecture.
* Key files and directories.
* Important components, classes, functions, hooks, services, and tests.
* Existing implementation and testing patterns.
* Current state of the relevant functionality.
* Important dependencies.

The Researcher should provide context only.

Do not ask it to implement anything or create the detailed execution plan.

---

## Step 3 — Process One Execution Block

Split the plan into logical **execution blocks**.

Process **only one block at a time**.

Do not prepare or expand future blocks until the current block is completed.

For the current block:

1. Break it into small atomic implementation tasks.
2. Keep tasks small enough for the Implementor's context window.
3. Simple tasks may be grouped together.
4. Complex work should be split into smaller tasks.

---

## Step 4 — Implement the Current Task

**Launch an `Implementor` agent.**

Give the agent the current task or a small group of closely related tasks.

The Implementor is responsible for the **complete implementation cycle**:

* Understand the assigned task.
* Modify the code.
* Add or update tests where required.
* Run relevant tests.
* Run relevant lint/type checks.
* Validate the implementation according to:
  `C:\py_dev\mko_bazuna\.kilo\rules\commands.md`
* Fix any problems found during validation.
* Return only after the assigned task is implemented and locally validated.

For simple work, the Implementor may receive several related tasks or the entire current block.

For complex work, assign only a manageable subset.

**Never run Implementors in parallel.**

The Tech Lead must not implement code or perform these checks itself.

---

## Step 5 — Continue Within the Current Block

After an Implementor finishes:

* Review only whether the assigned task was completed.
* If the task is complete, proceed to the next atomic task.
* If additional work is required, assign the required task to an Implementor.

Continue until the **entire current block** is implemented and locally validated by its Implementor(s).

Then move to the next block.

---

## Step 6 — Repeat for All Blocks

Repeat Steps 3–5 until every execution block in the plan is complete.

Always maintain sequential execution:

`Block → Tasks → Implementor → Local Validation → Next Task → Next Block`

Do not skip blocks or implement future blocks early.

---

## Step 7 — Final Validation

After all blocks are complete:

**Launch a `Validator` agent.**

Ask the Validator to verify the complete implementation against:

* The original plan.
* The intended functionality.
* Relevant architecture and project conventions.
* Tests and test coverage.
* Relevant lint/type checks.
* Regressions.
* Unrelated changes.
* Any missing or incomplete requirements.

The Validator should perform the **final repository-level validation** and report whether the implementation is ready to commit.

If the Validator finds problems:

1. Do not fix them directly.
2. Create the smallest necessary implementation task.
3. Launch an `Implementor`.
4. Let the Implementor implement and locally validate the fix.
5. Run the `Validator` again.

Do not commit until the Validator confirms the implementation is ready.

---

## Step 8 — Mark the Plan as Done

After successful final validation:

* Rename the plan file to `*_DONE.md` or `*_DONE.yaml`.
* Move it to `.ai/plans/done`.
* Ensure it is no longer present in `.ai/plans/todo`.

---

## Step 9 — Commit Changes

Only after the final Validator passes, create a Conventional Commit:

```powershell
git add <task-related files>
git commit -m "{type}({scope}): {description}"
```

Rules:

* Use specific file paths with `git add`.
* Never use `git add -A` or `git add .`.
* Do not include unrelated changes from other agents.

---

# Constraints

* Do not redesign the architecture.
* Do not change the plan scope.
* Do not perform unrelated refactors.
* Do not introduce speculative abstractions.
* Prefer minimal, safe implementation.
* Follow existing project patterns and conventions.
* Process one block at a time.
* Keep Implementor tasks small and focused.
* Never run Implementors in parallel.
* The Tech Lead never implements code.
* The Tech Lead does not perform implementation-level testing, linting, or validation.
* `Implementor` owns implementation and local validation.
* `Validator` owns final repository-level validation.
* The Tech Lead owns orchestration and the final commit only.

---

# Expected Result

The final result must include:

* Complete implementation of the plan.
* Implementation-level validation performed by Implementors.
* Passing relevant tests.
* Passing relevant lint/type checks.
* Final validation performed by the Validator.
* Preserved architecture and project conventions.
* No unrelated refactors or speculative changes.
* Plan file marked as done.
* Plan file moved to `.ai/plans/done`.
* Plan file removed from `.ai/plans/todo`.
* Conventional Git commit created only after final validation passes.

---

# Plan File

