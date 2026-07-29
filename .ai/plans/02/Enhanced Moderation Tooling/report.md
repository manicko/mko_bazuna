# Enhanced Moderation Tooling — Implementation Verification Report

**Plan file:** `.ai/plans/02/Enhanced Moderation Tooling/plan.md`
**Date:** 2026-07-29
**Scope:** Verify whether each task in the plan is implemented in the actual codebase.
**Codebase root:** `src/backend/`
**Method:** Static inspection of source files, migrations, templates, and cross-referencing via grep for all plan symbols. No code was modified.

---

## Executive Summary

The plan defines 11 tasks (T1–T11) across 4 logical layers: enums, model, service/calculator, views, admin, signals, migration, and URL/template wiring.

**Result: 4 of 11 tasks implemented. 7 of 11 tasks NOT implemented.**

The foundation layer (enum, model, calculator, migration) is in place, but the entire integration layer — the `PriorityService` that ties everything together, the queue view, the bulk API, the admin enhancements, the auto-calculation signal, the advisory lock constant, and the URL/template wiring — is entirely absent.

| Task | Symbol | File | Status |
|------|--------|------|--------|
| T1 | `AdPriorityLevel` | `apps/core/enums.py` | ✅ Implemented |
| T2 | `AdModerationPriority` | `apps/moderation/models.py` | ✅ Implemented (minor deviations) |
| T3 | `PriorityCalculator` | `apps/moderation/services/priority_calculator.py` | ✅ Implemented (minor deviations) |
| T4 | `PriorityService` | `apps/moderation/services/priority.py` | ❌ NOT implemented |
| T5 | `moderation_queue` | `apps/moderation/views/queue.py` | ❌ NOT implemented |
| T6 | `EnhancedAdAdmin` | `apps/moderation/admin.py` | ❌ NOT implemented |
| T7 | `calculate_ad_priority` | `apps/moderation/signals.py` | ❌ NOT implemented |
| T8 | `bulk_moderation_action` | `apps/moderation/views/api_bulk.py` | ❌ NOT implemented |
| T9 | `AdvisoryLockId.QUEUE_PROCESSING` | `apps/core/enums.py` | ❌ NOT implemented |
| T10 | queue URL + template | `apps/moderation/urls.py` + `templates/...` | ❌ NOT implemented |
| T11 | Migration 0003 | `apps/moderation/migrations/0003_ad_moderation_priority.py` | ✅ Implemented (minor deviations) |

---

## Detailed Findings

### T1: AdPriorityLevel StrEnum — ✅ IMPLEMENTED

**File:** `src/backend/apps/core/enums.py` (lines 82–87)

The `AdPriorityLevel(StrEnum)` enum is present with `HIGH`, `MEDIUM`, `LOW` values, matching the plan exactly. It is included in the module `__all__` list (line 175).

```python
class AdPriorityLevel(StrEnum):
    """Priority levels for moderation queue triage."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
```

**No deviations.**

---

### T2: AdModerationPriority Model — ✅ IMPLEMENTED (minor deviations)

**File:** `src/backend/apps/moderation/models.py` (lines 133–164)

The `AdModerationPriority` model exists with all required fields:

| Field | Type | Plan | Actual |
|-------|------|------|--------|
| `ad` | OneToOneField | `"ads.Ad"`, CASCADE, `related_name="moderation_priority"` | ✅ Matches |
| `base_score` | PositiveSmallIntegerField | `default=0` + help_text | ✅ Type/default match; **no help_text** |
| `priority_level` | CharField | `max_length=10`, choices, `default=MEDIUM` | ✅ Type/choices match; **no `default=AdPriorityLevel.MEDIUM`** |
| `flags` | JSONField | `default=list`, `blank=True` | ✅ Matches |
| `confidence_score` | FloatField | `default=0.0` | ✅ Matches |
| `escalation_required` | BooleanField | `default=False` | ✅ Matches |
| Meta | db_table + indexes | 3 indexes | ✅ All 3 indexes present |

**Deviations (cosmetic, non-breaking):**

1. **`db_table` name differs:** Plan specifies `"ad_moderation_priority"`; actual is `"ad_moderation_priorities"` (plural). This is internally consistent (model Meta and migration both use the plural form).
2. **Missing `help_text`:** The plan adds `help_text` to `base_score`, `confidence_score`, and `escalation_required`. The actual implementation omits all `help_text` attributes.
3. **Missing `default` on `priority_level`:** The plan specifies `default=AdPriorityLevel.MEDIUM`; the actual field has no default. This means a new `AdModerationPriority` row created without explicitly setting `priority_level` would raise an `IntegrityError` at the database level (no NULL allowed, no default). However, since `PriorityCalculator.calculate_priority()` always returns a `priority_level` value, and the (unimplemented) `PriorityService` always passes it via `update_or_create` defaults, this is not currently a runtime risk — but it is a latent risk if the model is ever instantiated directly.

