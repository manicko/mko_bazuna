# Phase 05 Validated Audit Findings — Ad Lifecycle, Categories & Moderation

**Validator:** validator  
**Source findings:** `.ai/audit/05-ad-lifecycle/findings.md`  
**Status:** complete  
**Validation date:** 2026-07-20

> **Validation process:** Verified against actual implementation in `src/telegram_bot/handlers/ad_create.py`, `src/backend/apps/moderation/services/auto_moderation.py`, `src/backend/apps/moderation/services/moderation_log.py`, `src/backend/apps/moderation/admin_actions.py`, `src/backend/apps/ads/models.py`, `src/backend/apps/ads/views/edit.py`, `src/backend/apps/ads/views/delete.py`, and `src/backend/apps/core/management/commands/sweep_drafts.py`. Cross-referenced with `docs/01-spec/technical-specification.md`, `docs/04-user-stories/admin-stories.md`, and `docs/02-database/db-schema.md`.

---

## Findings

### AD-001: Bot publish path bypasses the moderation gate and audit log

| Field | Value |
|-------|-------|
| **ID** | AD-001 |
| **Severity** | CRITICAL |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/telegram_bot/handlers/ad_create.py` (`update_ad_and_moderate`) |
| **Classification** | mandatory |
| **Validation** | **APPROVED** |

> **Validation Note:**
> - **Action:** Approved
> - **Detail:** Evidence confirms the bot publish flow does not call `auto_moderate()` or `set_published()` from the moderation services. Instead, it re-implements publish logic inline (lines 556-561) and creates `AnalyticsEvent` inline (lines 563-566) without creating a `ModeratorActionLog` entry. The `_validate_max_ads_per_user` equivalent in the bot (line 535-537) counts only `PUBLISHED` ads, while the centralized auto-moderation (auto_moderation.py:194-198) counts `PUBLISHED + ON_MODERATION + ON_MODERATION_FAILED`. This creates divergent enforcement of limits and missing audit trail for bot-submitted ads.
> - **See also:** AD-002 (centralized transition), AD-003 (manual approve)

**Recommendation:** Route bot submission through the single `auto_moderate(ad)` / `set_published(ad)` path instead of duplicating publish logic. This guarantees one gate, identical criteria, and a complete audit trail. Effort: medium. Priority: mandatory (correctness + moderation integrity).

---

### AD-002: No centralized transition driver — status overwritten in 7+ places

| Field | Value |
|-------|-------|
| **ID** | AD-002 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `ads/views/edit.py`, `ads/views/delete.py`, `moderation/admin_actions.py`, `moderation/services/moderation_log.py`, `telegram_bot/handlers/ad_create.py` |
| **Classification** | mandatory |
| **Validation** | **REJECTED** (Stale Finding) |

> **Validation Note:**
> - **Action:** Rejected
> - **Detail:** The `Ad.transition_to()` method **exists and is fully implemented** in `ads/models.py:188-294`. The task `TASK_005_add_ad_transition_to_DONE.yaml` confirms completion. However, this method is **not used** by any of the current code paths — the grep search found 0 invocations of `.transition_to()` and 13 direct `ad.status = AdStatus.X` assignments across the codebase. The finding's claim that `transition_to` is "not implemented" is outdated, but the underlying architectural problem (scattered status assignments) remains because the method exists but is not wired.
> - **See also:** AD-001 (bot path), AD-003 (manual approve)

> **Rejection reason:** The core claim "no centralized transition driver" is factually incorrect. `Ad.transition_to()` method exists (TASK_005 completed). However, the method exists but is **not wired** to any code path — this is a different issue (adoption gap, not absence). The finding's evidence references "task_005 absent from ads/models.py" which is demonstrably false per line 188. Rejection made under "stale finding" criterion.

---

### AD-003: Manual approve does not set `original_published_at` on first publish

| Field | Value |
|-------|-------|
| **ID** | AD-003 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/moderation/admin_actions.py` (`approve_ad`) |
| **Classification** | mandatory |
| **Validation** | **APPROVED** |

> **Validation Note:**
> - **Action:** Approved
> - **Detail:** Evidence is accurate. `approve_ad` (admin_actions.py:35-38) sets `status=PUBLISHED`, `published_at=now`, and `published_by_id` but does not include `original_published_at` in the save call. Contrast with `set_published` (moderation_log.py:214-221) which correctly sets `original_published_at` when None. The model docstring (models.py:94-98) explicitly states `original_published_at` is "Set once on FIRST publish; IMMUTABLE, audit only."
> - **See also:** AD-001 (audit trail)

**Recommendation:** In `approve_ad`, set `original_published_at` from `published_at` when `original_published_at is None`, mirroring `set_published`. Effort: trivial. Priority: mandatory (data-integrity; audit field inconsistent between publish paths).

---

### AD-004: Bot DRAFT cleanup leaves physical image files orphaned

