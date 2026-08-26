---
name: audit-test-performance

description: Analyze test suite performance and design an efficient test execution strategy using multi-agent research
agent: tech-lead
alwaysApply: false

---

# Test Suite Performance & Strategy Audit

## Goal

Analyze the test suite, identify performance bottlenecks, classify tests by risk and cost, and design an efficient execution strategy without reducing meaningful coverage.

The orchestrator only synthesizes structured agent reports. All measurement, profiling, deep inspection, and research must be delegated to specialized agents.

---

# Workflow

## Step 1. Baseline Current State

**Agent:** `researcher`

Map test structure, configuration, fixtures, markers, coverage, dependencies, CI commands, and collection behavior.

Return a concise structured baseline report, including known slow paths and relevant infrastructure.

---

## Step 2. Measure & Profile Execution

**Agent:** `test-engineer`

Measure the representative CI test path. Report:

* total tests and wall-clock time
* collection vs execution time
* slowest tests/groups
* expensive fixtures/setup/teardown
* DB, I/O, external-service, import, and coverage overhead

Rank findings by impact.

Every measurement must state command/scope and relevant environment or limitations. Do not infer performance problems without evidence.

---

## Step 3. Root-Cause Analysis

**Agent:** `test-engineer`

Using the baseline and measurement reports, investigate the highest-impact bottlenecks.

Check:

* fixture scope and repeated setup
* real I/O and external dependencies
* shared state and isolation
* discovery/collection cost
* parallelization safety

Return ranked root causes with evidence.

---

## Step 4. Test Taxonomy

**Agent:** `test-engineer`

Classify tests by:

* unit / integration / API / E2E
* smoke / critical / regression
* fast / slow

Flag misclassified, redundant, or unnecessarily expensive tests.

Prioritize risk coverage over test count or coverage percentage alone.

---

## Step 5. Research Proven Optimizations

**Agent:** `researcher`

Research techniques applicable to the actual stack:

* parallelization / sharding
* test-impact or change-based selection
* fixture scoping / caching
* coverage efficiency
* CI layering

Return only evidence-backed, low-risk techniques relevant to observed bottlenecks.

No generic recommendations without demonstrated applicability.

---

## Step 6. Design Execution Strategy

**Agent:** `test-engineer`

Using all previous reports, define:

* PR/commit suite: fast + high-risk tests
* full CI suite
* nightly/release suite
* safe parallelization/sharding
* infrastructure and caching improvements

Optimize for feedback speed and risk coverage while preserving critical business and regression coverage.

---

## Step 7. Produce Optimization Plan

**Agent:** `planner`

Synthesize all structured reports into:

1. Bottlenecks and evidence
2. Test taxonomy
3. PR / CI / nightly suites
4. Recommended optimizations and expected impact
5. Prioritized implementation steps

Where practical, define feedback-time targets and prioritize changes by impact, confidence, and effort.

Output to `.ai/plans`.

Do not modify tests or configuration unless explicitly requested.

---

# Constraints

* Base recommendations on measured evidence.
* Never remove tests solely because they are slow.
* Never replace meaningful integration coverage with mocks without equivalent coverage.
* Preserve critical business and regression coverage.
* Prefer simple, incremental changes.
* Avoid speculative optimization.
* Validate parallelization safety before recommending it.
* Downstream agents must use relevant previous reports and avoid duplicating expensive analysis.
* The orchestrator only synthesizes; measurement and deep analysis remain with sub-agents.

---

# Expected Result

A concise, evidence-based plan that reduces test feedback time, preserves meaningful coverage, and clearly defines which tests run at each CI stage.
