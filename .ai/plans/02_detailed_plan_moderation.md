# Phase 2 Detailed Plan: Moderation System

**Wave:** Core Features  
**Depends_on:** Phase 1  
**Files_modified:** `src/backend/`, `docs/wiki/*.md`  
**Autonomous:** Yes

---

## Task 1: Moderation Criteria Refinement
**Goal:** Admin-editable moderation thresholds.
**Acceptance Criteria:**
- `ModerationCriteria` model: `title_min_length`, `description_min_length`, `min_price`, `max_price`, `max_photos`, `max_ad_size_mb`
- Admin form in Django admin
- Cached in Django cache (5 min timeout) for bot/moderation reads
**Artifacts:** Model refinement, admin class, cache utility
**Dependencies:** Phase 1 Task 4

---

## Task 2: ModeratorActionLog Population
**Goal:** Track auto + manual moderation events.
**Acceptance Criteria:**
- Auto-moderation failures create `ModeratorActionLog` entry with action_type (ModeratorActionType enum), reason auto-generated for ON_MODERATION_FAILED
- Manual admin rejections create entry via admin action (action_type from enum, reason TEXT from dropdown)
- `published_by`/`moderated_by` FK populated on ad edits (NULL for auto-actions)
**Artifacts:** `services/moderation_log.py`
**Dependencies:** Phase 1 Task 4

---

## Task 3: Admin Moderation UI
**Goal:** Manual review interface (US-A11).
**Acceptance Criteria:**
- Admin list view: filter by status (ON_MODERATION, ON_MODERATION_FAILED)
- Admin detail view: "Reject" button with reason text (from Layer-2 checklist: adult_content, violence_gore, etc.)
- Photo review grid (US-A1)
**Artifacts:** `apps/ads/admin.py`
**Dependencies:** Phase 1 Task 11

---

## Task 4: Failed Moderation Purge Job
**Goal:** 7-day cleanup of auto-failed ads (Decision A).
**Acceptance Criteria:**
- `purge_failed_ads` command queries `ads` where `moderation_failed_at < now() - interval '7 days'`
- Deletes ad + images atomically
- Logs count of purged items
**Artifacts:** `apps/core/management/commands/purge_failed_ads.py`
**Dependencies:** Phase 1 Task 6

---

## Task 5: Documentation Updates
**Goal:** Moderation spec consolidation.
**Acceptance Criteria:**
- `docs/wiki/01`: Decision A (auto-publish), US-A3..A11 covered
- `docs/wiki/04`: Rejection reasons documented (TEXT in ModeratorActionLog.reason)
**Artifacts:** Wiki updates