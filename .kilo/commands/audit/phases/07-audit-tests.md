---
name: 06-tests
status: complete
validated: no
executor: auditor
problems-only: true
---

# Phase 07 Audit — Test Quality

## Purpose

This is a **reusable, system-agnostic handbook** for auditing the test suite of ANY
project. It is not tied to a specific test runner, mocking library, or set of
modules. Apply the discovery steps and audit dimensions to whatever the system's
testing setup actually is, adapting concrete names to the implementation at hand.

## Output Mode

`problems-only: true` — **only problems, bugs, and deviations are documented.**

- **Do NOT** write sections that say "X is correct" or "no issues found in Y".
- **Do NOT** include checklist rows where the check passes — omit them entirely.
- If a dimension has zero findings after investigation, **omit the dimension entirely**.
- Every finding must be actionable: it describes a real problem, its evidence (code/logs/output), and its impact.

---

## Discovery Stage

Before performing audit checks, discover the testing architecture:

1. **Test Framework Discovery** — Identify the test runner, map test organization (unit per module), discover fixture/sharing patterns, find the mocking strategy.
2. **Coverage Discovery** — Map which architectural blocks have tests: entry layer, config/models, services, integrations, data flow.
3. **Test Patterns Discovery** — Identify common anti-patterns, map mocking strategies, discover assertion patterns, find async/sync test handling.
4. **Quality Discovery** — Identify tautological tests, map coverage gaps in critical paths, discover test brittleness indicators.

---

## Mandatory Runtime Verification

**Before evaluating any checklist item, you MUST complete these steps. Use the commands provided in the project's commands file. Skip only if a step is impossible — document why.**

### Step R1 — Run the Full Test Suite

Run the project's test suite and capture the complete output.

- Record pass/fail/skip counts.
- Record every failure with its full traceback.
- Record total execution time — excessively slow tests are a finding.
- If the test suite cannot run at all (import errors, config errors), that is CRITICAL.

### Step R2 — Analyze Test Failures

For each failing test from Step R1:

- Read the test code and the code it tests.
- Determine: is the test wrong, or is the production code wrong?
- If the production code is wrong, that is a CRITICAL finding (the bug exists in production).
- If the test is wrong (outdated, incorrect assertion), that is a finding (false sense of security).

### Step R3 — Detect Tautological and No-Op Tests

Search for tests that cannot fail or test nothing:

- Tests with no assertions (only `pass` or no body).
- Tests that assert a literal (`assert True`, `assert 1 == 1`).
- Tests that only call a function without checking the result.
- Tests where the mock is asserted to have been called, but the mock IS the implementation (testing the mock, not the logic).

Each instance is a finding with file:line.

### Step R4 — Verify Test Isolation

Run the test suite multiple times in sequence (or shuffle test order if the runner supports it).

- If tests pass individually but fail in suite: shared state between tests. Finding.
- If test results are non-deterministic: race condition or time-dependent test. Finding.
- Read test fixtures: verify cleanup happens even on test failure (teardown/fixture finalizers).

### Step R5 — Coverage Gap Analysis

Identify critical paths with low or zero coverage:

- For each critical architectural block, check if tests exist.
- For each critical path without tests, create a finding.
- If no coverage tool is configured, note it (but it is not a finding — coverage is advisory).

---

## Audit Scope

All test files, test fixtures, mocking strategies, test coverage, test isolation.

---

## Audit Dimensions

### 1. Critical Path Coverage

| Component | Must Have Tests For |
|-----------|-------------------|
| CLI commands (init, validate, run, config, version) | Each command/operation. Error paths tested. |
| Config loading | Valid config, invalid config, missing config, path resolution. |
| core/models, core/channels, core/telethon (Typed models) | Model validation, field constraints, custom validators, unknown-key rejection. |
| monitor_forward (process_task, process_messages, forward_to_users) | Message fetching, keyword matching, forwarding logic, error handling. |
| monitor_client | Client creation, auth/connection flow, message link building, sender tag. |
| Init service | Template copying, force flag, path creation. |
| Error handling | Custom exceptions raised correctly. |

**For each component without tests, create a finding.**

### 2. Test Anti-Patterns

| Check | Description |
|-------|-------------|
| No tautological tests | Every test can actually fail. |
| Assertions verify outcomes | Tests check return values and side effects, not just mock call counts. |
| Mocks at boundaries only | External systems are mocked. Internal logic is tested directly. |
| No shared mutable state | Tests are independent and can run in any order. |
| Tests don't depend on execution order | Any test can run in isolation. |
| No over-mocking | Tests do not mock the function they are testing. |

**Evidence required:** Read test files. For each anti-pattern found, provide file:line.

### 3. Mock Correctness

| Check | Description |
|-------|-------------|
| Mocks match real API | Mock return values match the real response format of the system under test. |
| Error paths are mocked | Tests cover error scenarios (not just happy paths) by mocking error responses. |
| Async mocks are correct | If the service uses async, mocks use the async-mock equivalent for the framework in use. |

**Evidence required:** Read mock setups in test files. Compare mock return values against real response formats.

### 4. Test Quality Indicators

| Check | Description |
|-------|-------------|
| Tests are readable | Test names describe the scenario. Setup is minimal. Assertions are clear. |
| Tests are fast | Unit tests complete quickly. No real network calls in unit tests. |
| Tests are deterministic | Same input always produces the same result. No time-dependent tests without freezing. |

**Evidence required:** Read test files. Run the test suite and check execution time.

---

## Report Output

Write findings to: `.ai/audit/07-tests/findings.md` using template `.ai/audit/templates/audit-findings.md`.

Use prefix `TST-` for finding IDs.

**`problems-only: true` rules:**
- The report contains **only findings** — real problems discovered during investigation.
- Do NOT include sections, dimensions, or checklist rows where everything is correct.
- If after completing all Runtime Verification steps and all Audit Dimensions, no problems were found, write a single line: `No problems found in this phase.`
- Every finding MUST include:
  1. **Runtime evidence** — test output, failure tracebacks, coverage gaps, file:line of problematic tests.
  2. **Not just:** "test coverage is low" — show exactly which critical path has no tests and what bug could go undetected.
