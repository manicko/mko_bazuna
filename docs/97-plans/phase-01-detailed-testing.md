# Phase 1 Detailed Testing Plan

## Overview

This document identifies testing and quality assurance gaps in the Mko Bazuna Phase 1 codebase and outlines a comprehensive plan to address them. Based on codebase analysis, the project has a solid foundation of integration tests but lacks coverage in several critical areas.

---

## Current Test Coverage Analysis

### Existing Test Files (11 files)

| File | Purpose | Coverage Type |
|------|---------|---------------|
| `telegram_bot/tests/test_ad_lifecycle.py` | Ad lifecycle transitions (DRAFT → PUBLISHED) | Integration |
| `telegram_bot/tests/test_create_draft_ad.py` | Draft ad creation/deletion | Integration (async) |
| `telegram_bot/tests/test_media.py` | Media validation (JPEG, dimensions, EXIF) | Unit |
| `telegram_bot/tests/test_login_claim.py` | Login token atomic claim | Integration (async) |
| `telegram_bot/tests/test_claim_login_token.py` | Login token claim (duplicate coverage) | Integration (async) |
| `backend/apps/ads/tests/test_search_triggers.py` | PostgreSQL FTS trigger verification | Integration |
| `backend/apps/ads/tests/test_media_security.py` | Media access control, EXIF, path traversal | Integration |
| `backend/apps/search/tests/test_query_translator.py` | Query translation with circuit breaker | Unit |
| `backend/apps/users/tests/test_account_state.py` | Account state gating logic | Integration |
| `backend/apps/users/tests/test_deletion.py` | Consent withdrawal/deletion | Integration |
| `backend/apps/core/tests/test_migrations.py` | Migration idempotency | Integration |
| `backend/apps/core/tests/test_contact.py` | Contact render conditions | Integration |
| `backend/apps/moderation/tests/test_auto_moderation.py` | Auto-moderation validation functions | Unit/Integration |

### Test Markers in Use
- `pytest.mark.slow` — for DB-backed tests
- `pytest.mark.integration` — for tests requiring database
- `pytest.mark.asyncio` — for async handler tests

### Coverage Configuration
- **Target:** 80% coverage
- **Sources:** `src/backend`, `src/telegram_bot`
- **Omit:** migrations, tests, manage.py, wsgi.py, asgi.py

---

## Missing Test Categories

### Priority 1: Critical Business Logic (HIGH RISK)

#### 1.1 Bot Handler FSM Integration Tests

**Missing Tests:**
- `handlers/ad_create.py` — Complete FSM flow coverage
  - [ ] Category step: invalid keyword handling
  - [ ] Category step: multiple match selection by number
  - [ ] City step: fuzzy "did-you-mean" matching behavior
  - [ ] Title step: Pydantic validation boundary cases
  - [ ] Description step: Pydantic validation boundary cases
  - [ ] Price step: skip handling, invalid input handling
  - [ ] Photos step: photo limit enforcement (max 5)
  - [ ] Photos step: document rejection (non-telegram photo)
  - [ ] Preview step: translation failure fallback behavior
  - [ ] Preview step: moderation failure handling in FSM context

- `handlers/login.py` — Login handler tests
  - [ ] `handle_login_orm` missing: user lookup race condition tests
  - [ ] Login token with ban check integration

- `handlers/contact.py` — Contact handler tests
  - [ ] Contact deep-link parsing and delivery
  - [ ] Invalid ad_id in contact link
  - [ ] Contact to DELETED seller

**File to Create:** `src/telegram_bot/tests/test_handlers_fsm.py`

#### 1.2 Listings View Edge Cases

**Missing Tests:**
- `views/listings.py` — Listings and detail view coverage
  - [ ] Category filter with inactive category handling
  - [ ] Price filter boundary values (negative, zero, max)
  - [ ] Invalid sort parameter handling (fallback to default)
  - [ ] HTMX partial rendering boundary tests
  - [ ] Empty result log verification
  - [ ] City "did-you-mean" suggestion accuracy

**File to Create:** `src/backend/apps/ads/tests/test_listings_views.py`

#### 1.3 Moderation Services — Negative Paths

**Missing Tests:**
- `services/auto_moderation.py`
  - [ ] Duplicate title detection edge cases (threshold = 0, threshold = 100)
  - [ ] Max ads per user enforcement (exact boundary)
  - [ ] Price required = False combined with other failures
  - [ ] Cache miss behavior (database query on first access)
  - [ ] Criteria cache invalidation on signal

