---
name: audit-test-performance

description: Analyze test suite performance and design an efficient test execution strategy using multi-agent research
agent: tech-lead
alwaysApply: false

---

# Task: Test Suite Performance & Strategy Audit

## Goal

Analyze the test suite, identify performance bottlenecks, classify tests by purpose and cost, and design an efficient test execution strategy without reducing meaningful coverage.

The orchestrator must delegate large-scale analysis to specialized agents and synthesize their structured reports.

---

# Workflow

## Step 1. Analyze the Current Test Suite

**Launch Agent:** `researcher`

**Goal:** Establish the current state and identify relevant test categories and infrastructure.

Inspect test configuration, structure, fixtures, markers, coverage rules, CI commands, and test dependencies.

Return a concise structured report.

---

## Step 2. Profile Test Performance

**Goal:** Identify where execution time is spent.

**Launch Agent:** `test-engineer`

Run the relevant test suite and report:

* total tests and execution time;
* slowest tests/groups;
* expensive setup/fixtures;
* database and external-service overhead;
* other significant bottlenecks.

Rank findings by impact.

---

## Step 3. Design Test Classification

**Goal:** Create a practical taxonomy for test selection.

**Launch Agent:** `test-engineer`

Define and evaluate categories such as:

* unit / integration / API / E2E;
* smoke / critical / regression;
* fast / slow.

Identify misclassified, redundant, or unnecessarily expensive tests.

---

## Step 4. Design the Execution Strategy

**Goal:** Minimize feedback time while preserving important coverage.

**Launch Agent:** `test-engineer`

Define:

* tests required for every PR/commit;
* tests for full CI;
* tests for nightly/release runs;
* safe parallelization/sharding opportunities;
* infrastructure or caching improvements.

Do not optimize for test count or coverage percentage alone; optimize for risk coverage and feedback speed.

---

## Step 5. Produce the Optimization Plan

**Goal:** Provide a prioritized, actionable plan.

**Launch Agent:** `planner`

Synthesize the reports into:

1. Main performance bottlenecks.
2. Proposed test taxonomy.
3. PR/CI/nightly test suites.
4. Recommended optimizations.
5. Prioritized implementation steps with expected impact.

Do not modify tests or configuration unless explicitly requested.

Output path: `.ai/plans`

---

# Constraints

* Base recommendations on measured evidence.
* Do not remove slow tests solely because they are slow.
* Do not replace meaningful integration tests with mocks without preserving equivalent coverage.
* Preserve critical business and regression coverage.
* Prefer simple, incremental improvements.
* Avoid speculative optimization.

---

# Expected Result

A concise, evidence-based plan that reduces test feedback time while maintaining meaningful test coverage and clearly defining which tests run at each CI stage.