**Assessment:** Functionally correct. Deviations are documentation/robustness gaps, not behavioral bugs.

---

### T3: PriorityCalculator Service — ✅ IMPLEMENTED (minor deviations)

**File:** `src/backend/apps/moderation/services/priority_calculator.py`

The `PriorityCalculator` class exists with all methods from the plan:

| Method | Plan | Actual |
|--------|------|--------|
| `calculate_priority(ad)` | ✅ | ✅ |
| `_calculate_content_score(ad)` | ✅ | ✅ |
| `_calculate_user_score(ad)` | ✅ | ✅ |
| `_get_priority_level(score)` | ✅ | ✅ |
| `_estimate_confidence(ad)` | ✅ | ✅ |

**Deviations (enhancements, not regressions):**

1. **Score capping added:** The plan's `_calculate_content_score` and `_calculate_user_score` return `{"score": score, "flags": flags}` without capping. The actual implementation adds `min(score, 100)` to both, capping scores at 100. This is a defensive enhancement that prevents overflow when many banned words or repeat-offender flags accumulate. The test suite (`test_priority.py`) explicitly validates this capping behavior (e.g., `test_banned_word_multiple_words_increase_score` expects content score capped at 100).
2. **Logging added:** The actual file imports `logging` and creates a module-level `logger`, which the plan does not show. This is consistent with project rule 12 (no `print()` statements; use logging).
3. **Pyright type-ignore comment:** The actual code has `# pyright: ignore[reportGeneralTypeIssues]` on the `for word in criteria.banned_words` line, which the plan does not show. This is a type-checker workaround for the JSONField return type.

**Assessment:** Fully implemented. Deviations are improvements aligned with project conventions and test expectations.

---

### T4: PriorityService — ❌ NOT IMPLEMENTED

**Planned file:** `src/backend/apps/moderation/services/priority.py`
**Status:** File does not exist.

The `services/` directory contains only:
- `__init__.py`
- `auto_moderation.py`
- `moderation_log.py`
- `priority_calculator.py`

There is no `priority.py`. A grep for `PriorityService` across the entire `src/backend/` tree returns **zero matches**.

**Impact:** This is a critical missing dependency. T5 (queue view), T6 (admin), T7 (signal), and T8 (bulk API) all depend on `PriorityService`. Without it, none of the downstream tasks can function even if their files were created. The `PriorityCalculator` (T3) is implemented but has no service wrapper to persist results to the `AdModerationPriority` model.

---

### T5: Moderation Queue View — ❌ NOT IMPLEMENTED

**Planned file:** `src/backend/apps/moderation/views/queue.py`
**Status:** File does not exist.

The `views/` directory contains only:
- `__init__.py`
- `review.py`

There is no `queue.py`. A grep for `moderation_queue` returns **zero matches** (the only match for `moderation_queues` is an unrelated list in `apps/ads/admin.py` line 122, which is a pre-existing quick-filter preset, not the planned priority queue view).

**Assessment:** The queue view function, the `_staff_required` decorator (which would be a duplicate of the one in `review.py`), and the priority-filtering logic are all absent.

---

### T6: EnhancedAdAdmin — ❌ NOT IMPLEMENTED

**Planned file:** `src/backend/apps/moderation/admin.py`
**Status:** The `EnhancedAdAdmin` class does not exist.

The actual `admin.py` contains only:
- `log_ad_link` (helper)
- `log_user_link` (helper)
- `ModerationCriteriaAdmin`
- `ModeratorActionLogAdmin`

There is no `EnhancedAdAdmin` class, no `list_filter` with `moderation_priority__priority_level`, no `get_queryset` override with `select_related`/`prefetch_related`, and no `changelist_view` override that injects `priority_queue_stats`.

A grep for `EnhancedAdAdmin` returns **zero matches**.

**Note:** The `Ad` model admin is registered in `apps/ads/admin.py` (not `apps/moderation/admin.py`). The plan's T6 shows `@admin.register(Ad)` in the moderation admin, which would conflict with the existing registration in `apps/ads/admin.py`. This suggests the plan may have intended to modify the `Ad` admin in `apps/ads/admin.py` rather than creating a new registration in the moderation app.

---

### T7: calculate_ad_priority Signal — ❌ NOT IMPLEMENTED

