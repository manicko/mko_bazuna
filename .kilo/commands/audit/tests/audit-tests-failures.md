---
name: audit-tests-failures

description: Analyze failing tests, determine whether failures indicate outdated tests or real implementation defects, and produce an actionable remediation plan

agent: tech-lead                                                                                                                                                                                                                                             

alwaysApply: false

---

# Task: Failing Tests Audit

## Goal

Analyze failing tests, identify the root cause of each failure, and determine whether:

1. the test is outdated and no longer matches the current architecture or intended behavior;
2. the test itself should be updated or removed;
3. the failure exposes a real defect in the implementation that requires code changes.

The orchestrator must delegate detailed investigation to specialized agents and synthesize their findings into an actionable plan.

---

# Workflow

## Step 1. Analyze the Failing Tests

**Goal:** Establish the scope and current state of test failures.

**Launch Agent:** `test-engineer`

Run the relevant test suite and collect:

- failing tests;
- failure messages and stack traces;
- affected modules;
- failure frequency/reproducibility;
- related fixtures, mocks, and dependencies.

Group related failures where they share the same underlying cause.

Return a concise structured report.

---

## Step 2. Investigate Root Causes

**Goal:** Determine why each group of tests is failing.

**Launch Agent:** `researcher`

For each failure group, inspect:

- current implementation;
- current architecture;
- test assumptions;
- related models, APIs, services, and workflows;
- relevant specifications or development plans;
- recent architectural changes where available.

Determine whether the test expectation still matches the intended current behavior.

Return evidence-based findings.

---

## Step 3. Classify the Failures

**Goal:** Decide whether each failure represents an outdated test or a real implementation problem.

**Launch Agent:** `test-engineer`

Classify each failure as one of:

### `OUTDATED_TEST`

The implementation is correct and the test relies on obsolete behavior, architecture, API, fixture, or assumptions.

Recommended action:

- update the test if the scenario remains valuable;
- remove the test if it is redundant or no longer meaningful.

### `REAL_DEFECT`

The test correctly identifies behavior that violates the current requirements, contracts, or architecture.

Recommended action:

- fix the implementation;
- keep or strengthen the test as regression coverage.

### `UNCERTAIN`

Available evidence is insufficient to determine the correct behavior.

Identify exactly what information is missing.

Do not guess.

---

## Step 4. Create the Remediation Plan

**Goal:** Convert the analysis into concrete implementation decisions.

**Launch Agent:** `planner`

For each failure group, produce:

- affected tests;
- root cause;
- classification;
- evidence;
- required action;
- files/components likely affected;
- priority;
- dependencies or risks.

Separate clearly:

```text
Update tests
Remove tests
Fix implementation
Needs clarification
````

Output path: `.ai/plans`

Do not modify code or tests.

---

# Constraints

* Do not assume that a failing test means the implementation is broken.
* Do not assume that a failing test is obsolete merely because the architecture changed.
* Treat current requirements and architecture as the source of truth.
* Preserve tests that protect valid business behavior.
* Do not remove a test without explaining why its scenario is no longer meaningful.
* Do not weaken assertions merely to make tests pass.
* Do not change implementation code during the audit.
* Group failures that share the same root cause.
* Base classifications on evidence from the implementation, tests, and relevant project documentation.
* Mark a case `UNCERTAIN` when the intended behavior cannot be established reliably.

---

# Expected Result

A concise, evidence-based remediation plan that clearly identifies:

* which tests should be updated;
* which tests should be removed;
* which failures expose real implementation defects;
* which cases require clarification;

with enough evidence for the implementation agents to execute the required changes safely.

