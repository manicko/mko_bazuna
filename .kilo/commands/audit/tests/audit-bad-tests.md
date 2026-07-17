---
name: audit-bad-tests
description: audit-bad-tests
agent: auditor
alwaysApply: false
---

# Test Quality Audit

## Step 0 — Ensure Docker Environment is Running

Start Docker services in **both development and test modes** (never production) before executing any test commands. Follow the setup instructions in `docs/11-guides/docker.md`. Confirm all required containers are in `running` or `healthy` state before proceeding. If the environment cannot be started, document why and skip dependent steps.

## Objective

Identify tests that:
1. **Don't match current architecture** — outdated contracts, wrong patterns, force production code to satisfy tests
2. **Have low verification value** — don't test business logic, only check status codes or mock calls
3. **Should be improved or removed** — redundant, fragile, or testing the wrong thing

Also recommend **missing test coverage** for critical business flows that have no tests at all.

## Recommendation Types

Label every finding:
- `[TEST-DELETE]` — test is harmful or worthless; delete it
- `[TEST-REWRITE]` — test intent is right but implementation is wrong; rewrite
- `[TEST-UPDATE]` — test needs minor updates to match current code
- `[BEST-PRACTICE]` — missing test coverage or quality improvement; advisory
- `[DOC-UPDATE]` — test reveals that docs/spec are wrong, not the code

## Research

Use `websearch` to verify current best practices for:
- pytest async testing patterns
- FastAPI test client patterns (httpx AsyncClient)
- SQLAlchemy async test fixtures
- Meaningful test coverage vs coverage for its own sake

## Bad Test Indicators (subject to deletion or complete rewrite):

### Architecture / Contract Mismatch
- Use `sync` instead of `async`/`await`
- Call deprecated methods, functions, or settings
- Violate the current layer separation (API → Service → Repository)
- Test against old response shapes (e.g., login returning only `{access_token}` instead of `TokenWithUser` with `user` + `display_name`)
- Reference removed or renamed StrEnum classes (e.g., old enum names)
- Test for `print()` output instead of logger calls

### No Business Logic Verification
- Only verify object creation or HTTP status codes (e.g., `assert response.status_code == 200` with no body checks)
- Verify method calls instead of business rules
- Mock completely replaces business logic
- Assertions check mock values, not real results
- Don't verify side effects (DB state, processing_logs entries, temp file cleanup)

### Weak Coverage & Low Value
- Ignore negative scenarios and boundary conditions
- Use minimal/artificial data instead of realistic data
- Don't verify DB state, logs, or side effects after execution
- Superficial tests ("field exists", "function doesn't crash")
- `assert True` or no `assert` at all
- `assert result is None` without verifying WHY it's None

### Quality & Maintenance Problems
- Redundant and duplicate tests
- Depend on test execution order
- Strongly coupled to internal implementation (fragile)
- Excessive mocking where test DB or real dependencies would suffice
- Don't use pytest fixtures from `conftest.py` (duplicate fixture definitions)
- Don't use `pytest.mark.asyncio` for async tests

### Specific Anti-Patterns
- Tests that don't verify JSONB normalization (dims key sorting)
- Tests that don't verify `display_name` is computed from email prefix
- Tests that don't verify `TokenWithUser` response shape (token + user profile)
- Tests that don't verify admin bypass for dashboard access
- Tests that don't verify 403/404 dual-signal behavior
- Tests that don't verify rate limiting (fail-open/fail-closed)
- Tests that don't verify temp file cleanup after processing
- Tests that don't verify processing_logs status lifecycle transitions
- Tests that don't verify registration approval flow (temp password generation)
- Tests that don't verify StrEnum values match PostgreSQL ENUM types
- Tests that use `unittest.TestCase` instead of pytest style

## Special Attention

- Tests without `assert` or with `assert True` / `assert not None`
- Mocks of repositories/services inside unit tests when test DB would suffice
- Tests that break after architecture refactoring without behavior change
- Tests written for old code version and not updated
- Tests that import from wrong module paths (e.g., old package structure)

**Rule:** If a test requires significant changes to production code just to make the test pass — delete that test.

**Rule:** If a test was written for old code and the code has legitimately evolved, update the test — don't revert the code.

**Rule:** When a test fails because the spec was wrong (not the code), recommend updating the spec, not the code.

## Report Format

Create file: `.ai/audit/tests/audit_report_<number>.md` (next available number)

| FilePath | TestName | Type | Problem | Recommendation |
|----------|----------|------|---------|----------------|
| tests/test_auth.py | test_login_old_response | [TEST-REWRITE] | Checks only `{access_token}`, not `TokenWithUser` with `display_name` | Rewrite to verify full response shape |
| tests/test_processing.py | test_process_uses_pandas | [TEST-DELETE] | Imports pandas instead of polars | Delete — violates tech stack |
| tests/test_upload.py | test_no_assert | [TEST-DELETE] | Has no assert statement | Delete or add meaningful assertions |
| tests/test_dashboards.py | — | [BEST-PRACTICE] | No tests for 403/404 dual-signal | Add negative scenario tests |
| tests/test_upload.py | test_upload_cleanup | [DOC-UPDATE] | Test expects old cleanup behavior, code evolved | Update test to match current `platformdirs` cleanup |
