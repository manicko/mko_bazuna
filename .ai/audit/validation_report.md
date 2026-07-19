# Validation Report: Plans vs Tasks

**Date:** 2026-07-19
**Validator:** Validator Agent
**Source:** `.ai/plans/`, `.ai/tasks/todo/`, `.kilo/commands/plan/plan-tasks.md`

---

## Executive Summary

**Status:** APPROVED

The task set follows the semantic targeting requirements of `plan-tasks.md`, uses proper naming conventions, and maintains correct dependency ordering. All file paths align with plans. One **SPEC-DEVIATION** was found and corrected during validation (PostgreSQL version inconsistency in TASK_005 and TASK_011).

---

## Applied Fixes (First Pass)

| File | Change | Status |
|------|--------|--------|
| TASK_005_docker_compose_test.yaml | postgres:17 → postgres:18 | ✓ Fixed |
| TASK_011_docker_ci.yaml | postgres:17 → postgres:18 | ✓ Fixed |
| TASK_015_docker_wiki_alignment.yaml | postgres:17 → postgres:18 in goals | ✓ Fixed |

---

## Applied Fixes (Second Pass)

| File | Change | Status |
|------|--------|--------|
| TASK_051_phase4_nginx_hardening.yaml | Add `- task_007_docker_nginx` to `depends_on` | ✓ Fixed |
| order_04_phase4_analytics_harden.yaml | Add `task_007_docker_nginx` dependency | ✓ Fixed |

---

## Approved: Task Naming Convention Compliance

All 53 task files follow the required pattern `TASK_<XXX>_<task_id>_<short_name>.yaml`:

| Task ID Range | Naming Pattern | Status |
|--------------|----------------|--------|
| TASK_001-015 | Foundation infrastructure | ✓ Valid |
| TASK_016-020 | Roadmap coordination gates | ✓ Valid |
| TASK_021-033 | Phase 1 detailed tasks | ✓ Valid |
| TASK_034-040 | Phase 2 detailed tasks | ✓ Valid |
| TASK_041-047 | Phase 3 detailed tasks | ✓ Valid |
| TASK_048-053 | Phase 4 detailed tasks | ✓ Valid |

All task IDs use zero-padded sequential numbers (001-053) that preserve sortable execution order.

---

## Approved: Semantic Anchors (No Line Numbers)

All tasks use semantic targeting via `type: class`, `type: module`, `type: file` - **no line number references found**. This complies with rule 18 of `plan-tasks.md`: "DO NOT use line numbers — use semantic anchors".

---

## Approved: Dependency Graph Consistency

### Foundation → Phase 1 Dependencies (order_00 + order_01)

| Task | Plan Dependencies | Task Dependencies | Match |
|------|-------------------|-------------------|-------|
| task_021_phase1_structure_enums | Docker Tasks 0, 6 | task_006_docker_settings_package | ✓ |
| task_022_phase1_core_models | Task 21 | task_021_phase1_structure_enums | ✓ |
| task_023_phase1_categories_locations | Task 21 | task_021_phase1_structure_enums | ✓ |
| task_024_phase1_admin_registration | Tasks 22, 23, 25 | task_022, task_023, task_025 | ✓ |
| task_025_phase1_moderation_analytics_models | Task 21 | task_021_phase1_structure_enums | ✓ |
| task_026_phase1_search_triggers | Tasks 22, 23 | task_022, task_023 | ✓ |
| task_027_phase1_lifecycle_indexes | Task 22 | task_022_phase1_core_models | ✓ |
| task_028_phase1_settings_security | Tasks 21, 6 | task_021, task_006 | ✓ |
| task_029_phase1_deployment_wiring | Tasks 21, 2, 6, 7 | task_021, task_002, task_003, task_006, task_007 | ✓ |
| task_030_phase1_bot_fsm | Tasks 22, 23, 25, 1, 2, 7 | task_022, task_023, task_025, task_002, task_003, task_007 | ✓ |
| task_031_phase1_auto_moderation | Tasks 22, 25 | task_022, task_025 | ✓ |
| task_032_phase1_web_search_views | Tasks 22, 23, 27 | task_022, task_023, task_027 | ✓ |
| task_033_phase1_docs_sync | All Phase 1 tasks + Task 15 | Correct dependency chain | ✓ |

### Phase 1 → Phase 2 Dependencies (order_02)

All Phase 2 tasks correctly depend on Phase 1 tasks. Phase 2 owns advisory locks 6-7; Phase 1 Task 9 (scheduler) references these correctly.

### Phase 2 → Phase 3 Dependencies (order_03)