- `services/moderation_log.py` (referenced but untested)
  - [ ] `set_moderation_failed` logging
  - [ ] `set_published` logging

**File to Create:** `src/backend/apps/moderation/tests/test_moderation_negative.py`

### Priority 2: Security & Privacy (HIGH RISK)

#### 2.1 XSS Prevention Tests

**Missing Tests:**
- Ad content sanitization
  - [ ] XSS payloads in title/description are neutralized
  - [ ] Script injection in category search
  - [ ] Null byte injection in search queries

**File to Create:** `src/backend/apps/core/tests/test_xss_prevention.py`

#### 2.2 Rate Limiting & Abuse Prevention

**Missing Tests:**
- Login brute-force prevention
  - [ ] Multiple failed login attempts (test login_issue rate limiting)
- Search query flood limiting
  - [ ] Translation circuit breaker state validation

#### 2.3 CSRF & Session Security

**Missing Tests:**
- Consent action CSRF protection (POST method required)
- Session fixation prevention (login_status tests)

### Priority 3: Database Contract Tests (MEDIUM RISK)

#### 3.1 PostgreSQL Trigger Tests

**Missing Tests:**
- Search vector trigger conditions
  - [ ] Trigger not fired on non-PUBLISHED status changes (optimization)
  - [ ] Trigger handles special characters in Russian text
  - [ ] Trigger handles NULL values gracefully

**File to Create:** `src/backend/apps/core/tests/test_trigger_conditions.py`

#### 3.2 Advisory Lock Tests

**Referenced but untested:** `apps/core/utils/advisory_lock.py`
- [ ] Concurrent execution prevention
- [ ] Lock acquisition timeout handling

#### 3.3 Cache Invalidation Tests

**Missing Tests:**
- Criteria cache invalidation
  - [ ] `invalidate_criteria_cache` actually clears cache
  - [ ] Signal-triggered invalidation

---

## QA Processes Needed

### 2.1 Test Infrastructure

#### 2.1.1 Test Database Management
- **Current:** Uses `pytest.mark.django_db` — good
- **Gap:** No test fixtures for common test data (factories)
- **Recommendation:** Add `pytest-factoryboy` fixtures for consistent test data

```python
# Suggested factory pattern in conftest.py
@pytest.fixture
def ad_factory():
    """Factory for creating test ads with sensible defaults."""
    pass  # TODO: implement
```

#### 2.1.2 Code Coverage Enforcement
- **Current:** 80% target configured in pyproject.toml
- **Gap:** No CI enforcement of coverage requirements
- **Recommendation:** Add GitHub Actions workflow with coverage check

#### 2.1.3 Parallel Test Execution
- **Current:** Not configured
- **Recommendation:** Configure pytest-xdist for faster test runs in CI

### 2.2 Static Analysis & Type Checking

#### 2.2.1 Type Checking
- **Current:** `basedpyright` configured (report errors suppressed)
- **Gap:** Error suppression masks real issues
- **Recommendation:** 
  - Fix type errors instead of suppressing
  - Run `basedpyright` in CI with `--error` flag

#### 2.2.2 Linting
- **Current:** `ruff` configured with E, F, I, B, UP rules
- **Gap:** No CI enforcement
- **Recommendation:** Add ruff check to CI pipeline

### 2.3 Security Scanning

#### 2.3.1 Dependency Vulnerability Scanning
- **Missing:** No automated dependency audit
- **Recommendation:** Add `pip-audit` or `safety` to CI

#### 2.3.2 Secret Detection
- **Missing:** No secret scanning in CI
- **Recommendation:** Add `gitleaks` or `detect-secrets` to pre-commit

### 2.4 Performance Testing

#### 2.4.1 Query Performance
- **Current:** No query count assertions in tests
- **Recommendation:** Add `pytest-django-querycount` or assert query counts

#### 2.4.2 Load Testing
- **Missing:** No load testing infrastructure
- **Recommendation:** Add `locust` for API load testing (Phase 1.5)

### 2.5 Contract Testing

#### 2.5.1 OpenAPI Schema Generation
- **Missing:** No schema validation for future API compatibility
- **Recommendation:** Add `drf-spectacular` or similar (Phase 2)

