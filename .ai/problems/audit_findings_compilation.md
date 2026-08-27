# Audit Findings Compilation — Test Quality Audit

**Compiled:** 2026-08-26  
**Source sessions:** 8/20–8/26 Test Quality Audit workflow (Steps 0–3), 8/26 current session  
**Scope:** Full test suite (backend + telegram_bot), config, and production code  
**Status:** All findings below are UNRESOLVED unless marked RESOLVED. Items marked RESOLVED were already corrected in prior sessions and must NOT be re-implemented.

---

## Table of Contents

1. [Resolved Findings (Do Not Re-implement)](#1-resolved-findings-do-not-re-implement)
2. [Open Findings — Grouped by Root Cause](#2-open-findings-grouped-by-root-cause)
3. [Coverage Gaps (Missing Tests)](#3-coverage-gaps-missing-tests)
4. [Plan & Documentation Discrepancies](#4-plan--documentation-discrepancies)
5. [Validation Matrix](#5-validation-matrix)
6. [Summary Statistics](#6-summary-statistics)

---

## 1. Resolved Findings (Do Not Re-implement)

### F-01: Shadowed `tests.py` Files Silently Skipped

| Attribute | Value |
|---|---|
| **Type** | `[TEST-DELETE]` |
| **Severity** | CRITICAL |
| **Status** | **RESOLVED** — commits `07a8f49` and `d72e597` |
| **Found by** | test-engineer (8/20) → researcher validation (8/21) |

**Root cause:** `pyproject.toml` configures `python_files = ["tests.py", "test_*.py"]`. When an app has both a `tests.py` module and a `tests/` package (with `__init__.py`), pytest collects the package and silently skips the module file. Two apps had this collision:

- `apps/moderation/tests.py` — 22 tests, tracked in git
- `apps/search/tests.py` — 9 tests, tracked in git

**Evidence:**
- `--collect-only` confirmed 0 items from `tests.py` files; all items came from `tests/` packages.
- Shadowed `moderation/tests.py::TestRejectAdView::test_reject_failed_moderation_ad` failed at runtime with `IntegrityError: new row for relation "ads" violates check constraint "ck_ads_moderation_failed_at_if_failed"`.
- Root cause of failure: the local `_create_ad` helper (lines 95–104) only set `published_at` for `PUBLISHED` status; it did NOT set `moderation_failed_at`, `rejected_at`, `archived_at`, or `deleted_at` for other statuses, violating the DB check constraints.

**Corrective action already taken:**
1. Deleted `src/backend/apps/moderation/tests.py` and `src/backend/apps/search/tests.py`.
2. Migrated tests into active `tests/` packages:
   - `apps/moderation/tests/test_moderation_views.py` (22 tests) — fixes `_create_ad` to set all status-specific timestamps.
   - `apps/search/tests/test_search_view.py` (9 tests) — strengthens assertions to check `response.context["page_obj"]` instead of model-level `Ad.objects.filter()` counts.
3. Verified: collection no longer includes `tests.py`; moderation+search tests pass (223 passed, 0 failed) with `--create-db`.

> **DO NOT re-delete or re-implement.** These files no longer exist in the working tree. The migrated replacements are tracked and passing.

---

## 2. Open Findings — Grouped by Root Cause

### 2.1 Duplicated Shared Fixtures (MEDIUM)

| Attribute | Value |
|---|---|
| **Type** | `[BEST-PRACTICE]` |
| **Severity** | MEDIUM |
| **Status** | OPEN |
| **Found by** | researcher validation (8/21) + test-engineer audit (8/20) |

**Root cause:** ~29 test files independently redefine `seller`, `user`, `category`, `city` fixtures instead of importing them from the root conftest at `src/backend/conftest.py`. The root conftest already provides all four with canonical values (`seller.telegram_id=900000001`, `user.telegram_id=900000002`, `category.name="Транспорт"`, `city.name="Тестград"`).

**Files with local `seller` fixture redefinitions:**
- `apps/ads/tests/test_ad_lifecycle.py`
- `apps/ads/tests/test_search_triggers.py`
- `apps/ads/tests/test_auth_nav.py`
- `apps/ads/tests/test_favorites.py`
- `apps/ads/tests/test_detail_context.py`
- `apps/ads/tests/test_gallery_markup.py`
- `apps/ads/tests/test_catalog_filters.py`
- `apps/ads/tests/test_listings_context.py`
- `apps/ads/tests/test_dashboard_stats.py`
- `apps/moderation/tests/test_admin_actions.py`
- `apps/moderation/tests/test_moderation_views.py`
- `apps/moderation/tests/test_priority.py`
- `apps/moderation/tests/test_priority_service.py`
- `apps/search/tests/test_search_view.py`
- `apps/search/tests/test_autocomplete.py`
- `apps/search/tests/test_alert_query.py`
- `apps/analytics/tests/test_views.py`
- `apps/analytics/tests/test_ads_published.py`
- `apps/analytics/tests/test_trust_analytics.py`
- `apps/trust/tests/test_trust_calculator.py`
- `apps/core/tests/test_contact.py`
- `apps/core/tests/test_sweep_commands.py`
- `apps/users/tests/test_login.py`
- `apps/users/tests/test_consent.py`
- `apps/users/tests/test_deletion.py`
- `src/telegram_bot/tests/conftest.py` (separate scope — async `user`, cannot resolve backend fixtures)

**Evidence:**
- Local `seller` fixtures use different `telegram_id` values (900000100, 900000020, 900000042, 910000001, 990030001, etc.) to avoid collisions — indicating the duplication is intentional but fragile.
- Some files (`test_media_security.py`, `test_ad_image_service.py`) define `seller`/`category` with `-> object` type annotations, weaker than the root conftest's typed return (`User`, `Category`).

**Recommendation:** Migrate all non-bot test files to use the root conftest fixtures. Document the bot conftest as a separate scope (async event loop + `sync_to_async` thread isolation makes fixture sharing infeasible).

---

### 2.2 Duplicated `_make_ad` / `_create_ad` Helpers (MEDIUM)

| Attribute | Value |
|---|---|
| **Type** | `[TEST-UPDATE]` |
| **Severity** | MEDIUM |
| **Status** | OPEN |
| **Found by** | researcher validation (8/21) |

**Root cause:** ~14 test files define their own `_make_ad` or `_create_ad` helper instead of using the root conftest's `create_test_ad`. The root `create_test_ad` is currently dead code (0 import/call references outside its definition).

**Files with local helpers:**
- `apps/moderation/tests/test_admin_actions.py` — `_make_ad`
- `apps/moderation/tests/test_moderation_views.py` — `_create_ad` (FIXED version — sets all timestamps)
- `apps/moderation/tests/test_priority.py` — `_make_ad`
- `apps/moderation/tests/test_priority_service.py` — `_make_ad`
- `apps/ads/tests/test_ad_lifecycle.py` — `_create_ad`
- `apps/ads/tests/test_dashboard_stats.py` — `_create_ad`
- `apps/ads/tests/test_detail_context.py` — `_create_ad`
- `apps/analytics/tests/test_views.py` — `_create_ad`
- `apps/analytics/tests/test_trust_analytics.py` — `_create_ad`
- `apps/search/tests/test_search_view.py` — `_create_ad`
- `apps/search/tests/test_autocomplete.py` — `_create_ad`
- `apps/search/tests/test_autocomplete_template.py` — `_create_ad`
- `apps/search/tests/test_saved_search_create.py` — `_create_ad`
- `apps/core/tests/test_sweep_commands.py` — `_create_ad`

**Evidence:**
- Some helpers handle Ad check constraints correctly (set all status-specific timestamps), others have bugs (the deleted `moderation/tests.py` only set `published_at` — the root cause of the CRITICAL failure in F-01).
- Each helper has slightly different signatures and default values (different `title`, `price`, `description`), leading to inconsistent test data.

**Recommendation:** Adopt `create_test_ad` from root conftest across all ~14 files; deprecate and remove local helpers.

---

### 2.3 Inconsistent Test Framework — `django.test.TestCase` Usage (LOW)

| Attribute | Value |
|---|---|
| **Type** | `[TEST-UPDATE]` |
| **Severity** | LOW |
| **Status** | OPEN |
| **Found by** | researcher validation (8/21) |

**Root cause:** 9 test files use `django.test.TestCase` (subclass of `unittest.TestCase`) instead of the project convention of plain `class TestX:` + `pytest.mark.django_db`. Per `docs/99-agent/rules.md`, tests must NOT use `django.test.TestCase` or `unittest.TestCase`.

**Affected files (9):**
| File | TestCase usage |
|---|---|
| `apps/ads/tests/test_ad_image_service.py` | `from django.test import TestCase` |
| `apps/media/tests/test_save_photo_exif.py` | `from django.test import TestCase` |
| `apps/ads/tests/test_media_security.py` | `from django.test import TestCase` |
| `apps/moderation/tests/test_auto_moderation.py` | `from django.test import TestCase` (in `TestValidate*` classes) |
| `apps/moderation/tests/test_priority_service.py` | `from django.test import TestCase` |
| `apps/moderation/tests/test_priority.py` | `from django.test import TestCase` |
| `apps/moderation/tests/test_admin_actions.py` | `from django.test import TestCase` |
| `apps/users/tests/test_consent.py` | `from django.test import TestCase` |
| `apps/users/tests/test_login.py` | `from django.test import TestCase` |

**Impact:** These tests cannot be filtered with `-m integration` or `-m unit`, breaking the project's marker-based test selection. Django's `TestCase` wraps each test in a DB transaction (rollback isolation), which is slower than pytest-django's default `django_db` behavior.

**Recommendation:** Migrate all 9 files to plain `class TestX:` + `pytest.mark.django_db` + `pytest.mark.integration` (per the dominant pattern: `pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]`).

---

### 2.4 Private Method Testing (LOW/MEDIUM)

| Attribute | Value |
|---|---|
| **Type** | `[BEST-PRACTICE]` |
| **Severity** | LOW/MEDIUM |
| **Status** | OPEN |
| **Found by** | researcher validation (8/21) |

**Root cause:** Tests directly invoke private methods (prefixed `_`), coupling tests to implementation details and reducing refactoring freedom.

**Affected files and methods:**
| File | Private method(s) tested |
|---|---|
| `apps/moderation/tests/test_auto_moderation.py` | `_contains_banned_words`, `_validate_title_length`, `_validate_description_length` |
| `apps/core/tests/test_sweep_commands.py` | Internal service calls (tests via command invocation, but asserts on internal state) |
| `apps/trust/tests/test_trust_calculator.py` | `_get_trust_level` (tested indirectly via `calculate_and_save`) |
| `apps/moderation/services/priority_calculator.py` (source) | `_get_priority_level`, `_estimate_confidence` — no direct unit tests, but `test_priority.py` tests via `PriorityCalculator` class |

**Evidence:**
- `test_auto_moderation.py` `TestValidate*` classes test `_validate_title_length`, `_validate_description_length` directly — these are internal validation functions, not public APIs.
- `PriorityCalculator._get_priority_level` (score→level: 0–39→LOW, 40–79→MEDIUM, 80–100→HIGH) and `_estimate_confidence` (always returns 0.7) are tested through the public `calculate` method but not at boundary edges.

**Recommendation:** Rewrite `test_auto_moderation.py` `TestValidate*` to test through the public `AutoModerator` class interface (the `moderate` method) rather than private `_validate_*` functions. The priority private methods are acceptable as they're tested through public API, but boundary-edge tests should be added.

---

### 2.5 Missing Decorator Unit Tests (LOW)

| Attribute | Value |
|---|---|
| **Type** | `[BEST-PRACTICE]` |
| **Severity** | LOW |
| **Status** | OPEN |
| **Found by** | researcher validation (8/21) |

**Root cause:** `staff_required` and `staff_required_api` decorators in `apps/moderation/views/decorators.py` are only tested indirectly through view-level integration tests. No dedicated unit tests for decorator-specific behaviors.

**Untested decorator behaviors:**
- `staff_required`: `is_superuser` branch, `is_staff` boundary, 404 response for non-staff
- `staff_required_api`: 403 JSON response for non-staff, POST enforcement (405 for non-POST), superuser bypass

**Evidence:**
- Grep for `staff_required` finds usage in view decorators but no `test_staff_required` or `TestStaffRequired` test class exists.
- `test_moderation_views.py` tests moderation views (HTTP-level) but doesn't isolate decorator logic.

**Recommendation:** Add `apps/moderation/tests/test_decorators.py` with focused unit tests for both decorators using Django's `RequestFactory`.

---

### 2.6 `e2e` Marker Registered but Unused (LOW)

| Attribute | Value |
|---|---|
| **Type** | `[DOC-UPDATE]` |
| **Severity** | LOW |
| **Status** | OPEN |
| **Found by** | researcher validation (8/21) |

**Root cause:** `pyproject.toml` registers an `e2e` marker, but zero tests in the codebase use `@pytest.mark.e2e`.

**Evidence:** Grep for `@pytest.mark.e2e` returns 0 results across `src/backend/` and `src/telegram_bot/`.

**Recommendation:** Remove the `e2e` marker from `pyproject.toml` (it's dead config).

---

### 2.7 `SimpleTestCase` Usage — Convention Violation (LOW)

| Attribute | Value |
|---|---|
| **Type** | `[TEST-UPDATE]` |
| **Severity** | LOW |
| **Status** | OPEN |
| **Found by** | current session (8/26) audit reading |

**Root cause:** 9 test files use `SimpleTestCase` (subclass of `unittest.TestCase`), violating the project rule "do NOT use `django.test.TestCase` or `unittest.TestCase`."

**Affected files (9):**
| File | Context |
|---|---|
| `apps/trust/tests/test_trust_prefetch.py` | No DB needed — tests prefetch query count |
| `apps/core/tests/test_context_processors.py` | No DB — tests context processor output |
| `apps/core/tests/test_language_middleware.py` | No DB — tests language middleware |
| `apps/core/tests/test_language_locale.py` | No DB — tests locale negotiation |
| `apps/ads/tests/test_listings_context.py` | No DB — tests view context |
| `apps/ads/tests/test_i18n_completeness.py` | No DB — compiles gettext catalogs |
| `apps/ads/tests/test_i18n_pipeline.py` | No DB — tests i18n pipeline |
| `apps/ads/tests/test_adimage_thumbnail_urls.py` | No DB — tests thumbnail URL generation |
| `apps/ads/tests/test_ad_localization.py` | No DB — in-memory only, intentional exception |

**Evidence:** All use `from django.test import SimpleTestCase` and `class TestX(SimpleTestCase):` with `self.assertEqual` / `self.assertSetEqual` style assertions instead of plain `assert`.

**Recommendation:** Convert all 9 files to plain `class TestX:` + `assert` to follow project conventions. `test_ad_localization.py` is an intentional in-memory exception and may be out of scope.

---

### 2.8 Raw Strings for Enum Fields — Convention Violation (LOW)

| Attribute | Value |
|---|---|
| **Type** | `[TEST-UPDATE]` |
| **Severity** | LOW |
| **Status** | OPEN |
| **Found by** | current session (8/26) |

**Root cause:** Tests use raw string literals for Enum fields instead of `StrEnum` values, violating project rule #10 ("All fixed values must use `Enum` or `StrEnum`").

**Affected files and usages:**
| File | Field | Raw string used |
|---|---|---|
| `apps/core/tests/test_sweep_commands.py` | `event_type` | `"search_performed"`, `"ad_archived"`, `"ad_deleted"` |
| `apps/core/tests/test_deletion.py` | `action_type` | `"ban_account"`, `"content_removal"` |

**Recommendation:** Replace raw strings with the corresponding `StrEnum` members (e.g., `AuditEventType.SEARCH_PERFORMED`, `DeletionReason.BAN_ACCOUNT`).

---

### 2.9 `Ad.objects.create()` Direct Usage Instead of Shared Helper (LOW)

| Attribute | Value |
|---|---|
| **Type** | `[BEST-PRACTICE]` |
| **Severity** | LOW |
| **Status** | OPEN |
| **Found by** | current session (8/26) |

**Root cause:** Two test files bypass the shared `create_test_ad` helper and use `Ad.objects.create()` directly, risking omission of required status-specific timestamps.

**Affected files:**
| File | Usage |
|---|---|
| `apps/ads/tests/test_breadcrumbs_render.py` | `Ad.objects.create(...)` directly |
| `apps/users/tests/test_deletion.py` | `Ad.objects.create(...)` directly |

**Evidence:** Direct `Ad.objects.create()` calls may set `status` but omit `published_at`, `archived_at`, etc., silently violating check constraints or producing inconsistent test data.

**Recommendation:** Replace all direct `Ad.objects.create()` calls with `create_test_ad(...)` from root conftest, which sets the correct timestamps per status.

---

### 2.10 Fragile Structure Inspection via `inspect.getsource()` (MEDIUM)

| Attribute | Value |
|---|---|
| **Type** | `[TEST-REWRITE]` |
| **Severity** | MEDIUM |
| **Status** | OPEN |
| **Found by** | current session (8/26) |

**Root cause:** `test_sweep_lock_structure.py` uses `inspect.getsource()` to verify code structure (that `transaction.atomic` wraps `pg_advisory_xact_lock`) rather than testing observable behavior.

**Evidence:**
```python
source = inspect.getsource(sweep_function)
assert "pg_advisory_xact_lock" in source
assert "transaction.atomic" in source
```
This test breaks if the function is refactored (e.g., extracted to a helper), even if behavior is preserved. It's a test of implementation, not behavior.

**Recommendation:** Rewrite to verify observable behavior — e.g., test that concurrent sweep invocations don't deadlock, or that the lock is acquired before processing (via a mock/spy on the lock function or a DB-level lock test).

---

### 2.11 Low-Value Tests — Private Auto-Moderation Functions (MEDIUM)

| Attribute | Value |
|---|---|
| **Type** | `[TEST-DELETE]` / `[TEST-REWRITE]` |
| **Severity** | MEDIUM |
| **Status** | OPEN |
| **Found by** | current session (8/26) — also noted in §2.4 |

**Root cause:** `test_auto_moderation.py` `TestValidate*` classes test private functions `_contains_banned_words`, `_validate_title_length`, `_validate_description_length` directly. These are implementation details, not public contracts.

**Evidence:**
- `TestValidateTitleLength.test_title_too_short` calls `validate_title_length("a")` directly — but the function signature is `_validate_title_length` (private).
- These tests would break if the moderation logic were refactored to use a different validation pipeline.

**Recommendation:** Rewrite to test through the public `AutoModerator.moderate()` interface, asserting on the returned `ModerationResult` or the `status` transition on the `Ad` object.

---

### 2.12 Duplicate/Redundant Test Coverage — Bot Login Token Tests (LOW)

| Attribute | Value |
|---|---|
| **Type** | `[TEST-DELETE]` |
| **Severity** | LOW |
| **Status** | OPEN |
| **Found by** | current session (8/26) |

**Root cause:** `test_claim_login_token.py` and `test_login_claim.py` both test the same `handle_login_orm` function in the Telegram bot, creating redundant coverage.

**Evidence:**
- Both test files test the same handler function with overlapping scenarios (token creation, token claim, token reuse, bot-phase-only flow).
- `test_login_claim.py` focuses on the bot-side FSM flow (Telegram message handling).
- `test_claim_login_token.py` focuses on the token model-level operations (ORM interaction).

**Recommendation:** Consolidate into a single test file that covers both layers, or clearly delineate the test boundaries (one for FSM, one for token model).

---

## 3. Coverage Gaps (Missing Tests)

### C-01: Ad Model Check Constraints (P0)

| Attribute | Value |
|---|---|
| **Type** | `[BEST-PRACTICE]` — missing coverage |
| **Priority** | P0 |
| **Status** | OPEN |

**Gap:** The `Ad` model has 5+ DB check constraints (`ck_ads_published_at_if_published`, `ck_ads_rejected_at_if_rejected`, `ck_ads_moderation_failed_at_if_failed`, `ck_ads_archived_at_if_archived`, `ck_ads_deleted_at_if_deleted`) and `AdStatus.transition_to()` enforces valid state transitions in code. No test directly exercises these constraints or the transition matrix.

**Evidence:** `src/backend/apps/ads/models.py` has `Meta.constraints` with `CheckConstraint` definitions, but no test file calls `Ad.full_clean()` or `transition_to()` at boundary edges. `test_ad_lifecycle.py` tests some transitions but not the invalid-state rejection.

**Recommendation:** Add `test_ad_constraints.py` testing each check constraint (invalid state → `IntegrityError`/`ValidationError`) and the `transition_to` state machine edge cases (e.g., `ARCHIVED → ON_MODERATION` is invalid).

---

### C-02: TrustCalculator Quality Score Truncation (P0)

| Attribute | Value |
|---|---|
| **Type** | `[BEST-PRACTICE]` — missing coverage |
| **Priority** | P0 |
| **Status** | OPEN |

**Gap:** `TrustCalculator.calculate_and_save()` computes `quality_score = int((1 - rejected/total) * 30)`. The `int()` truncates (e.g., `133 → 40` instead of `41`). No test exercises truncation edge cases.

**Evidence:** `apps/trust/services/trust_calculator.py` — quality score formula. `test_trust_calculator.py` tests basic scenarios but not truncation boundaries (e.g., total=3, rejected=1 → 66.67% → int(20) = 20, not 21).

**Recommendation:** Add boundary tests for the `int()` truncation behavior with specific `total`/`rejected` combinations.

---

### C-03: PriorityCalculator `_estimate_confidence` Boundaries (P0)

| Attribute | Value |
|---|---|
| **Type** | `[BEST-PRACTICE]` — missing coverage |
| **Priority** | P0 |
| **Status** | OPEN |

**Gap:** `PriorityCalculator._estimate_confidence` always returns `0.7` (a constant). No boundary tests exist for when confidence should vary. Additionally, `_get_priority_level` thresholds (score≥80→HIGH, score≥50→MEDIUM) are not tested at exact boundary edges (49→LOW, 50→MEDIUM, 79→MEDIUM, 80→HIGH).

**Recommendation:** Add tests for `_estimate_confidence` constants and `_get_priority_level` boundary edges.

---

### C-04: Contact Service `can_contact_seller` Edge Cases (P1)

| Attribute | Value |
|---|---|
| **Type** | `[BEST-PRACTICE]` — missing coverage |
| **Priority** | P1 |
| **Status** | OPEN |

**Gap:** `can_contact_seller` logic: returns renderable only when ad is PUBLISHED + seller has `telegram_id` != NULL + seller not deleted/banned + consent not revoked. Edge cases (banned user, revoked consent mid-session, deleted seller) are not tested.

**Recommendation:** Add combinatorial edge-case tests for `can_contact_seller` and `get_seller_for_contact` (see also `test_contact.py` which already added 9-case parametrized tests in the current session).

---

### C-05: Search Sorting — DATE_OLD / DATE_NEW (P1)

| Attribute | Value |
|---|---|
| **Type** | `[BEST-PRACTICE]` — missing coverage |
| **Priority** | P1 |
| **Status** | OPEN |

**Gap:** `test_search_triggers.py` only tests `PRICE_LOW` sorting. `DATE_OLD` (oldest first) and `DATE_NEW` (newest first, default) are not tested.

**Recommendation:** Add sort-order tests covering `DATE_OLD`, `DATE_NEW`, and the default (no `sort` param).

---

### C-06: Ad Detail View Trust Score Prefetch N+1 (P1)

| Attribute | Value |
|---|---|
| **Type** | `[BEST-PRACTICE]` — architecture issue + missing coverage |
| **Priority** | P1 |
| **Status** | OPEN |

**Gap:** `listings.py` (search results) prefetches `user__trust_score`, but `ad_detail` (in `listings.py` `ad_detail` function) does NOT. This means the ad detail page triggers an N+1 query when rendering the trust badge (`render_trust_badge` template tag accesses `user.trust_score`).

**Evidence:** `listings.py` line ~255: `.prefetch_related("user__trust_score")` — wait, actually `.select_related("user")` + `.prefetch_related("user__trust_score")`. The `ad_detail` function uses a different queryset without the trust score prefetch.

**Recommendation:** Add `user__trust_score` prefetch to `ad_detail` queryset; add a query-count regression test (`test_ad_detail_queries.py`).

---

### C-07: Admin Action Side Effects — `approve_ad` Signal Chain (P1)

| Attribute | Value |
|---|---|
| **Type** | `[BEST-PRACTICE]` — missing coverage |
| **Priority** | P1 |
| **Status** | OPEN |

**Gap:** `approve_ad` (admin action) transitions `Ad` to PUBLISHED. On `Ad.post_save`, signals trigger: auto-moderation check, `AdArchive`/`AdDelete` schedule (CELERY, 2mo/4mo from `published_at`), and immediate Telegram alert to seller. No test verifies the full signal chain.

**Recommendation:** Add `test_approve_ad_side_effects.py` testing: approve → PUBLISHED → auto-moderation gate → alert dispatched.

---

### C-08: LoginToken HMAC Issuance and Claim Edge Cases (P2)

| Attribute | Value |
|---|---|
| **Type** | `[BEST-PRACTICE]` — missing coverage |
| **Priority** | P2 |
| **Status** | OPEN |

**Gap:** `LoginToken` two-phase atomic claim uses `hmac.compare_digest` for token hash comparison. Edge cases: token mismatch → 410, consumed-token replay → 410, expired token rejection, token hash is SHA-256 not raw — are not comprehensively tested.

**Recommendation:** Add edge-case tests for token lifecycle (mismatched hash, replay, expiry, raw-token-not-stored). (Note: current session 8/26 already added `TestLoginTokenSecurity` class with 5 tests to `test_login.py`.)

---

### C-09: Thumbnail Generation Integration (P2)

| Attribute | Value |
|---|---|
| **Type** | `[BEST-PRACTICE]` — missing coverage |
| **Priority** | P2 |
| **Status** | PARTIALLY COVERED |

**Gap:** `generate_thumbnails` is unit-tested, but the `save_photo` → `generate_thumbnails` integration chain (at `ad_create.py:588`) is not tested end-to-end with real image data. `test_save_photo_exif.py` tests EXIF extraction but not thumbnail generation.

**Update:** The current session (8/26) confirmed `generate_thumbnails` IS well unit-tested. The real gap is the `save_photo`→thumbnails integration at `ad_create.py:588`.

---

### C-10: Moderation Priority Scoring Boundaries (P2)

| Attribute | Value |
|---|---|
| **Type** | `[BEST-PRACTICE]` — missing coverage |
| **Priority** | P2 |
| **Status** | PARTIALLY COVERED |

**Gap:** `PriorityCalculator` thresholds (score≥80→HIGH, score≥50→MEDIUM, <50→LOW) — boundary-edge tests (79→MEDIUM, 80→HIGH) are missing. Confidence score is always 0.7 (constant) — no tests assert this invariant.

**Update:** The current session (8/26) already added `TestPriorityLevelBoundaries` (5 tests) and `TestConfidenceScore` (1 test) to `test_priority.py`.

---

### C-11: Trust Level Floor Logic (P2)

| Attribute | Value |
|---|---|
| **Type** | `[BEST-PRACTICE]` — missing coverage |
| **Priority** | P2 |
| **Status** | PARTIALLY COVERED |

**Gap:** `get_trust_level()` — when `score=0` but user is verified/premium, should return `VERIFIED` (floor logic). The researcher validated this behavior exists in code but it's not tested.

**Recommendation:** Add a test asserting that `get_trust_level(user_with_score_0_but_verified)` returns `VERIFIED`.

---

## 4. Plan & Documentation Discrepancies

### D-01: Test-Optimization Plan §1.2 — Markers "Not Registered"

| Attribute | Value |
|---|---|
| **Type** | `[DOC-UPDATE]` |
| **Severity** | LOW |
| **Status** | OPEN |

**Discrepancy:** Plan §1.2 states markers are "Not registered." Actual `pyproject.toml` registers all 7 markers: `unit`, `integration`, `e2e`, `seed`, `settings`, `concurrent`, `slow` (plus `real_images`, `xdist_group` in the current version).

**Recommendation:** Update plan §1.2 to reflect current marker registration.

---

### D-02: Test-Optimization Plan §1.4 — "CI Runs All 934 Tests"

| Attribute | Value |
|---|---|
| **Type** | `[DOC-UPDATE]` |
| **Severity** | LOW |
| **Status** | OPEN |

**Discrepancy:** Plan §1.4 claims "CI runs all 934 tests." Actual CI (`.github/workflows/ci.yml` line 85) runs `pytest -m "not seed"` — only 918 non-seed tests.

**Recommendation:** Update plan §1.4 to reflect CI filtering.

---

### D-03: Test-Optimization Plan §1.1 — References Deleted `tests.py`

| Attribute | Value |
|---|---|
| **Type** | `[DOC-UPDATE]` |
| **Severity** | LOW |
| **Status** | RESOLVED (partially) |

**Discrepancy:** Plan §1.1 references shadowed `tests.py` files as existing and active. These were deleted (commits `07a8f49`, `d72e597`) and migrated to `tests/` packages.

**Status:** Partly resolved — the deletion happened, but the plan doc may still reference the old files.

**Recommendation:** Update plan §1.1 to reference the migrated `test_moderation_views.py` and `test_search_view.py` instead of `tests.py`.

---

### D-04: Test-Optimization Plan §14 — T-12 "All Previously-Failing Tests Pass"

| Attribute | Value |
|---|---|
| **Type** | `[DOC-UPDATE]` |
| **Severity** | MEDIUM |
| **Status** | OPEN |

**Discrepancy:** Plan §14 T-12 claims "Previously-failing tests (50+) — All now pass ✅" and "moderation/search backend tests: 376 passed ✅." This was measured WITHOUT the shadowed `tests.py` files being collected. The 31 shadowed tests (including 1 real failure: `test_reject_failed_moderation_ad`) were never run during validation.

**Recommendation:** Update §14 T-12 to clarify that the shadowed tests were excluded from the baseline, and that the failure in `test_reject_failed_moderation_ad` was a real (now-resolved) bug in the test helper, not the production code.

---

## 5. Validation Matrix

| Finding ID | Type | Severity | Status | Verified by |
|---|---|---|---|---|
| F-01 | `[TEST-DELETE]` | CRITICAL | RESOLVED | Runtime (docker pytest) + git history |
| §2.1 | `[BEST-PRACTICE]` | MEDIUM | OPEN | Static (grep + conftest read) |
| §2.2 | `[TEST-UPDATE]` | MEDIUM | OPEN | Static (grep + file reads) |
| §2.3 | `[TEST-UPDATE]` | LOW | OPEN | Static (grep for `TestCase` imports) |
| §2.4 | `[BEST-PRACTICE]` | LOW/MEDIUM | OPEN | Static (code + test reads) |
| §2.5 | `[BEST-PRACTICE]` | LOW | OPEN | Static (grep for decorator tests) |
| §2.6 | `[DOC-UPDATE]` | LOW | OPEN | Static (grep for `@pytest.mark.e2e`) |
| §2.7 | `[TEST-UPDATE]` | LOW | OPEN | Static (file reads) |
| §2.8 | `[TEST-UPDATE]` | LOW | OPEN | Static (file reads) |
| §2.9 | `[BEST-PRACTICE]` | LOW | OPEN | Static (file reads) |
| §2.10 | `[TEST-REWRITE]` | MEDIUM | OPEN | Static (file read) |
| §2.11 | `[TEST-DELETE/REWRITE]` | MEDIUM | OPEN | Static (file read) |
| §2.12 | `[TEST-DELETE]` | LOW | OPEN | Static (file comparison) |
| C-01 | `[BEST-PRACTICE]` | P0 | OPEN (some covered) | Source + test reads |
| C-02 | `[BEST-PRACTICE]` | P0 | OPEN | Source + test reads |
| C-03 | `[BEST-PRACTICE]` | P0 | PARTIALLY COVERED | Source + test reads |
| C-04 | `[BEST-PRACTICE]` | P1 | PARTIALLY COVERED | Source + test reads |
| C-05 | `[BEST-PRACTICE]` | P1 | OPEN | Source + test reads |
| C-06 | `[BEST-PRACTICE]` | P1 | OPEN | Source + test reads |
| C-07 | `[BEST-PRACTICE]` | P1 | OPEN | Source + test reads |
| C-08 | `[BEST-PRACTICE]` | P2 | PARTIALLY COVERED | Source + test reads |
| C-09 | `[BEST-PRACTICE]` | P2 | PARTIALLY COVERED | Source + test reads |
| C-10 | `[BEST-PRACTICE]` | P2 | PARTIALLY COVERED | Source + test reads |
| C-11 | `[BEST-PRACTICE]` | P2 | PARTIALLY COVERED | Source + test reads |
| D-01 | `[DOC-UPDATE]` | LOW | OPEN | Static (pyproject.toml) |
| D-02 | `[DOC-UPDATE]` | LOW | OPEN | Static (ci.yml) |
| D-03 | `[DOC-UPDATE]` | LOW | RESOLVED (partial) | Git history |
| D-04 | `[DOC-UPDATE]` | MEDIUM | OPEN | Static (plan doc + runtime) |

---

## 6. Summary Statistics

### By Type

| Type | Open | Resolved | Total |
|---|---|---|---|
| `[TEST-DELETE]` | 2 | 1 | 3 |
| `[TEST-REWRITE]` | 1 | 0 | 1 |
| `[TEST-UPDATE]` | 5 | 0 | 5 |
| `[BEST-PRACTICE]` | 16 | 0 | 16 |
| `[DOC-UPDATE]` | 3 | 1 | 4 |

### By Severity

| Severity | Count |
|---|---|
| CRITICAL | 1 (resolved) |
| HIGH | 0 |
| MEDIUM | 5 |
| LOW | 18 |
| P0–P2 (coverage gaps) | 11 |

### By Status

| Status | Count |
|---|---|
| RESOLVED | 2 (F-01, D-03 partial) |
| PARTIALLY COVERED | 6 (C-03, C-04, C-08, C-09, C-10, C-11) |
| OPEN | 16 + 5 doc = 21 |

---

*Document compiled from agent session transcripts: `ses_fdee6e92affe` (test-engineer 8/20), `ses_fdfac9506ffe` (researcher 8/20), `ses_fdebe0bc7ffe` (researcher validation 8/21), `ses_fde653743ffe` (auditor 8/21), `ses_fde5b4ccdffe` (planner 8/21), `ses_fc22394a4ffe` (current audit session 8/26).*
