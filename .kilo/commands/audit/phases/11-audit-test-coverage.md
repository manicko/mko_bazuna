# 11 — Test Coverage

> Audit phase. LLM-auditor instruction. Architecture-agnostic: described via
> ARCHITECTURAL LAYERS, ZONES OF RESPONSIBILITY, KEY RISKS, GOALS. NOT tied to
> specific files, modules, or functions. Must stay valid if the architecture changes.
>
> **Output mode:** `problems-only` — report only findings; do not narrate a clean bill of health.

## 1. Goal

Verify the test suite is a trustworthy safety net for every security- and
correctness-critical behavior owned by phases 01–09: the ad-lifecycle state
machine, the login-token two-phase claim/expiry/replay, the PII-erasure sweep,
contact-gating, FTS visibility, the media sweep, and translation fallback. Tests
must be meaningful (not tautological), deterministic, isolated, and compliant
with the production-code-king rule.

## 2. System Under Audit (layers & zones)

| Zone | Concern |
|------|---------|
| **Persistence / Model-Test** | ORM behavior, status transitions, data invariants. |
| **Service-Logic-Test** | Business-logic validation, moderation rules, sweeps. |
| **Web-View-Test** | Request/response, search visibility, contact gating. |
| **Bot-Handler / FSM-Test** | Bot flow, login-token claim, contact deep-link, FSM persisted as DRAFT rows in the shared ORM. |
| **Integration / E2E-Test** | Cross-process ORM sharing; full flows against the real DB. |
| **External-Mock** | Telegram gateway + translator mocked; no real calls, no PII egress. |
| **Migration-Test** | Schema reproducibility; migrations idempotent; no drift. |
| **Fixture / Factory** | Synthetic data only (no PII/secrets); isolated DB + media store. |
| **CI-Gating** | Lint + type-check + test (+ coverage) enforced on PR; deterministic. |

## 3. Prerequisites

- Test suite runnable via the documented command (pytest over the whole repo).
- Coverage tooling available (line + branch).
- Real DB available for tests per project spec (no SQLite fallback masking drift).
- External dependencies mockable (no network/cost in CI).
- No code modification — audit only.

## 4. Runtime Verification (mandatory)

Execute, then capture evidence (pass/fail/skip, duration, coverage numbers, grep hits):

1. **Suite baseline** — run full suite → capture counts + duration.
2. **Critical-path coverage** — measure branch coverage on each critical behavior: lifecycle transitions, login-token claim/expiry/replay, PII-erasure sweep, contact-gating (all conditions), FTS visibility (PUBLISHED-only), media sweep (file+row atomicity), translation fallback. Assert each is actually exercised (not mocked away).
3. **Critical-path isolation** — run each critical test alone → confirm it asserts real behavior (e.g. consumed token rejected, sweep removes only expired revocations, each gating condition blocks independently, non-PUBLISHED ads excluded from search).
4. **Mock discipline** — grep tests for real external calls (gateway/translator) → assert mocked; assert no PII/secrets in test data.
5. **Test quality** — flag tests that mock the function under test or assert nothing real (tautology); flag tests coupled to private internals that break on refactor without behavior change.
6. **Two-process testing** — confirm bot FSM is tested against the REAL shared ORM (DRAFT persistence), not a fake; confirm web+bot consistency where relevant.
7. **Migration test** — confirm a test verifies migrations apply cleanly + are idempotent.
8. **Determinism** — run suite twice → identical results; confirm timezone/randomness/order handled explicitly.
9. **Prod-code-king** — flag any test that asserts wrong business logic or forces a production distortion; recommend fix/removal.
10. **CI gating** — confirm lint→type-check→test enforced; coverage reporting + threshold configured (or flag absence).

## 5. Audit Dimensions (checks + evidence)

### (a) Coverage of critical paths — CRITICAL
Every critical behavior from phases 01–09 has meaningful tests.
- Evidence: coverage on each path; tests assert real ORM/behavioral state.