**Planned file:** `src/backend/apps/moderation/signals.py`
**Status:** The `calculate_ad_priority` receiver does not exist.

The actual `signals.py` contains only one signal handler:
- `invalidate_criteria_cache_on_save` — triggered on `ModerationCriteria` post_save.

There is no `calculate_ad_priority` receiver for `Ad` post_save. A grep for `calculate_ad_priority` returns **zero matches**.

**Signal infrastructure exists:** `apps/moderation/apps.py` (line 18) imports `apps.moderation.signals` in `ready()`, so any signal added to `signals.py` would be automatically registered. The wiring is in place; the signal handler itself was never written.

---

### T8: Bulk Moderation Actions API — ❌ NOT IMPLEMENTED

**Planned file:** `src/backend/apps/moderation/views/api_bulk.py`
**Status:** File does not exist.

There is no `api_bulk.py` in the `views/` directory. A grep for `bulk_moderation_action` returns **zero matches**.

**Partial related functionality exists:** `apps/moderation/admin_actions.py` contains `bulk_approve`, `bulk_reject`, `bulk_ban_users`, and `bulk_delete` functions (lines 127–209), and `apps/ads/admin.py` registers them as Django admin actions (`action_approve`, `action_ban_user`, `action_soft_delete`). However, these are admin-action-based bulk operations, not the JSON API endpoint (`bulk_moderation_action`) specified in the plan. The plan's T8 is a separate REST-style API view that accepts JSON POST with `action`, `selected_items`, and `reason` fields.

---

### T9: AdvisoryLockId.QUEUE_PROCESSING — ❌ NOT IMPLEMENTED

**Planned location:** `src/backend/apps/core/enums.py`, inside `AdvisoryLockId(IntEnum)`
**Status:** The `QUEUE_PROCESSING` constant does not exist.

The actual `AdvisoryLockId` enum (lines 20–32) contains:

| Member | Value |
|--------|-------|
| ARCHIVE_SWEEP | 1 |
| DELETE_SWEEP | 2 |
| CONSENT_HARD_DELETE | 3 |
| SWEEP_DRAFTS | 4 |
| CLEANUP_LOGIN_TOKENS | 5 |
| PURGE_FAILED_ADS | 6 |
| PURGE_REJECTED_ADS | 7 |
| ROLLUP_DAILY_METRICS | 8 |
| MIGRATE | 100 |
| CREATE_ADMIN | 101 |

The plan specifies `QUEUE_PROCESSING = 10`. Value `10` is not present. A grep for `QUEUE_PROCESSING` returns **zero matches**.

---

### T10: Queue URL and Template — ❌ NOT IMPLEMENTED

**Planned locations:**
- `src/backend/apps/moderation/urls.py` — add `path("queue/", moderation_queue, name="queue")`
- `templates/admin/moderation/queue.html` — Django template

**Status:** Both are absent.

The actual `urls.py` (lines 10–15) contains only:
```python
urlpatterns = [
    path("review/<int:ad_id>/", moderation_review, name="review"),
    path("approve/<int:ad_id>/", approve_ad, name="approve"),
    path("reject/<int:ad_id>/", reject_ad, name="reject"),
    path("ban/<int:ad_id>/", ban_user, name="ban"),
]
```

There is no `queue/` path. A grep for `queue.html` returns **zero matches** across the entire codebase. No HTML templates exist in the moderation app's template directory.

---

### T11: Migration 0003 for AdModerationPriority — ✅ IMPLEMENTED (minor deviations)

**File:** `src/backend/apps/moderation/migrations/0003_ad_moderation_priority.py`

The migration creates the `AdModerationPriority` model with all fields and indexes.

**Deviations:**

1. **Dependency differs from plan:** The plan specifies `("ads", "0003_add_index_conditions")` as a dependency. The actual migration depends on `("ads", "0007_adimage_thumbnails")`. This is **correct** — the plan's dependency was written before the actual migration history was finalized. The real `ads` app has migrations up to `0007`, so depending on `0007_adimage_thumbnails` is the accurate, working dependency. The plan's `0003_add_index_conditions` may not even exist in the real migration history.

2. **`db_table` name:** The migration uses `"ad_moderation_priorities"` (plural), consistent with the model's Meta. The plan specifies `"ad_moderation_priority"` (singular). Internally consistent in the actual code.

3. **Indexes in migration:** The plan's migration code shows a comment `# Indexes added via model Meta` and omits explicit index definitions. The actual migration includes all three indexes explicitly in the `options` dict (with auto-generated names). This is the standard Django behavior when `makemigrations` is run — indexes from `Meta.indexes` are serialized into the migration. Both approaches are functionally equivalent.

