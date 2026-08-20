---
name: audit-bad-tests

description: Audit test quality, identify obsolete or low-value tests, and recommend test improvements or missing coverage using multi-agent research

agent: tech-lead

alwaysApply: false

---

# Task: Test Quality Audit

## Goal

Identify tests that are outdated, low-value, redundant, fragile, or inconsistent with the current architecture, and identify important missing test coverage.

The orchestrator must delegate analysis to specialized agents and synthesize their structured findings.

---

# Workflow

## Step 0. Verify Test Environment

**Goal:** Ensure the test environment is available for reliable analysis.

**Launch Agent:** `test-engineer`

Start the required test environment and verify that required services are running.

If the environment cannot be started, document the reason and continue with static analysis where possible.

---

## Step 1. Analyze Current Architecture and Test Conventions

**Goal:** Establish the current implementation and determine what tests should be considered valid.

**Launch Agent:** `researcher`

Inspect:

- current architecture and layer boundaries;
- relevant models, APIs, services, and workflows;
- project testing conventions;
- relevant specifications and documentation;
- existing test configuration and fixtures.

Identify current contracts and important business behaviors that tests should verify.

Return a concise structured report.

---

## Step 2. Audit Test Quality

**Goal:** Identify tests that provide insufficient value or conflict with the current implementation.

**Launch Agent:** `test-engineer`

Analyze the test suite against the current architecture and conventions.

Look for:

- outdated contracts or imports;
- tests coupled to obsolete implementation details;
- tests that force production code to satisfy obsolete assumptions;
- missing or weak assertions;
- tests that only verify status codes or mock calls;
- tests that do not verify meaningful business behavior;
- excessive or inappropriate mocking;
- missing side-effect verification;
- redundant or duplicate tests;
- fragile or order-dependent tests;
- artificial or unrealistic test data;
- tests that should use shared fixtures;
- superficial tests with little verification value;
- tests that fail or require production changes because their assumptions are obsolete.

Identify missing coverage for important business flows, negative cases, boundaries, and side effects.

Return findings grouped by root cause.

---

## Step 3. Validate Findings

**Goal:** Confirm that proposed test changes are justified by the current system behavior.

**Launch Agent:** `researcher`

For each significant finding, verify:

- what the test currently expects;
- what the current implementation actually does;
- whether the behavior is defined by current requirements or documentation;
- whether the test is obsolete, incorrectly implemented, or exposing a real behavior that should remain protected.

Classify each finding as:

- `[TEST-DELETE]` — test has no meaningful value or is harmful;
- `[TEST-REWRITE]` — test intent is valid but implementation is fundamentally wrong;
- `[TEST-UPDATE]` — test requires a minor update to current behavior;
- `[BEST-PRACTICE]` — recommended quality or missing-coverage improvement;
- `[DOC-UPDATE]` — test and implementation agree, but documentation/specification is outdated or incorrect.

Do not assume that a failing or outdated-looking test should be deleted without validating the intended behavior.

---

## Step 4. Produce the Audit Report

**Goal:** Produce a concise, actionable test-quality audit.

**Launch Agent:** `auditor`

Synthesize the findings into a report containing:

| FilePath | TestName | Type | Problem | Recommendation |
|----------|----------|------|---------|----------------|

Include:

- obsolete tests;
- tests requiring rewrite or update;
- redundant or low-value tests;
- fragile tests;
- missing critical coverage;
- documentation/specification issues.

Group related findings where they share the same root cause.

Output path:

`.ai/audit/tests/audit_report_<number>.md`

Use the next available report number.

---

## Step 5. Create the Implementation Plan

**Goal:** Turn the audit findings into a prioritized implementation plan.

**Launch Agent:** `planner`

Using the audit report, create a plan covering:

- tests to delete;
- tests to rewrite;
- tests to update;
- missing tests to add;
- documentation/specification updates;
- dependencies between changes;
- recommended implementation order;
- validation required after each group of changes.

Prioritize changes by:

1. correctness and regression risk;
2. business importance;
3. impact on test quality;
4. implementation effort.

Do not modify tests, production code, or configuration.

Output path:

`.ai/plans`

---

# Constraints

- Evaluate tests against the current architecture and intended behavior.
- Do not preserve obsolete tests merely to increase coverage.
- Do not delete a test solely because it is simple; determine whether it protects meaningful behavior.
- Do not weaken assertions to make tests pass.
- Do not change production code during the audit.
- Do not recommend changing production code merely to satisfy an obsolete test.
- Preserve meaningful business, integration, and regression coverage.
- Prefer testing observable behavior and business rules over implementation details.
- Mark uncertain cases explicitly rather than guessing.
- Base recommendations on evidence from the codebase, tests, and current project documentation.

---

# Expected Result

A validated test-quality audit and a prioritized implementation plan identifying which tests should be deleted, rewritten, or updated, which important scenarios are missing, and which documentation/specification changes are required.