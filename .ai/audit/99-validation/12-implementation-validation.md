# Implementation Validation Report

**Date:** 2026-09-17  
**Validator:** Independent (read-only)  
**Decision reference:** `.ai/audit/99-validation/11-failing-tests-solution-decisions.md`  
**Status:** ACCEPTED

---

## 1. Executive Summary

All 5 fixes across 6 files were verified against the architectural decisions in the solution-decisions document. Each fix matches its intended design, passes lint and type-checking, and produces zero test failures. The full fast gate (1,570 tests) passes with 0 failures, and the seed test classes pass with 0 failures.

**Overall assessment: ACCEPTED — no issues found.**

---

## 2. Per-Fix Verification Results

### Fix 1 — Migration help_text sync (Category D)

| Checklist item | Status | Evidence |
|---|---|---|
| Migration help_text matches model exactly | ✅ PASS | Migration line 68: `"FTS query string stored in the user's language; matched against the per-language search vector (no query-time translation)"`. Model lines 76-79: same concatenated string. Programmatic comparison confirmed exact match. |
| Field type (TextField) unchanged | ✅ PASS | Both migration (line 66) and model (line 73) use `models.TextField(...)`. No schema change. |
| No new migration file created | ✅ PASS | `glob` on `src/backend/apps/search/migrations/*.py` returns only `0001_initial.py` and `__init__.py`. No additional migration. |
| `test_makemigrations_check` passes | ✅ PASS | Full fast gate run: 1,570 passed, 0 failures. Test included in the run. |

**Git diff confirms:** help_text changed from `"FTS query string (translated to Russian if Bosnian input)"` to the model-matching text.

---

### Fix 2 — Pydantic error serialization (Category C)

| Checklist item | Status | Evidence |
|---|---|---|
| Uses `exc.json(include_input=False, include_url=False, include_context=False)` | ✅ PASS | `sanitize.py:88-89` — `json.loads(exc.json(include_input=False, include_url=False, include_context=False))`. Matches decision document exactly. |
| Function imported and used in `api_bulk.py` | ✅ PASS | Import at `api_bulk.py:15`; usage at `api_bulk.py:48` — `pydantic_errors_json(exc)`. No direct `exc.errors()` call. |
| Full error logged before stripping | ✅ PASS | `api_bulk.py:46` — `logger.warning("Invalid bulk moderation request body: %s", exc)`. Logs full `exc` (including input/ctx/url) server-side before the helper strips them. |
| No `include_input` in response (CWE-209) | ✅ PASS | The helper passes `include_input=False`, so raw request body never reaches the JSON response. |
| Helper in `core/utils/sanitize.py` | ✅ PASS | Consistent with module's existing sanitize pattern (`sanitize_query_for_log`, `mask_telegram_id`). |
| `test_empty_body_returns_422` passes | ✅ PASS | Full fast gate: 1,570 passed, 0 failures. |
| `test_malformed_json_body_returns_422` passes | ✅ PASS | Full fast gate: 1,570 passed, 0 failures. |

**Git diff confirms:** import added at line 15; `exc.errors()` → `pydantic_errors_json(exc)` at line 48; `logger.warning` now includes `%s` with `exc` at line 46.

---

### Fix 3 — i18n gettext_lazy (Category B)

| Checklist item | Status | Evidence |
|---|---|---|
| `gettext` → `gettext_lazy` import | ✅ PASS | `telegram_tags.py:42` — `from django.utils.translation import gettext_lazy as _`. Diff confirms change from `gettext`. |
| `_LABELS` type annotation handles `Promise` | ✅ PASS | `telegram_tags.py:65` — `dict[TelegramDeepLinkCommand, str \| Promise]`. `Promise` imported from `django.utils.functional` at line 39. `from __future__ import annotations` at line 31 ensures annotations are strings at runtime. |
| `str(_LABELS[cmd])` resolves lazy string at render time | ✅ PASS | `telegram_tags.py:151` — `label = str(_LABELS[cmd])`. `str()` on a `gettext_lazy` `Promise` forces translation resolution at render time, when per-request language is active. |
| No other template tags affected | ✅ N/A (verified) | `dashboard.py` uses `gettext_lazy` inside function bodies (safe); `enums.py` uses `gettext_lazy` at class-body level (safe). `telegram_tags.py` was the only module-level `gettext` pattern. |
| `test_home_renders_catalog_header` passes | ✅ PASS | Auth_nav tests run: 9 passed, including both catalog header tests. |
| `test_detail_renders_catalog_header` passes | ✅ PASS | Same run: 9 passed. |
| `test_i18n_completeness` passes | ✅ PASS | 9 passed, 0 failures. |

