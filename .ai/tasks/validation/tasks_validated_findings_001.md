# Task Validation Report — Phase 2 Implementation Tasks

**Generated:** 2026-07-28  
**Tasks analyzed:** 60  
**Source:** `.ai/tasks/todo/`

---

## Executive Summary

After comprehensive analysis, **8 tasks are REJECTED** due to critical issues, while **52 tasks are APPROVED** with warnings. The primary concerns are:

1. **Invalid semantic targets** - Tasks reference non-existent symbols or incorrect insertion anchors
2. **Missing file paths** - Tasks target files that don't exist or use incorrect paths
3. **Hidden file lock conflicts** - Same-file edits with inconsistent ordering
4. **Missing dependency declarations** - Tasks depend on same-file edits but don't declare `file_lock`

---

## Approved Tasks

### Phase 1: Foundation (Enums)

| Task | Status | Notes |
|------|--------|-------|
| TASK_001_Add_ad_FK_to_AnalyticsEvent | ✅ APPROVED | Valid target (AnalyticsEvent class exists), clear semantic anchor |
| TASK_002_Add_AD_VIEWED_to_AnalyticsEventType | ✅ APPROVED | Valid target (AnalyticsEventType class exists) |
| TASK_003_Add_TimeRange_StrEnum | ✅ APPROVED | New class creation, valid file target |
| TASK_004_Extend_AnalyticsEventType_trust_moderation | ⚠️ APPROVED WITH WARNING | Targets existing class, but semantic anchor references non-existent `CONTACT_RESPONSE` field that is added by TASK_036 |
| TASK_005_Add_TrustLevel_StrEnum | ✅ APPROVED | Valid target, new class creation |
| TASK_006_Add_AdPriorityLevel_StrEnum | ✅ APPROVED | Valid target, new class creation |
| TASK_007_Add_ThumbnailSizeStrEnum | ✅ APPROVED | Valid target, new class creation |
| TASK_016_Add_SearchSuggestionSource_enum | ✅ APPROVED | Valid target, new class creation |
| TASK_027_Extend_AdvisoryLockId_for_phases | ✅ APPROVED | Valid target, valid field reference (PURGE_REJECTED_ADS exists) |
| TASK_036_Add_CONTACT_RESPONSE_event | ✅ APPROVED | Valid target, valid field reference (CONTACT_INITIATED exists) |

### Phase 2: Model Changes

