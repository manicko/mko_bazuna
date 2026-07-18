# Phase 2 Detailed Plan: Moderation System

**Wave:** Core Features
**Depends_on:** Phase 1 (Tasks 2, 4, 6, 9, 10)
**Files_modified:** `src/backend/apps/moderation/`, `src/backend/apps/ads/`, `src/backend/apps/core/management/commands/`, `docs/wiki/*.md`
**Autonomous:** Yes

> **Spec source:** `docs/wiki/01_technical_specification.md` (decision A, US-A3/A10/A11),
> `docs/wiki/04_db_structure.md` (ModerationCriteria singleton — **exact field list**, ModeratorActionLog, indexes).

---

## Task 1: ModerationCriteria Singleton (exact fields)

**Goal:** Admin-editable thresholds matching `04_db_structure.md` exactly.

**Acceptance Criteria:**
- `apps/moderation/models.py` — `ModerationCriteria` fields EXACTLY:
  `title_min_length` (INT, default 5), `title_max_length` (INT, default 100),
  `description_min_length` (INT, default 10), `description_max_length` (INT, default 2000),
  `price_required` (BOOL, default True), `min_images` (INT, default 1), `max_images` (INT, default 5),
  `banned_words` (JSONB `[]`), `max_ads_per_user` (INT, default 10),
  `duplicate_title_threshold` (INT, default 85), `updated_at`, `updated_by` (FK nullable SET_NULL).
- **No `min_price`/`max_price`/`max_photos`/`max_ad_size_mb`** (these do NOT exist in the DB spec — corrected from prior draft).
- Singleton enforced (exactly one active row); created via migration.
- Django admin inline for runtime editing (US-A11); `updated_by` set on save.
- Cached in Django cache (5-min TTL) for bot/auto-moderation reads.

**Artifacts:** `apps/moderation/models.py`, `apps/moderation/admin.py`, `apps/core/utils/cache.py`, migration.
**Dependencies:** Phase 1 Task 4
**Risks:** Singleton race on creation; cache invalidation after admin edit.

---

## Task 2: ModeratorActionLog Population

**Goal:** Audit trail for auto-fail + manual reject (zone D8).

**Acceptance Criteria:**
- Auto-fail: `ON_MODERATION_FAILED` creates `ModeratorActionLog` with `action_type=OTHER` (auto), auto-generated reason text; `moderated_by` NULL (auto action).
- Manual reject (admin): creates entry `action_type=REJECT`, `reason` chosen from `CategoryRejectReason` Layer-2 checklist (adult_content, violence_gore, drugs_weapons, hate_speech, counterfeit_goods, illegal_goods, spam_scam, off_topic) + free TEXT; `moderated_by` set.
- `published_by`/`moderated_by` FKs on `ads` populated on manual actions (NULL for auto).
- `reason` is NEVER shown to seller (US-A11).
- On user erasure: `user_id` SET NULL, `reason`/`created_at`/`action_type` preserved (zone R1).

**Artifacts:** `apps/moderation/services/moderation_log.py`, admin actions.
**Dependencies:** Phase 1 Task 4
**Risks:** Reason length; NULL `user_id` handling on erasure.

---

## Task 3: Admin Moderation UI (US-A11)

**Goal:** Manual review interface for moderator=admin role (decision A).

**Acceptance Criteria:**
- Admin list filter: status `ON_MODERATION`, `ON_MODERATION_FAILED`, `REJECTED`.
- Detail view: photo grid (lazy load), ad metadata, "Reject" action with Layer-2 checklist dropdown + reason TEXT.
- Outcomes: REJECT → status `REJECTED`, `rejected_at` set, `ModeratorActionLog` written; BAN_ACCOUNT → `user.is_banned=True` + log; SOFT_DELETE supported.
- Bulk actions: approve/reject selected.
- `uv run ruff check` + `basedpyright` pass.

**Artifacts:** `apps/ads/admin.py`, `templates/admin/moderation/review.html`, `apps/moderation/admin_actions.py`.
**Dependencies:** Phase 1 Task 11 (ad detail), Task 2
**Risks:** Photo display perf; permission scoping (admin only).

---

## Task 4: 7-Day Failed-Moderation Purge

**Goal:** Auto-clean ads that failed auto-moderation (decision A).

**Acceptance Criteria:**
- `apps/core/management/commands/purge_failed_ads.py`: queries `ads` WHERE `status=ON_MODERATION_FAILED` AND `moderation_failed_at < now() - interval '7 days'`.
- Atomically deletes ad + related `ad_images` (CASCADE); logs count to stdout.
- Idempotent; safe to re-run. Uses `IX_ads_purge_failed`.
- Hooked into scheduler (Phase 4).

**Artifacts:** `apps/core/management/commands/purge_failed_ads.py`.
**Dependencies:** Phase 1 Task 6, Task 2
**Risks:** Accidental data loss; FK cascade.

---

## Task 5: 90-Day REJECTED Purge

**Goal:** Clean manually-rejected ads after retention window (zone D4).

**Acceptance Criteria:**
- `apps/core/management/commands/purge_rejected_ads.py`: queries `ads` WHERE `status=REJECTED` AND `rejected_at < now() - interval '90 days'`.
- Deletes ad + images; preserves `ModeratorActionLog` (`ad_id` SET NULL). Idempotent. Uses `IX_ads_rejected_sweep`.

**Artifacts:** `apps/core/management/commands/purge_rejected_ads.py`.
**Dependencies:** Task 2
**Risks:** Audit retention vs deletion balance.

---

## Task 6: Auto-Moderation Service Wiring (refine Phase 1 Task 10)

**Goal:** Ensure bot submit path calls auto-moderation and logs correctly.

**Acceptance Criteria:**
- Bot submit (Phase 1 Task 9/10) calls `auto_moderation.check(ad)`; on fail sets `moderation_failed_at` + `ON_MODERATION_FAILED` + `ModeratorActionLog`.
- Case-insensitive banned-words check; `price_required` enforced (price present when True); photo count within `min_images`..`max_images`; duplicate-title via `difflib.ratio`.
- Returns structured, seller-safe error (no specific reason, US-A11).

**Artifacts:** `apps/moderation/services/auto_moderation.py` (extend Phase 1).
**Dependencies:** Tasks 1, 2
**Risks:** Cache miss; large banned-words list perf.

---

## Task 7: Documentation Updates

**Goal:** Consolidate moderation spec.

**Acceptance Criteria:**
- `docs/wiki/01`: decision A (single auto-gate), US-A3..A11 covered; clarify `ModerationCriteria` has NO price-range fields.
- `docs/wiki/04`: `ModerationCriteria` field list confirmed exact; `ModeratorActionLog.reason` TEXT, never shown to seller; indexes `IX_ads_purge_failed`, `IX_ads_rejected_sweep` documented.

**Artifacts:** Updated wiki files (English-only).
**Dependencies:** Tasks 1-6
**Risks:** Doc drift.