**Note:** The decision document references line 150 for `str(_LABELS[cmd])`; the current file has it at line 151. This 1-line offset is due to the added `from django.utils.functional import Promise` import line, which shifted downstream code. No functional impact.

---

### Fix 4 — Seed generator draft deduplication (Category E)

| Checklist item | Status | Evidence |
|---|---|---|
| `_deduplicate_drafts()` reassigns excess DRAFTs to non-DRAFT statuses | ✅ PASS | `ads.py:569-610` — method iterates ads, tracks `seen_draft_users` set, reassigns 2nd+ DRAFT per user via `self._rng.choices(non_draft_statuses, ...)`. |
| Uses `self._rng` for reassignment | ✅ PASS | `ads.py:604-606` — `ad.status = self._rng.choices(non_draft_statuses, weights=non_draft_weights, k=1)[0]`. Preserves determinism (faker_seed=42). |
| Called in `generate()` before returning | ✅ PASS | `ads.py:507` — `self._deduplicate_drafts(ads, statuses, weights)` called after the generation loop, before `return ads` at line 508. |
| Handles all-DAFT edge case with PUBLISHED fallback | ✅ PASS | `ads.py:595-597` — if `non_draft_statuses` is empty (all-DAFT distribution), falls back to `non_draft_statuses = [AdStatus.PUBLISHED]`, `non_draft_weights = [1.0]`. Mirrors `_normalize_weights` fallback pattern. Unit tests with `{"draft": 1.0}` pass (see below). |
| Timestamp fields set correctly | ✅ PASS | `_set_status_timestamp()` helper (`ads.py:545-567`) sets `published_at`, `archived_at`, `rejected_at`, or `moderation_failed_at` depending on the reassigned status. Called at `ads.py:608`. |
| `TestAdGenerator` unit tests pass | ✅ PASS | 13 passed (includes `test_no_transition_to_called` with 20% DRAFT weight, `test_status_distribution_default`). |
| `TestAdGeneratorMultiLang` tests pass | ✅ PASS | 13 passed (includes `test_original_language_set`, `test_deterministic_multi_language`, `test_fallback_template_for_unknown_category` — all use `{"draft": 1.0}`). |
| `TestSeedFilterCoverage` (seed-marked) tests pass | ✅ PASS | 13 passed, including `test_seed_filter_by_feature_returns_results`. |
| `TestSeedCategoryIntegration` (seed-marked) tests pass | ✅ PASS | Included in the 13 passed seed-marked tests. |
| No schema changes | ✅ PASS | Constraint `uq_ads_single_draft_per_user` left intact; generator now respects it. |

**Git diff confirms:** 68 lines added — `_set_status_timestamp()` (23 lines) and `_deduplicate_drafts()` (42 lines) — plus the call site at line 507.

---

### Fix 5 — Test fixture draft duplication (Category A)

| Checklist item | Status | Evidence |
|---|---|---|
| Second DRAFT changed to REJECTED | ✅ PASS | `test_ads_published.py:44` — `create_test_ad(seller, category, city, title="Rejected Ad 2", status=AdStatus.REJECTED)`. Diff: changed from `title="Another Draft", status=AdStatus.DRAFT`. |
| Test assertions hold (6 total ads, ads_published == 3) | ✅ PASS | Full fast gate: 1,570 passed. `test_ads_published_counts_only_published` asserts `ads_published == 3` (3 PUBLISHED + 1 DRAFT + 2 REJECTED). `test_per_ad_stats_includes_all_ads` asserts `len(per_ad_stats) == 6`. Both pass. |
| Fixture docstring updated | ✅ PASS | `test_ads_published.py:38` — `"Create 3 published + 1 draft + 2 rejected ads for the seller."`. Comment at line 71 also updated: `"# 3 published + 1 draft + 2 rejected = 6 total ads"`. |

**Constraint verification:** `uq_ads_single_draft_per_user` (ads/models.py:352-356) is a `UniqueConstraint(fields=["user_id"], condition=Q(status=AdStatus.DRAFT))`. Only DRAFT ads are constrained — 2 REJECTED ads per user is allowed. The fixture now has exactly 1 DRAFT per seller, satisfying the constraint.

---

## 3. Code Quality Verification