| Task | Status | Notes |
|------|--------|-------|
| TASK_008_Create_migration_ad_field | ✅ APPROVED | Depends on TASK_001, valid migration target |
| TASK_010_Create_media_app_structure | ✅ APPROVED | New module structure creation |
| TASK_012_Add_AdImage_thumbnail_fields | ✅ APPROVED | Valid target (AdImage class exists), valid anchor (image_url property exists) |
| TASK_013_Create_migration_thumbnail_fields | ✅ APPROVED | Depends on TASK_012 |
| TASK_019_Create_AdModerationPriority_model | ✅ APPROVED | New model in existing app |
| TASK_037_Create_migration_saved_search_models | ⚠️ APPROVED WITH WARNING | Depends on TASK_017 which has invalid file path (see Rejection #4) |
| TASK_038_Create_migration_trust_models | ⚠️ APPROVED WITH WARNING | Depends on TASK_018 which has invalid file path (see Rejection #6) |
| TASK_039_Create_migration_moderation_priority | ⚠️ APPROVED WITH WARNING | Depends on TASK_019 which has invalid file path (see Rejection #7) |
| TASK_040_Create_migration_daily_ad_metrics | ⚠️ APPROVED WITH WARNING | Depends on TASK_025 which has valid file path but conflicts with TASK_001 (see Warnings) |

### Phase 3: Service Layer

| Task | Status | Notes |
|------|--------|-------|
| TASK_009_Create_SellerStats_service | ✅ APPROVED | New service file, depends on valid prerequisites |
| TASK_011_Implement_ThumbnailService | ✅ APPROVED | New service file in apps/media/ |
| TASK_020_Create_TrustCalculator_service | ⚠️ APPROVED WITH WARNING | Valid target file path, but file doesn't exist yet (new file) |
| TASK_021_Create_PriorityCalculator_service | ⚠️ APPROVED WITH WARNING | Similar to above |
| TASK_024_Create_alert_query_service | ⚠️ APPROVED WITH WARNING | Depends on TASK_017 with invalid path |
| TASK_026_Create_TrustAnalytics_service | ⚠️ APPROVED WITH WARNING | Valid target file, but file needs to be created in trust app |
| TASK_033_Create_ModerationAnalytics_service | ⚠️ APPROVED WITH WARNING | Depends on TASK_004 |
| TASK_048_Add_sanitize_autocomplete_query | ✅ APPROVED | Standalone utility function |
| TASK_049_Create_popular_search_service | ⚠️ APPROVED WITH WARNING | Depends on TASK_014 (invalid path) |
| TASK_050_Create_search_history_service | ⚠️ APPROVED WITH WARNING | Depends on TASK_015 (invalid path) |
| TASK_051_Create_entity_suggestions_service | ⚠️ APPROVED WITH WARNING | Depends on TASK_016 |
| TASK_054_Create_rate_limit_service | ⚠️ APPROVED WITH WARNING | Depends on TASK_023 |

### Phase 4: Integration

| Task | Status | Notes |
|------|--------|-------|
| TASK_022_Add_telegram_premium_to_User | ✅ APPROVED | Valid target (User class exists), valid field anchor (ads_auto_publish exists) |
| TASK_023_Add_CACHES_setting | ✅ APPROVED | Valid target (base.py exists) |
| TASK_028_Add_AdImage_thumbnail_url_properties | ⚠️ APPROVED WITH WARNING | Depends on TASK_012 |
| TASK_029_Integrate_SellerStats_into_DashboardView | ✅ APPROVED | Valid target (dashboard function exists) |
| TASK_030_Create_TrustBadge_templates | ⚠️ APPROVED WITH WARNING | Depends on TASK_005 |
| TASK_031_Create_trust_template_tags | ⚠️ APPROVED WITH WARNING | Depends on TASK_018 (invalid path) |
| TASK_032_Create_AutocompleteView | ⚠️ APPROVED WITH WARNING | Depends on multiple tasks with invalid paths |
| TASK_034_Create_rollup_daily_metrics_command | ⚠️ APPROVED WITH WARNING | Complex dependencies |
| TASK_035_Update_auto_moderation_for_extended_events | ✅ APPROVED | Valid targets (functions exist), depends on valid prerequisites |
| TASK_052_Register_apps_trust_in_settings | ⚠️ APPROVED WITH WARNING | Depends on TASK_018 (invalid path) |
| TASK_053_Hook_trust_score_to_auto_moderation | ✅ APPROVED | Valid target (auto_moderation.py exists) |
| TASK_055_Integrate_ThumbnailService_into_bot | ❌ INVALID TARGET (see Rejection #1) |
| TASK_056_Record_AD_VIEWED_in_ad_detail | ✅ APPROVED | Valid target (ad_detail exists) |

### Phase 5: Test Tasks

| Task | Status | Notes |
|------|--------|-------|
| TASK_041_Test_SellerStats_service | ✅ APPROVED | Properly structured test task |
| TASK_042_Test_ThumbnailService | ✅ APPROVED | Valid test target |
| TASK_043_Test_TrustCalculator | ⚠️ APPROVED WITH WARNING | Depends on TASK_020 |
| TASK_044_Test_PriorityCalculator | ⚠️ APPROVED WITH WARNING | Depends on TASK_021 |
| TASK_057_Test_TrustAnalytics_service | ⚠️ APPROVED WITH WARNING | Depends on TASK_026 |
| TASK_058_Test_ModerationAnalytics_service | ⚠️ APPROVED WITH WARNING | Depends on TASK_033 |
| TASK_059_Test_rollup_daily_metrics | ⚠️ APPROVED WITH WARNING | Depends on TASK_034 |

### Phase 6: Verification Tasks

| Task | Status | Notes |
|------|--------|-------|
| TASK_045_Verify_Seller_Dashboard_Statistics | ⚠️ APPROVED WITH WARNING | Depends on multiple tasks |
| TASK_046_Verify_Trust_Signals_System | ⚠️ APPROVED WITH WARNING | Depends on TASK_018/020 |
| TASK_047_Verify_Moderation_Queue | ⚠️ APPROVED WITH WARNING | Depends on TASK_021 |
| TASK_060_Final_Validation_Phase_2 | ✅ APPROVED | Final verification, properly structured |

---

## Rejected Tasks

### Rejection #1 — TASK_055_Integrate_ThumbnailService_into_bot.yaml

**Reason:** Invalid semantic target - function `save_photo_with_thumbnails` does not exist in target file.

**Evidence:**
- Target file: `src/telegram_bot/handlers/ad_create.py`
- Target function: `save_photo_with_thumbnails` 
- Actual file contains: `save_photo` function (line 452) and `update_ad_and_moderate` function (line 534)
- Task targets a non-existent function to integrate into

**Unsafe Areas:**
- The task would require creating the function or renaming `save_photo`, which is not specified
- The `thumbnail_small`, `thumbnail_medium`, `thumbnail_large` fields don't exist in `AdImage` until TASK_012 completes

**Required Fixes:**
- Target existing function `save_photo` or `update_ad_and_moderate`
- Ensure TASK_012 completes before integration

---

### Rejection #2 — TASK_004_Extend_AnalyticsEventType_trust_moderation.yaml

**Reason:** Invalid semantic anchor - `insert_after: CONTACT_RESPONSE` references a field that doesn't exist yet.

**Evidence:**
- Target file: `apps/core/enums.py`
- Current enum values end with `CONTACT_INITIATED = "contact_initiated"` (line 58)
- Task specifies `insert_after: CONTACT_RESPONSE` but `CONTACT_RESPONSE` is added by TASK_036

**Unsafe Areas:**
- Semantic target will fail when TASK_004 runs before TASK_036
- Order.yaml shows correct sequencing but task file has incorrect anchor

**Required Fixes:**
- Change anchor to `insert_after: CONTACT_INITIATED` (or `SELLER_VERIFIED` if re-ordered)
- Update task to use stable anchor

---

### Rejection #3 — TASK_036_Add_CONTACT_RESPONSE_event.yaml

**Reason:** Semantic target confusion — task ordering in order.yaml may cause anchor conflicts.

**Evidence:**
- Task is placed at position 5 in enum chain (line 19-21 of order.yaml)
- However, TASK_004 (which depends on TASK_002) is supposed to add multiple events including those that should come after CONTACT_RESPONSE
- The order.yaml shows TASK_004 at position 4, TASK_036 at position 5, but TASK_004 specifies `insert_after: CONTACT_RESPONSE` which doesn't exist until TASK_036

**Unsafe Areas:**
- The ordering creates an impossible insertion scenario
- TASK_004 cannot insert after CONTACT_RESPONSE if CONTACT_RESPONSE hasn't been added yet

**Required Fixes:**
- Reorder TASK_004 and TASK_036, or
- Change TASK_004's anchor to insert after `CONTACT_INITIATED` instead of `CONTACT_RESPONSE`

---

### Rejection #4 — TASK_014_Create_PopularSearch_model.yaml

**Reason:** Invalid file path — `apps/search/models.py` does not exist.

**Evidence:**
- File system search shows: `apps/search/` contains only `apps.py`, `tests.py`, `urls.py`, `__init__.py`
- No `models.py` file exists in the search app

**Unsafe Areas:**
- Task would create a new file but specifies path that doesn't exist
- Would result in file creation error

**Required Fixes:**
- Create `apps/search/models.py` first, or
- Use correct path if models should be in separate module files

---

### Rejection #5 — TASK_015_Create_SearchHistory_model.yaml

**Reason:** Same as #4 — invalid file path.

**Evidence:**
- Same target file `apps/search/models.py` does not exist

**Required Fixes:**
- Same as #4

---

### Rejection #6 — TASK_018_Create_Trust_models.yaml

**Reason:** Invalid file path — `apps/trust/models.py` does not exist (trust app doesn't exist).

**Evidence:**
- No `apps/trust/` directory exists in the codebase
- Task targets a non-existent Django app

**Unsafe Areas:**
- Would require creating the entire trust app structure first
- Task assumes trust app exists

**Required Fixes:**
- Create `apps/trust/` module structure first (missing prerequisite)
- Add `apps.trust` to INSTALLED_APPS before this task

---

### Rejection #7 — TASK_019_Create_AdModerationPriority_model.yaml

**Reason:** Invalid file path — places new model in existing `apps/moderation/models.py` but order.yaml doesn't reflect file lock.

**Evidence:**
- File `apps/moderation/models.py` exists
- Task creates `AdModerationPriority` model
- No file_lock declared despite potentially conflicting with other tasks

**Unsafe Areas:**
- No explicit coordination with other moderation model edits

**Required Fixes:**
- Add `file_lock: apps/moderation/models.py` to task or order.yaml
- Add missing dependency on AdPriorityLevel enum

---

### Rejection #8 — TASK_017_Create_SavedSearch_models.yaml

**Reason:** Invalid file path — `apps/search/models/saved_search.py` implies nested models directory that doesn't exist.

**Evidence:**
- Target path: `apps/search/models/saved_search.py`
- Actual search app has no `models/` directory structure

**Unsafe Areas:**
- Directory structure doesn't match task specification

**Required Fixes:**
- Either create `apps/search/models/` directory structure, or
- Use `apps/search/models.py` as the target path

---

## Dependency Warnings

### Warning D1 — Hidden File Lock Dependencies in Enum Chain

Tasks modifying `apps/core/enums.py` use `file_lock` in `order.yaml` but the semantic anchors are inconsistent:

- TASK_002: `insert_after: CONTACT_INITIATED` ✓
- TASK_004: `insert_after: CONTACT_RESPONSE` ✗ (CONTACT_RESPONSE doesn't exist yet)
- TASK_036: `insert_after: CONTACT_INITIATED` (same anchor as TASK_002!)

**Risk:** Multiple tasks inserting after the same field will cause conflicts.

**Recommendation:** Review and fix semantic anchors to use unique stable insertion points.

---

### Warning D2 — Missing Prerequisite for Trust App

TASK_018 and following tasks assume `apps/trust/` exists but:
- No task creates the trust app structure
- TASK_052 registers `apps.trust` but depends on TASK_018, not vice versa
- Dependency direction is inverted

**Risk:** Django will fail to load models if app isn't registered before migrations.

**Required Fix:** Add task to create `apps/trust/` structure, or invert TASK_052 dependency

---

### Warning D3 — Search Models Path Inconsistency

Tasks TARGET_014, TASK_015, TASK_017, TASK_037 all target non-existent or incorrectly structured paths:

| Task | Target Path | Actual State |
|------|-------------|--------------|
| 014 | `apps/search/models.py` | Does not exist |
| 015 | `apps/search/models.py` | Does not exist |
| 017 | `apps/search/models/saved_search.py` | Directory doesn't exist |
| 037 | Migration for saved_search | Dependent on non-existent models |

**Risk:** Execution will fail due to missing files/directories.

---

### Warning D4 — CACHES Setting Dependency Fragility

TASK_023 adds CACHES to base.py, but:
- Task_009 (SellerStats) and TASK_054 (rate_limit) depend on this
- No verification that CACHES is properly configured before service tasks run

**Risk:** Services may fail if cache isn't available in test/dev environments.

---

## Semantic Stability Warnings

### Warning S1 — Enum Insertion Chain Fragility

The enum modification chain relies on sequential execution with shared `file_lock`. However:

1. TASK_003 (TimeRange) is placed OUTSIDE the enum chain in order.yaml (line 43-44)
2. TASK_003 depends on nothing but is needed by TASK_009
3. Tasks 004 and 036 both target insertion after CONTACT_INITIATED

**Risk:** Race conditions or merge conflicts in the enum file.

---

### Warning S2 — Multiple Same-File Edit Tasks Without Explicit Coordination

Tasks modifying `apps/search/models.py` (014, 015, 017):
- Use `insert_position: module:end` 
- No `file_lock` in task files themselves
- `insert_before: image_url` in TASK_012 is correct (property exists)

**Risk:** Inconsistent ordering may cause merge issues.

---

## Rollout Warnings

### Warning R1 — Media App Registration Timing

TASK_052 (register apps) depends on TASK_010 (create media app structure) and TASK_018 (trust models). However:

- TASK_055 (integrate into bot) depends on TASK_010 and TASK_028
- If TASK_052 runs after TASK_055, the bot may import ThumbnailService before Django is configured

**Risk:** Import errors in bot process.

**Recommendation:** TASK_052 should run earlier, or remove dependency on TASK_010.

---

### Warning R2 — Test Tasks May Execute Before Implementation Complete

TASK_043 (Test TrustCalculator) and TASK_044 (Test PriorityCalculator) depend only on service creation tasks but not on their enum prerequisites:

- TASK_043 depends on TASK_020 but TASK_020 depends on TASK_018 (TrustLevel enum)
- TASK_044 depends on TASK_021 but TASK_021 depends on TASK_019 (AdPriorityLevel enum)

Order.yaml shows correct transitive dependencies, but tests should explicitly depend on all prerequisites.

---

## Required Corrections

### Critical (Must Fix Before Execution)

1. **Fix TASK_004 semantic anchor**: Change `insert_after: CONTACT_RESPONSE` to `insert_after: CONTACT_INITIATED`
2. **Create apps/search/models.py** or adjust all search model tasks to use correct paths
3. **Create apps/trust/ structure** before TASK_018, or add prerequisite task
4. **Fix TASK_055 targets**: Target existing functions (`save_photo`, `update_ad_and_moderate`) or clarify that `save_photo_with_thumbnails` must be created
5. **Reorganize enum chain**: Ensure insertion anchors are stable and unique

### Recommended (Should Fix)

1. Add explicit `file_lock` declarations to task files that modify shared files
2. Move TASK_052 earlier in the rollout (before TASK_055)
3. Add verification that all model prerequisites exist before migration tasks

---

## Task File Renaming

Per workflow requirements, rejected tasks must be renamed with `_REJECTED` suffix:

```
TASK_055_Integrate_ThumbnailService_into_bot.yaml → TASK_055_Integrate_ThumbnailService_into_bot_REJECTED.yaml
TASK_004_Extend_AnalyticsEventType_trust_moderation.yaml → TASK_004_Extend_AnalyticsEventType_trust_moderation_REJECTED.yaml
TASK_036_Add_CONTACT_RESPONSE_event.yaml → TASK_036_Add_CONTACT_RESPONSE_event_REJECTED.yaml
TASK_014_Create_PopularSearch_model.yaml → TASK_014_Create_PopularSearch_model_REJECTED.yaml
TASK_015_Create_SearchHistory_model.yaml → TASK_015_Create_SearchHistory_model_REJECTED.yaml
TASK_018_Create_Trust_models.yaml → TASK_018_Create_Trust_models_REJECTED.yaml
TASK_019_Create_AdModerationPriority_model.yaml → TASK_019_Create_AdModerationPriority_model_REJECTED.yaml
TASK_017_Create_SavedSearch_models.yaml → TASK_017_Create_SavedSearch_models_REJECTED.yaml
```

---

## Conclusion

The task specification has a solid foundation but requires corrections to:
- Fix invalid semantic targets
- Resolve file path inconsistencies
- Correct dependency ordering for the trust app
- Stabilize the enum insertion chain

Once the above corrections are made, the rollout graph is viable for execution.