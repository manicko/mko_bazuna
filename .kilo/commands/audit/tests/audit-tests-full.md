---
name: audit-tests-full
description: audit-tests-full
agent: auditor
alwaysApply: false
---

# Test Quality Audit

## Step 0 — Ensure Docker Environment is Running

Start Docker services in **both development and test modes** (never production) before executing any test commands. Follow the setup instructions in `docs/11-guides/docker.md`. Confirm all required containers are in `running` or `healthy` state before proceeding. If the environment cannot be started, document why and skip dependent steps.

## Objective

Perform a complete audit of test coverage to:
- Identify and delete/rewrite tests that don't match the current architecture and code style
- Ensure tests verify **real system behavior**, not mocks or implementation details
- Verify sufficient coverage of all key system parts
- Guarantee high diagnostic value of tests
- Recommend missing test coverage for critical business flows

**Core principle:** Production code is the source of truth. Tests adapt to it, not the other way around. When tests and docs conflict with production code, update tests and docs — not the code.

## Recommendation Types

Label every finding:
- `[TEST-DELETE]` — test is harmful or worthless; delete it
- `[TEST-REWRITE]` — test intent is right but implementation is wrong; rewrite
- `[TEST-UPDATE]` — test needs minor updates to match current code
- `[BEST-PRACTICE]` — missing test coverage or quality improvement; advisory
- `[DOC-UPDATE]` — test reveals that docs/spec are wrong, not the code

## Research

Use `websearch` to verify current best practices for:
- pytest async testing patterns (pytest-asyncio)
- FastAPI test client patterns (httpx AsyncClient vs TestClient)
- SQLAlchemy async test fixtures and session management
- Meaningful test coverage metrics vs coverage for its own sake

## Anti-Patterns (subject to deletion or complete rewrite)

### 1. Architecture / Contract Mismatch
- Sync/async mismatch 
- Use of deprecated methods, DTOs, data types, or contracts
- Testing removed or renamed functionality
- Forces keeping legacy code just to pass tests
- Tests against old response shapes (e.g., pre-`TokenWithUser` login response)

### 2. Overmocking
- Mock completely replaces business logic
- Assertions check mock values, not real results
- Excessive `patch`/`mock` without verifying side effects
- Mocking Redis when `fakeredis` or real Redis would be more valuable

### 3. Tautological / Useless Tests
- `assert True`, missing `assert`, or trivial checks
- Verify obvious things ("object created", "status 200")
- Repeat implementation instead of verifying business contract

### 4. Wrong Abstraction Level
- Test private methods, internal details, specific SQL queries
- Verify call order instead of final result and business rules

### 5. Fragile Tests
- Break on refactoring without behavior change
- Depend on test execution order, `sleep`, or shared mutable state
- Don't use `pytest.mark.asyncio` properly

### 6. Poor Business Coverage
- Ignore negative scenarios and boundary conditions
- Use primitive data instead of realistic data
- Don't verify DB state, logs, and side effects

## Additional Checks

- **Test Pyramid**: balance between unit, integration, and e2e tests (avoid over-reliance on mocked unit tests)
- Duplication, copy-paste tests and fixtures
- Giant fixtures, hidden dependencies, shared mutable state
- **Mutation resistance** — test must fail when business logic is broken

## 9.1 pytest Standards

- All tests use **pytest** (not `unittest.TestCase`)
- Fixtures extracted to `conftest.py`
- Mocking only via `unittest.mock` or `pytest-mock`
- Async tests use `pytest.mark.asyncio`
- Test file naming: `test_*.py`
- Test function naming: `test_*`

## 9.2 System Coverage

Verify tests exist for all key system parts:

### Required Coverage Areas

- **Authentication & Authorization**
  - Login (returns `TokenWithUser` with `display_name`)
  - Registration request (creates `registration_requests` record)
  - Token refresh
  - Password change
  - Role-based access control (admin/editor/viewer)
  - Admin bypass for dashboard access
  - 403/404 dual-signal for dashboard access