| Field | Value |
|-------|-------|
| **ID** | AD-004 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/telegram_bot/handlers/ad_create.py` (`delete_draft`, `save_photo`) |
| **Classification** | advisory |
| **Validation** | **APPROVED** |

> **Validation Note:**
> - **Action:** Approved
> - **Detail:** Evidence is accurate. `save_photo` (ad_create.py:431-437) writes photo bytes to `media/` filesystem immediately. `delete_draft` (ad_create.py:372-380) deletes the `Ad` ORM row without removing the already-written physical files. The `sweep_drafts` command (sweep_drafts.py:58) uses `queryset.delete()` which only removes DB rows, relying on CASCADE for `ad_images`. The `AdImage` CASCADE on `ad_images` table would delete the `AdImage` rows, but not the actual file content in `media/`. This is an operational hygiene issue per the spec note about deferred physical cleanup.
> - **See also:** ---

**Recommendation:** Track pending `storage_key`s in FSM state and unlink them on cancel; or store uploaded bytes transiently and only persist to `media/` at confirm. Effort: small. Priority: advisory (operational hygiene; orphaned files accumulate).

---

### AD-005: No seller-facing error returned on bot moderation failure

| Field | Value |
|-------|-------|
| **ID** | AD-005 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/telegram_bot/handlers/ad_create.py` (`process_preview`, `update_ad_and_moderate`) |
| **Classification** | advisory |
| **Validation** | **REJECTED** (Low Value for Project Scale) |

> **Validation Note:**
> - **Action:** Rejected
> - **Detail:** Per the validation process, BEST-PRACTICE findings with negative ROI at project scale should be rejected. The current generic error message aligns with the spec (technical-specification.md:44, admin-stories.md:60) which explicitly states "no specific reason disclosed." The bot already returns a generic message, not specific internal reasons. Adding "category of failure" would provide minimal user value while increasing code complexity.
> - **See also:** ---

> **Rejection reason:** Per validation rules, BEST-PRACTICE findings must be rejected if ROI is negative. The current behavior (generic error) matches spec requirements (US-A10: "no specific reason disclosed"). The suggested enhancement adds code without meaningful user value.

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 3 | AD-001, AD-003, AD-004 |
| Rejected | 2 | AD-002 (stale claim about missing method), AD-005 (negative ROI) |

### Rejected Findings

| ID | Title | Reason |
|----|-------|--------|
| AD-002 | No centralized transition driver | Core claim "transition_to absent" is false — method exists in ads/models.py:188 but is unused. Requires re-investigation for "unwired method" issue. |
| AD-005 | No seller-facing error on bot moderation failure | Behavior aligns with spec (generic error). Suggested change adds complexity with no meaningful user value. |

### Reclassified Findings

None

---

## Rollout Analysis

### Risks & Dependencies

1. **AD-001 (Bot publish bypass)** is the primary architectural risk — fixing it would centralize all publish logic through `auto_moderate()` and `set_published()`, which would then:
   - Require `approve_ad` to be updated to use `set_published` (resolving AD-003)
   - Create consistent `max_ads_per_user` counting across all paths
   - Ensure complete audit trail via `ModeratorActionLog` for all published ads

2. **AD-003 (original_published_at)** can be fixed independently as a trivial change, but if AD-001 is fixed, `approve_ad` should use `set_published` which already handles this correctly.

3. **AD-004 (orphaned files)** requires tracking storage keys in FSM state. This is a low-risk operational fix but touches the bot handler's state management.

### Sequencing

| Priority | Recommendation | Depends on |
|----------|----------------|------------|
| 1 | Fix AD-001: Route bot publish through centralized `auto_moderate()`/`set_published()` | ---
| 2 | AD-003 resolved automatically via #1 (use `set_published`) | AD-001 |
| 3 | AD-004: Add storage key tracking + cleanup | ---

---

## Warnings

### Architectural Risks

1. **Scattered status assignments:** 13 direct `ad.status = AdStatus.X` assignments exist across the codebase without going through `transition_to()`. This violates the state-machine integrity principle from the spec (technical-specification.md:66-71). Even though `transition_to()` exists (TASK_005 completed), it is unused. TASK_006 (blocked) plans to wire views/edit.py, views/delete.py, and moderation_log.py to use `transition_to()`.

2. **Inconsistent moderation counting:** The `_validate_max_ads_per_user` check in auto_moderation.py counts `PUBLISHED + ON_MODERATION + ON_MODERATION_FAILED` (line 194), but the bot path only counts `PUBLISHED` (ad_create.py:536). This allows the bot to publish ads that would be rejected by the web path.

3. **Missing audit trail:** `ModeratorActionLog` entries are missing for all bot-published ads. This affects compliance/audit requirements.

### Documentation Consistency

The spec describes "auto-check is the only gate before PUBLISHED" and "ModeratorActionLog" audit trail. AD-001 shows the implementation diverges from this spec.