4. **`verbose_name="ID"` on id field:** The actual migration includes `verbose_name="ID"` on the auto-generated `id` field, which the plan omits. This is a Django auto-generation detail, not a meaningful deviation.

**Assessment:** The migration is correctly implemented and consistent with the model. The dependency difference is an improvement (reflects actual migration history), not a bug.

---

## Dependency Chain Analysis

The plan defines a dependency chain:

```
T1 (enum) ──┬── T2 (model) ──┬── T3 (calculator) ──┐
            │                ├── T4 (PriorityService) ──┬── T5 (queue view)
            │                ├── T6 (admin)             ├── T7 (signal)
            │                └── T11 (migration)        └── T8 (bulk API)
T9 (lock) ──┘
T10 (URL+template) depends on T5
```

**Current state of the chain:**

- **T1 → T2 → T3 → T11:** All implemented. The foundation is solid and internally consistent.
- **T4 (PriorityService):** NOT implemented. This is the single point of failure that breaks the entire downstream chain. T5, T6, T7, and T8 all import or call `PriorityService`.
- **T5, T6, T7, T8, T9, T10:** All NOT implemented. These are downstream of T4 (except T9 and T10 which are independent of T4 but still unimplemented).

**Critical observation:** Even if T5–T10 were implemented, they would fail at runtime because `PriorityService` (T4) does not exist. The `PriorityCalculator` (T3) is implemented but has no persistence layer — there is no code that calls `calculator.calculate_priority()` and saves the result to `AdModerationPriority`.

---

## Evidence Summary

All findings are based on direct file inspection:

| Verification method | Result |
|---------------------|--------|
| `apps/core/enums.py` read | `AdPriorityLevel` present (T1 ✅); `QUEUE_PROCESSING` absent (T9 ❌) |
| `apps/moderation/models.py` read | `AdModerationPriority` present (T2 ✅) |
| `apps/moderation/services/priority_calculator.py` read | `PriorityCalculator` present (T3 ✅) |
| `apps/moderation/services/` directory listing | `priority.py` absent (T4 ❌) |
| `apps/moderation/views/` directory listing | `queue.py` and `api_bulk.py` absent (T5 ❌, T8 ❌) |
| `apps/moderation/admin.py` read | `EnhancedAdAdmin` absent (T6 ❌) |
| `apps/moderation/signals.py` read | `calculate_ad_priority` absent (T7 ❌) |
| `apps/moderation/urls.py` read | queue path absent (T10 ❌) |
| `apps/moderation/migrations/0003_ad_moderation_priority.py` read | Migration present (T11 ✅) |
| Template search (`**/*.html` in moderation) | No templates found (T10 ❌) |
| Grep `PriorityService` across `src/backend/` | 0 matches (T4 ❌) |
| Grep `calculate_ad_priority` across `src/backend/` | 0 matches (T7 ❌) |
| Grep `QUEUE_PROCESSING` across `src/backend/` | 0 matches (T9 ❌) |
| Grep `bulk_moderation_action` across `src/backend/` | 0 matches (T8 ❌) |
| Grep `EnhancedAdAdmin` across `src/backend/` | 0 matches (T6 ❌) |
| Grep `moderation_queue\|queue\.html\|api_bulk` across `src/backend/` | 0 relevant matches (T5 ❌, T8 ❌, T10 ❌) |
| Grep `AdModerationPriority` across `src/backend/` | 5 matches: model definition, `__str__`, migration, priority_calculator docstring reference |

---

## Warnings

### Architectural Risk: Orphaned Model
The `AdModerationPriority` model (T2) and its migration (T11) are fully implemented, but no code anywhere in the codebase creates, reads, updates, or deletes `AdModerationPriority` records. The model exists in the database schema but is a dead table — no signal, service, or view populates it. This is a schema-only implementation with no runtime behavior.

### Architectural Risk: Duplicate `_staff_required` Decorator
The plan's T5 defines a `_staff_required` decorator in `views/queue.py`, but an identical decorator already exists in `views/review.py` (lines 17–25). If T5 were implemented as written, it would duplicate this decorator. A shared utility would be preferable.

### Architectural Risk: Ad Admin Registration Conflict
The plan's T6 registers `Ad` model admin in `apps/moderation/admin.py` via `@admin.register(Ad)`. However, `Ad` is already registered in `apps/ads/admin.py`. Django does not allow registering the same model twice — this would raise `AlreadyRegistered` at startup. The plan should instead modify the existing `Ad` admin in `apps/ads/admin.py`.