| Task | Plan Dependencies | Task Dependencies | Match |
|------|-------------------|-------------------|-------|
| task_041_phase3_contact_bridge | Phase 1 Tasks 9, 11 | task_030, task_032 | ✓ |
| task_042_phase3_dashboard_views | Phase 1 Task 11 | task_032_phase1_web_search_views | ✓ |
| task_043_phase3_account_states | Phase 1 Task 2 | task_022_phase1_core_models | ✓ |
| task_044_phase3_consent_soft_delete | Phase 1 Task 4 | task_025_phase1_moderation_analytics_models | ✓ |
| task_045_phase3_self_delete_ad | Task 42 | task_042_phase3_dashboard_views | ✓ |
| task_046_phase3_consent_banner | Tasks 7, 42 | task_028, task_042 | ✓ |
| task_047_phase3_docs_sync | All Phase 3 tasks | Correct chain | ✓ |

### Phase 3 → Phase 4 Dependencies (order_04)

All Phase 4 tasks correctly depend on appropriate Phase 3 and Phase 1/2 tasks. Lifecycle sweep commands (locks 1-5) properly imported from `apps.core.utils.advisory_lock`.

---

## SPEC-DEVIATION: PostgreSQL Version Mismatch (RESOLVED)

**Severity:** HIGH (Fixed during validation)  
**Finding:** Task files `TASK_005_docker_compose_test.yaml` and `TASK_011_docker_ci.yaml` specified `postgres:17` while the Docker plan specified `postgres:18`/`postgres:18-alpine`.

**Evidence (Before Fix):**
- `TASK_005_docker_compose_test.yaml` goal 19: `postgres:17 (no persistent volume)`
- `TASK_011_docker_ci.yaml` goal 19: `postgres:17 service with healthcheck`
- `TASK_015_docker_wiki_alignment.yaml` goals 19-20: `postgres:17-alpine` / `PG17`
- `00_detailed_plan_docker_environment.md`: `postgres:18-alpine` in Tasks 2, 4, 5 acceptance criteria

**Resolution:** Corrected to `postgres:18`/`postgres:18-alpine` to match canonical specification in `docs/wiki/02_packages.md`.

---

## SPEC-DEVIATION: Missing Dependency for nginx.conf Edit (RESOLVED)

**Severity:** MEDIUM
**Finding:** `TASK_051_phase4_nginx_hardening.yaml` targets `docker/nginx/nginx.conf` but depends on `task_029_phase1_deployment_wiring` instead of `task_007_docker_nginx` (the Foundation task that owns nginx.conf).

**Evidence:**
- `TASK_051_phase4_nginx_hardening.yaml` line 8-9: `depends_on: - task_029_phase1_deployment_wiring`
- `TASK_007_docker_nginx.yaml` creates `docker/nginx/nginx.conf` (Foundation owner)
- Description text claimed "coordinates via depends_on on task_007" but the actual `depends_on` did NOT include `task_007_docker_nginx`

**Resolution:** Added `- task_007_docker_nginx` to `depends_on` in both TASK_051 and order_04. The fix ensures nginx.conf exists before editing. Note: task_029 already depends on task_007, so the implicit dependency was already satisfied; the explicit dependency makes the intent clear.

---

## Approved: Advisory Lock ID Consistency

Lock allocation is correctly maintained across all plans and tasks:

| Lock ID | Command | Owner Plan | Status |
|---------|---------|------------|--------|
| 1 | archive_sweep | Phase 4 | ✓ Correct |
| 2 | delete_sweep | Phase 4 | ✓ Correct |
| 3 | consent_hard_delete | Phase 4 | ✓ Correct |
| 4 | sweep_drafts | Phase 4 | ✓ Correct |
| 5 | cleanup_login_tokens | Phase 4 | ✓ Correct |
| 6 | purge_failed_ads | Phase 2 | ✓ Correct |
| 7 | purge_rejected_ads | Phase 2 | ✓ Correct |
| 100 | migrate | Docker Plan | ✓ Correct |

All sweep tasks correctly import `advisory_lock` from `apps.core.utils.advisory_lock` and use transaction-scoped locks.

---

## Advisory: TASK_040 Dependency Already Captured

**Finding:** `TASK_040_phase2_docs_sync.yaml` exists and its dependency on `task_039` is already captured in `order_02_phase2_moderation.yaml` (line 31: `- task_039_phase2_cache_invalidation` → `task_040` implicitly follows).

**Status:** Advisory - No action needed. The dependency chain is correct.

---

## Advisory: File Path Pattern Inconsistency

Some task files use `type: module` with dotted path notation (e.g., `apps.core.enums`) while others use `type: file` with filesystem paths. This is functionally correct but not consistently applied.

**Examples:**
- `apps/core/enums.py`: `type: module` with `apps.core.enums` ✓
- `pyproject.toml`: `type: file` with `pyproject.toml` ✓
- Mixed usage in `TASK_001_docker_pyproject_reconcile.yaml`