| Check | Status | Evidence |
|---|---|---|
| `ruff check` on all 6 files | ✅ PASS | "All checks passed!" — no lint errors on any file. |
| `basedpyright` on changed files | ✅ PASS | "0 errors, 0 warnings, 0 notes" — covers `sanitize.py`, `api_bulk.py`, `telegram_tags.py`, `ads.py`, `test_ads_published.py`. (Note: migrations are excluded from type-checking by convention.) |
| No `print()` statements | ✅ PASS | `api_bulk.py` uses `logger.warning`; no `print()` introduced in any file. |
| English-only comments/logs | ✅ PASS | All docstrings, comments, and log messages are in English. |
| No unrelated modifications | ✅ PASS | Git diff reviewed — changes are strictly scoped to the 5 fixes. Each file's change matches its checklist exactly. |

---

## 4. Test Run Results

### Full fast gate (non-seed, `PYTEST_SKIP_MARKERS=seed`)
```
1570 passed, 371 warnings in 106.11s
```
- 0 failures, 0 errors
- Warnings are all pre-existing (naive datetime, staticfiles directory, cache key) — unrelated to the changes

### Affected tests (confirmed within fast gate)
| Test | File | Result |
|---|---|---|
| `test_makemigrations_check` | `core/tests/test_migrations.py` | ✅ PASS |
| `test_empty_body_returns_422` | `moderation/tests/test_priority_service.py::TestBulkModerationActionView` | ✅ PASS |
| `test_malformed_json_body_returns_422` | `moderation/tests/test_priority_service.py::TestBulkModerationActionView` | ✅ PASS |
| `test_home_renders_catalog_header` | `ads/tests/test_auth_nav.py::TestAnonymousHeader` | ✅ PASS |
| `test_detail_renders_catalog_header` | `ads/tests/test_auth_nav.py::TestAnonymousHeader` | ✅ PASS |
| `test_ads_published_counts_only_published` | `analytics/tests/test_ads_published.py::TestAdsPublishedMetric` | ✅ PASS |
| `test_per_ad_stats_includes_all_ads` | `analytics/tests/test_ads_published.py::TestAdsPublishedMetric` | ✅ PASS |

### Seed generator unit tests (non-seed-marked, includes `{"draft": 1.0}` edge case)
```
13 passed in 8.68s
```
Classes: `TestAdGenerator`, `TestAdGeneratorMultiLang`

### Seed-marked integration tests
```
13 passed, 37 warnings in 52.14s
```
Classes: `TestSeedFilterCoverage`, `TestSeedCategoryIntegration`
- Includes `test_seed_filter_by_feature_returns_results` ✅
- Includes `test_seed_filter_by_condition_returns_results` ✅
- Includes `test_seed_filter_by_purpose_returns_results` ✅
- Includes `test_seed_populates_condition`, `test_seed_populates_features`, `test_seed_populates_listing_purpose` ✅
- Includes `test_seed_no_ad_has_both_new_and_used_features` ✅
- Includes `test_seed_charity_has_no_features` ✅
- Includes `test_full_seed_with_builder_categories` ✅

### i18n completeness tests
```
9 passed in 9.90s
```

### Auth Nav tests (explicit i18n test verification)
```
9 passed, 9 warnings in 10.48s
```
- Includes both catalog header tests with verbose output

---

## 5. Warnings

| Category | Description | Severity |
|---|---|---|
| None | No architectural, maintainability, or rollout risks identified. All fixes are minimal, backward-compatible, and independently verifiable. | — |

---

## 6. Required Fixes

None. All 5 fixes are correctly implemented and verified.

---

## 7. Advisory Recommendations

None. The implementation follows all existing project patterns (StrEnum, type hints, logging conventions, i18n best practices) and introduces no new abstractions beyond the single targeted helper function.

---

## 8. Overall Assessment

**ACCEPTED.** All 5 fixes match the architectural decisions documented in `11-failing-tests-solution-decisions.md`. Each fix:

1. **D** — Migration help_text synced to match model (documentation-only, no schema change)
2. **C** — Pydantic errors sanitized via `pydantic_errors_json()` helper, full errors logged server-side before stripping, CWE-209 compliant
3. **B** — `gettext` → `gettext_lazy` with correct `Promise` type annotation; `str()` resolves at render time
4. **E** — `_deduplicate_drafts()` enforces the `uq_ads_single_draft_per_user` constraint in seed generation, with DRAFT-only fallback and proper timestamp backfill
5. **A** — Test fixture corrected (2nd DRAFT → REJECTED), docstring/comment updated, assertions verified

**Test results:** 1,570 passed (fast gate) + 13 passed (seed unit) + 13 passed (seed integration) + 9 passed (i18n) + 9 passed (auth_nav) = **1,614 total test passes, 0 failures**.

**Lint:** `ruff check` — all checks passed on all 6 files.  
**Types:** `basedpyright` — 0 errors, 0 warnings, 0 notes on all changed files.