### Documentation Risk: Plan vs. Codebase Drift
The plan's T11 migration dependency (`("ads", "0003_add_index_conditions")`) does not match the actual migration history (`("ads", "0007_adimage_thumbnails")`). This indicates the plan was written before the migration history was finalized. The actual migration is correct; the plan is stale on this detail.

### Test Coverage Gap
The test file `tests/test_priority.py` (532 lines) comprehensively tests `PriorityCalculator` (T3) with 18 test methods covering banned word detection, user scoring, priority level mapping, escalation logic, and confidence estimation. However, there are **no tests** for `PriorityService` (T4), the queue view (T5), the bulk API (T8), or the signal (T7) — all of which are unimplemented.

---

## Required Fixes

1. **Implement T4 (`PriorityService`):** Create `apps/moderation/services/priority.py` with the `PriorityService` class (`calculate_and_save`, `get_queued_ads`, `get_priority_counts`). This is the single highest-priority missing piece — it unblocks T5, T6, T7, and T8.

2. **Implement T7 (`calculate_ad_priority` signal):** Add the `post_save` receiver for `Ad` in `apps/moderation/signals.py` that calls `PriorityService().calculate_and_save()` when an ad enters `ON_MODERATION` status. The signal infrastructure (apps.py `ready()`) is already wired.

3. **Implement T9 (`AdvisoryLockId.QUEUE_PROCESSING`):** Add `QUEUE_PROCESSING = 10` to the `AdvisoryLockId` enum in `apps/core/enums.py`.

4. **Implement T5 + T10 (queue view + URL + template):** Create `views/queue.py`, register the URL in `urls.py`, and create the `queue.html` template.

5. **Implement T8 (bulk moderation API):** Create `views/api_bulk.py` with the `bulk_moderation_action` endpoint.

6. **Implement T6 (EnhancedAdAdmin):** Modify the existing `Ad` admin in `apps/ads/admin.py` (NOT `apps/moderation/admin.py`) to add priority filters and queue stats. Do not create a duplicate `@admin.register(Ad)`.

7. **Fix T2 deviation:** Add `default=AdPriorityLevel.MEDIUM` to the `priority_level` field on `AdModerationPriority` to prevent potential `IntegrityError` on direct model instantiation.

---

## Advisory Recommendations

1. **Refactor `_staff_required` decorator:** Extract the `_staff_required` decorator from `views/review.py` into a shared utility (e.g., `apps/moderation/views/decorators.py` or `apps/core/utils/decorators.py`) to avoid duplication when T5 is implemented.

2. **Add `help_text` to `AdModerationPriority` fields:** The plan specifies `help_text` on `base_score`, `confidence_score`, and `escalation_required`. Adding these improves Django admin usability and aligns with the plan.

3. **Reconcile `db_table` naming:** The plan specifies `"ad_moderation_priority"` (singular) but the implementation uses `"ad_moderation_priorities"` (plural). Both are internally consistent; no action needed unless a specific naming convention is enforced. The current plural form follows Django's default convention.

4. **Add tests for PriorityService and signal:** The existing test suite covers `PriorityCalculator` thoroughly. Once T4 and T7 are implemented, add corresponding tests in `tests/test_priority_service.py` and `tests/test_signals.py`.

5. **Consider the `db_table` name in migration:** The migration's `db_table` (`"ad_moderation_priorities"`) matches the model's Meta. No migration change is needed for the T2 `default` fix if the field already has a database-level default — but since the current field has no default, adding one will require a new migration (e.g., `0004_ad_moderation_priority_priority_level_default`).

---

## Conclusion

The "Enhanced Moderation Tooling" plan is **partially implemented** — approximately 36% complete (4 of 11 tasks). The implemented portions (T1, T2, T3, T11) form a correct and consistent foundation: the enum, model, calculator, and migration are all present and internally aligned. The test suite for the calculator is comprehensive and passing.

However, the entire integration layer is missing. The `PriorityService` (T4) — the central orchestrator that connects the calculator to the model and exposes queue operations — does not exist. This single omission renders the implemented foundation inert: no code calls `calculate_priority()`, no `AdModerationPriority` records are ever created, and the model is a dead table in the database.

The remaining 7 tasks (T4–T10) represent the full integration layer: service, views, admin, signal, API, advisory lock, and URL/template wiring. None of these have been started.

**Recommendation:** Implement T4 (`PriorityService`) first, as it is the critical dependency for T5, T6, T7, and T8. Then implement T7 (signal) to activate automatic priority calculation. T9 is a trivial one-line addition. T5+T10 and T8 provide the user-facing queue and bulk operations. T6 requires careful integration with the existing `Ad` admin in `apps/ads/admin.py` to avoid a registration conflict.