---

## Approved: Single-Owner Rule Compliance

Foundation plan (00_detailed_plan_docker_environment.md) maintains sole ownership of:
- `pyproject.toml`, `uv.lock`
- `docker/Dockerfile`, `docker/entrypoint.sh`
- `docker-compose*.yml`
- `src/backend/config/settings/` package
- `docker/nginx/nginx.conf`

Feature phases correctly reference these as dependencies rather than recreating them. The `verifies` field in `TASK_029_phase1_deployment_wiring.yaml` properly documents this verification pattern.

---

## Approved: Roadmap Phase Gates

The roadmap coordination tasks (`TASK_016-020`) correctly sequence:
1. Foundation Gate (TASK_016) → depends on all Foundation tasks 001-015
2. Phase 1 Gate (TASK_017) → depends on Foundation Gate
3. Phase 2 Gate (TASK_018) → depends on Phase 1 Gate
4. Phase 3 Gate (TASK_019) → depends on Phase 2 Gate
5. Phase 4 Gate (TASK_020) → depends on Phase 3 Gate

---

## Rollout Analysis

### Execution Safety

1. **No circular dependencies detected** - All task graphs are DAG-valid.
2. **File-based sequential dependencies** properly encoded via `depends_on_previous_task_in_chain` pattern (infrastructure files modified by multiple tasks).
3. **Hidden dependencies** identified:
   - Phase 4 scheduler service depends on Phase 1 apps existing (correctly documented in plans)
   - Advisory lock utility must exist before sweep commands (correctly sequenced)

### Cross-Plan Contract Consistency

| Contract Item | Foundation Plan | Phase 1 | Phase 2 | Phase 3 | Phase 4 |
|--------------|-----------------|---------|---------|---------|---------|
| python:3.14-slim | ✓ | ✓ | ✓ | ✓ | ✓ |
| postgres:18 | ✓ | ✓ | ✓ | ✓ | ✓ |
| CONN_MAX_AGE=0 | ✓ | ✓ | ✓ | ✓ | ✓ |
| prepare_threshold=None | ✓ | ✓ | ✓ | ✓ | ✓ |
| advisory_lock util location | ✓ | ✓ | ✓ | ✓ | ✓ |
| Lock ID 1-5: Phase 4 | ✓ | N/A | N/A | N/A | ✓ |
| Lock ID 6-7: Phase 2 | ✓ | N/A | ✓ | N/A | N/A |
| Lock ID 100: migrate | ✓ | N/A | N/A | N/A | N/A |

---

## Required Fixes

**None remaining.** All SPEC-DEVIATION issues were corrected during validation.

---

## Advisory Recommendations

1. **Standardize target types** - Consider using `type: file` consistently with semantic anchors in changes descriptions, or document the module/file distinction for future planners.

2. **Add explicit ordering comment** - Consider adding a marker in `order_02_phase2_moderation.yaml` that `task_040_phase2_docs_sync` is implicitly included via `task_039` dependency.

---

## Second Validation Pass Summary (2026-07-19)

### Verified Items (All PASS)

1. **PostgreSQL version references** - All task goals now consistently use `postgres:18` or `postgres:18-alpine`:
   - TASK_005: `postgres:18` ✓
   - TASK_011: `postgres:18` ✓
   - TASK_015: `postgres:18-alpine` ✓
   - TASK_004 (Phase 1 plan): `postgres:18-alpine` ✓

2. **Advisory lock ID allocations** - Correct and consistent:
   - Phase 4 owns locks 1-5 (TASK_049 lifecycle sweeps)
   - Phase 2 owns locks 6-7 (TASK_037, TASK_038 purge commands)
   - migrate service uses lock 100 (Foundation)
   - All tasks properly import from `apps.core.utils.advisory_lock`

3. **Task dependencies referencing Docker plan** - All Foundation dependencies correctly referenced:
   - TASK_046_consent_banner → task_028 (Foundation settings) ✓
   - TASK_029_deployment_wiring → task_007 (Foundation nginx) ✓
   - TASK_042_dashboard → task_032 (Phase 1 web search) ✓

4. **Semantic anchors** - No line number references found in any task file. All use `type: module`, `type: class`, or `type: file`.

5. **Single-owner rule** - Foundation owns all infra files. Tasks correctly reference as dependencies or verify contracts.

---

## Conclusion

**Validation Status: APPROVED**

The task set demonstrates high-quality semantic targeting, correct dependency ordering, and adherence to the `plan-tasks.md` specification. All SPEC-DEVIATION issues were corrected during validation (first pass and second pass). No architectural risks or rollout conflicts identified.

*Report generated in accordance with `.kilo/commands/plan/plan-tasks.md` validation requirements.*

---

## Third Validation Pass (Final) — 2026-07-19