- **API Layer** — all public endpoints (success cases + all error cases)
  - Auth endpoints (login, register-request, refresh, me, change-password)
  - Dashboard CRUD endpoints
  - Graph CRUD endpoints
  - Filter CRUD endpoints
  - Layout CRUD endpoints
  - Upload + processing endpoints
  - Data retrieval endpoints
  - Admin endpoints (users, registration-requests, logs)
  - Health endpoints (`/health`, `/health/detailed`, `/`)

- **Business Logic / Services**
  - AuthService (login, password verification, JWT creation)
  - DashboardService (access checks, admin bypass)
  - DataService (upload pipeline, processing trigger)
  - Registration approval flow (temp password via `secrets.token_urlsafe(16)`)
  - Processing log lifecycle (`started` → `uploaded` → `processing` → `success`/`failed`)

- **Data Processing**
  - CSV/CSV.gz loading (Polars, not pandas)
  - Data validation (schema, encoding, MIME-type)
  - Transformations (per processing_configs)
  - Aggregations (groupby, YoY, shares, custom metrics)
  - Custom metrics formula parser (valid and invalid formulas)
  - JSONB normalization (dims key recursive sorting)
  - Temp file cleanup (success and failure paths)

- **Repositories / Data Access**
  - CRUD operations for all entities
  - Dashboard access queries
  - JSONB containment queries (GIN index usage)
  - UPSERT operations on `aggregated_data`

- **Configuration & Startup**
  - Multi-source config loading (env, Docker secrets, .env, app.yaml)
  - Production credential enforcement
  - CORS origin validation
  - Startup lifecycle (DB check, migrations, admin user creation, stale file cleanup)

- **Task Queue**
  - Task enqueue/status/result/error tracking
  - Background worker execution
  - Processing log updates during pipeline execution

- **Pydantic Models**
  - All request/response models
  - StrEnum serialization
  - Custom validators (CORS origins, admin credentials)
  - `TokenWithUser` model (token + user with `display_name`)
  - `UserRead` model (computed `display_name` from email prefix)

### Special Attention
- Negative scenario and boundary condition coverage
- Integration tests with real test database (`bidb_test`)
- Critical path coverage (upload → process → display)
- Test database isolation (SAVEPOINT rollback, NullPool)
- Fixture structure matches `docs/06-backend/testing.md` specification


## Audit Result Format

Create file: `.ai/audit/tests/audit_report_<number>.md` (next available number)

**Report Structure:**

1. **Statistics**
   - Total tests: N
   - Critical problems: M
   - Recommended for deletion: K
   - Coverage by module

2. **Problematic Tests Table**

| File | Test | Type | Category | Problem | Action | Priority |
|------|------|------|----------|---------|--------|----------|
| tests/test_auth.py | test_login_old_response | [TEST-REWRITE] | Contract | Checks only `{access_token}`, not `TokenWithUser` | Rewrite | HIGH |
| tests/test_processing.py | test_process_uses_pandas | [TEST-DELETE] | Architecture | Imports pandas instead of polars | Delete | HIGH |
| tests/test_upload.py | test_no_assert | [TEST-DELETE] | Quality | No assert statement | Delete | MEDIUM |
| tests/test_dashboards.py | — | [BEST-PRACTICE] | Coverage | No tests for 403/404 dual-signal | Add tests | HIGH |
| tests/test_upload.py | test_upload_cleanup | [DOC-UPDATE] | Contract | Expects old cleanup behavior | Update test + spec | LOW |

3. **Coverage Assessment** — which important areas/scenarios are uncovered or weakly covered

4. **Key Findings** (with examples)

5. **Action Plan**
   - Delete Required (tests that force wrong production code changes)
   - Rewrite Required (tests with right intent, wrong implementation)
   - Improve (add negative cases, integration tests, etc.)
   - Doc Updates (tests that revealed spec/docs are wrong)

6. **Blocked Refactorings** (if any)

## Acceptance Criteria

- Clear separation: what to delete / rewrite / improve
- For each `ARCHITECTURE_CONFLICT` — link to production code
- Prioritization of problems
- Recommendations for improving test culture
- Critical coverage gaps identified

**Rule:** Better to delete a questionable test than to keep a test that misleads or slows down project development.