#### 2.5.2 Database Migration Safety
- **Current:** Idempotent migration tests exist
- **Gap:** No rollback testing
- **Recommendation:** Add migration rollback tests

---

## Specific Test Cases to Implement

### Category

```
TestCategorySearch
  - test_search_empty_keyword_returns_empty
  - test_search_inactive_category_returns_empty
  - test_search_partial_match_returns_suggestions
  - test_search_exact_match_single_returns_selected
  - test_search_multiple_match_shows_options
  - test_search_multiple_match_number_selection
```

### City

```
TestCitySelection
  - test_exact_city_match_selected
  - test_typo_triggers_did_you_mean
  - test_unknown_city_shows_all_options
  - test_city_slug_validation
```

### Price

```
TestPriceValidation
  - test_valid_whole_number_accepted
  - test_negative_price_rejected
  - test_decimal_price_handling
  - test_zero_price_accepted
```

### Contact (R2 Conditions)

```
TestContactConditions
  - test_published_ad_with_deleted_seller_no_contact
  - test_published_ad_with_banned_seller_no_contact
  - test_archived_ad_no_contact
  - test_draft_ad_no_contact
  - test_contact_button_renders_for_valid_published
```

### Duplicate Detection

```
TestDuplicateTitle
  - test_exact_duplicate_detected
  - test_similar_title_threshold_dependent
  - test_different_user_titles_not_flagged
  - test_draft_ads_excluded_from_duplicate_check
```

---

## Test Execution Matrix

| Test Category | Current Coverage | Target Coverage | Priority |
|--------------|------------------|---------------|----------|
| FSM Handlers | ~30% | 90% | P1 |
| View Logic | ~40% | 85% | P1 |
| Moderation Services | ~60% | 85% | P1 |
| Security Controls | ~20% | 90% | P1 |
| Database Triggers | ~50% | 80% | P2 |
| Analytics Events | ~30% | 75% | P2 |
| Cache Mechanisms | ~40% | 80% | P2 |

---

## CI/CD Test Commands

```bash
# Current commands (from AGENTS.md)
uv run pytest <path>       # Run tests
uv run ruff check <path>   # Lint
uv run basedpyright <path> # Type check

# Recommended CI additions:
uv run pytest --cov --cov-fail-under=80  # Coverage enforcement
uv run ruff check src/                   # Full lint check
uv run basedpyright src/ --error           # Strict type check
```

---

## Test File Organization Recommendations

```
src/
├── telegram_bot/
│   └── tests/
│       ├── conftest.py          (existing)
│       ├── test_handlers_fsm.py     (NEW)
│       ├── test_ad_lifecycle.py  (existing)
│       ├── test_create_draft_ad.py (existing)
│       ├── test_media.py         (existing)
│       └── test_login_claim.py   (existing)
└── backend/
    └── apps/
        ├── ads/tests/
        │   ├── test_search_triggers.py (existing)
        │   ├── test_media_security.py (existing)
        │   └── test_listings_views.py  (NEW)
        ├── moderation/tests/
        │   ├── test_auto_moderation.py (existing)
        │   └── test_moderation_negative.py (NEW)
        ├── users/tests/
        │   ├── test_account_state.py (existing)
        │   └── test_deletion.py (existing)
        ├── search/tests/
        │   └── test_query_translator.py (existing)
        └── core/tests/
            ├── test_migrations.py (existing)
            ├── test_contact.py (existing)
            └── test_xss_prevention.py (NEW)
```

---

## Risk Mitigation

### Critical Risks Without Tests:

1. **FSM State Corruption** — No comprehensive FSM transition tests
2. **Media Security Bypass** — Path traversal partially covered, but XSS gaps exist
3. **Moderation Logic Gaps** — Duplicate detection threshold edge cases
4. **Race Conditions** — Advisory lock tests missing

### Recommended Test Data Pattern:

Use deterministic telegram_ids in tests to avoid conflicts:
- Seller IDs: 900000xxx range
- Admin/Moderator IDs: 900001xxx range
- Buyer IDs: 900002xxx range

---

## Next Steps

1. **Immediate:** Create missing test files for handler FSM and negative moderation paths
2. **Week 1:** Add XSS prevention tests
3. **Week 2:** Add view logic boundary tests
4. **Week 3:** Add factory fixtures for consistent test data
5. **Week 4:** Integrate linting/type-checking into CI