### 1. Task Dependencies Completeness and Ordering — **PASS**

**Evidence:**
- `order_00_docker_environment.yaml` correctly sequences tasks 001→002→006→003→(parallel: 004, 005, 007, 008, 012)→009→(010, 011, 013, 014)→015
- `order_01_plan_roadmap.yaml` correctly gates: Foundation Gate → Phase 1 → Phase 2 → Phase 3 → Phase 4
- `order_02_phase2_moderation.yaml` has correct dependencies (Tasks 37, 38 reference tasks from Phase 1)
- `order_03_phase3_contact_dashboard.yaml` correctly depends on Phase 1/2 tasks
- `order_04_phase4_analytics_harden.yaml` correctly depends on Phase 1/2/3 tasks (TASK_051 includes task_007)

All dependencies are complete, no missing prerequisite references found.

### 2. Command Names Match — **PASS**

**Docker Plan Task 9 commands vs Phase task implementations:**
| Command | Docker Plan (Task 9) | Phase Task | Status |
|---------|---------------------|------------|--------|
| `archive_sweep` | Lock 1, Phase 4 Task 2 | TASK_049 phase4_lifecycle_sweeps | ✓ Match |
| `delete_sweep` | Lock 2, Phase 4 Task 2 | TASK_049 phase4_lifecycle_sweeps | ✓ Match |
| `consent_hard_delete` | Lock 3, Phase 4 Task 2 | TASK_049 phase4_lifecycle_sweeps | ✓ Match |
| `sweep_drafts` | Lock 4, Phase 4 Task 2 | TASK_049 phase4_lifecycle_sweeps | ✓ Match |
| `cleanup_login_tokens` | Lock 5, Phase 4 Task 2 | TASK_049 phase4_lifecycle_sweeps | ✓ Match |
| `purge_failed_ads` | Lock 6, Phase 2 Task 4 | TASK_037 phase2_purge_failed | ✓ Match |
| `purge_rejected_ads` | Lock 7, Phase 2 Task 5 | TASK_038 phase2_purge_rejected | ✓ Match |
| `migrate` | Lock 100, Task 2 | TASK_003 docker_compose_base, TASK_009 | ✓ Match |

All command names are correctly aligned across plans and tasks.

### 3. Advisory Lock ID Uniqueness — **PASS**

**Lock allocation table verified:**
| Lock ID | Command | Owner | Status |
|---------|---------|-------|--------|
| 1 | archive_sweep | Phase 4 | ✓ Correct |
| 2 | delete_sweep | Phase 4 | ✓ Correct |
| 3 | consent_hard_delete | Phase 4 | ✓ Correct |
| 4 | sweep_drafts | Phase 4 | ✓ Correct |
| 5 | cleanup_login_tokens | Phase 4 | ✓ Correct |
| 6 | purge_failed_ads | Phase 2 | ✓ Correct |
| 7 | purge_rejected_ads | Phase 2 | ✓ Correct |
| 100 | migrate | Foundation (Docker) | ✓ Correct |

No lock ID collisions. All tasks correctly import from `apps.core.utils.advisory_lock`.

### 4. Rollback Semantics — **PASS**

**Finding:** No `rollback_on: [false]` or `rollback_on` fields found in any task YAML files.

Per plan-tasks.md requirements, rollback is handled through transactional advisory locks (`pg_advisory_xact_lock`) which auto-release on commit/rollback — this is correctly specified in all sweep command tasks.

### 5. Semantic Anchors (No Line Numbers) — **PASS**

All task files use semantic targeting:
- `type: class` for model/class targets (e.g., ModerationCriteria)
- `type: module` for module imports (e.g., apps.core.enums)
- `type: file` for file-level changes (e.g., pyproject.toml, nginx.conf)
- `semantic_anchors` in TASK_001 uses `type: section` for TOML insertion point

No line-number-based targeting found. All anchors are stable and symbol-based.

### 6. File Paths — **PASS**

All file paths in tasks are correctly specified following the `src/backend/...` prefix convention. Note: Paths referencing `src/backend/apps/core/utils/advisory_lock.py` are intentional planned targets (file does not yet exist — will be created by TASK_009).

---

## Final Validation Summary

| Check | Result |
|-------|--------|
| Task dependencies complete/ordered | ✓ PASS |
| Command names match across plans | ✓ PASS |
| Advisory lock IDs unique/allocated | ✓ PASS |
| No rollback_on false present | ✓ PASS |
| Semantic anchors (no line numbers) | ✓ PASS |
| File paths correct | ✓ PASS |

---

**Final Status: ALL VALIDATION CHECKS PASSED**

The task set in `.ai/tasks/todo/` is fully consistent with `.ai/plans/` and complies with all `plan-tasks.md` requirements. No issues remain. Ready for implementation.