### (b) Mock discipline — CRITICAL
External deps mocked; no real calls; no PII in test data.
- Evidence: grep clean; synthetic fixtures; no network in CI.

### (c) Test quality — HIGH
Assertions validate behavior, not implementation; no tautological tests.
- Evidence: tests fail on behavior regression, not on refactor; meaningful asserts.

### (d) Two-process testing — HIGH
Bot FSM tested against the real shared ORM (DRAFT persistence); web+bot consistency covered.
- Evidence: real-DB FSM tests; no fake-ORM false confidence.

### (e) Migration tests — HIGH
Migrations verified reproducible + idempotent.
- Evidence: migration test exists; re-run yields no drift/data loss.

### (f) Determinism — HIGH
No flakiness from timezone/randomness/DB order.
- Evidence: two identical runs; explicit time/order handling.

### (g) Prod-code-king compliance — CRITICAL
Tests don't distort production; bad tests fixed/removed.
- Evidence: no test-only branches in prod; wrong-logic tests flagged.

### (h) Fixtures hygiene — HIGH
No real PII/secrets; isolated DB + media store.
- Evidence: fixture scan clean; temp media root used.

### (i) CI gating + coverage reporting + speed — MEDIUM
Lint+type-check+test+coverage enforced; suite fast enough for CI.
- Evidence: CI config gates all; coverage threshold set; duration acceptable.

## 6. Cross-Cutting (owned here, not duplicated)
This phase verifies the TEST SAFETY NET for behaviors owned by other phases:
- Phase 05 lifecycle, Phase 04 login-token, Phase 06 PII/consent, Phase 07 media,
  Phase 08 search/FTS, Phase 09 integrations. The behaviors belong to those
  phases; this phase confirms they are actually tested and the tests are trustworthy.

## 7. Edge Cases
- A "test" mocks the very function it claims to test (zero-assertion tautology).
- Test passes but would not catch a regression (no assertion on changed behavior).
- Bot FSM test uses a fake ORM instead of the real shared one (false confidence).
- Timezone-dependent test passes locally, fails in UTC CI.
- Randomness/DB-order non-determinism.
- Migration test missing → schema drift undetected.
- Fixture with a real identity / secret.
- Test that, to pass, required a production distortion (prod-code-king violation).
- E2E test hitting the real translator (cost/flaky).

## 8. Severity Taxonomy

- **CRITICAL**
  - A security-critical path has ZERO tests (login-token replay, PII erasure, contact-gating, FTS visibility, lifecycle transitions, media sweep).
  - Tests assert WRONG business logic and pressure production distortion.
  - Tests make REAL external calls with PII.
  - Fixture contains real PII/secrets.
  - Forbidden lifecycle transition not blocked by tests.
- **HIGH**
  - Critical path tested only with mocks asserting nothing real / tautological.
  - Bot FSM not tested against the shared ORM.
  - No migration test.
  - Flaky / non-deterministic tests in CI.
  - Coverage <50% on security-critical modules.
  - Two-process consistency untested.
- **MEDIUM**
  - Branch coverage <80% on critical code.
  - Tests coupled to implementation details.
  - No coverage reporting / threshold.
  - Slow suite hurting CI.
- **LOW**
  - Missing type hints in tests.
  - Minor fixture duplication.
  - No test markers for slow/integration.

## 9. Recommended Sequence
1. Run suite → baseline.
2. Coverage on critical paths.
3. Mock discipline + fixtures hygiene.
4. Test quality (tautology / impl-coupling).
5. Two-process + migration + determinism.
6. Prod-code-king + CI gating.

## 10. Finding Prefix
Use `TST-` for all findings in this phase.

## 11. Reporting
- `problems-only: true`.
- Each finding: severity, zone, evidence (test name/line/coverage number/grep hit), and recommendation with effort/priority.
- Append incrementally (≤100 lines per write) to the phase findings file per `docs/99-agent/rules.md`.
