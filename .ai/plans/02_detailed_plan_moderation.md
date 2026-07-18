# Phase 2 Detailed Plan: Moderation System

**Wave:** Core Features
**Depends_on:** Phase 1 (Tasks 2, 4, 6, 9, 10)
**Files_modified:** `src/backend/apps/moderation/`, `src/backend/apps/ads/`, `src/backend/apps/core/management/commands/`, `docs/wiki/*.md`
**Autonomous:** Yes

> **Spec source:** `docs/wiki/01_technical_specification.md` (decision A, US-A3/A10/A11), `docs/wiki/04_db_structure.md` (exact ModerationCriteria fields, ModeratorActionLog, R1 erasure, IX_ads_purge_failed/IX_ads_rejected_sweep), `docs/wiki/03_structure.md` (management commands only, NOT Celery).
> **Planner note:** Produced via 3 iterative Planner runs. Coverage audit, version exactness, rule-compliance, DB-structure consistency verified in run 3.

---

## Task 1: ModerationCriteria Singleton (exact fields)

**Goal:** Admin-editable thresholds matching `04_db_structure.md` exactly.

**Acceptance Criteria:**
- `apps/moderation/models.py` — `ModerationCriteria` fields EXACTLY (no min_price/max_price):
  - `title_min_length` (INT, default 5)
  - `title_max_length` (INT, default 100)
  - `description_min_length` (INT, default 10)
  - `description_max_length` (INT, default 2000)
  - `price_required` (BOOL, default True)
  - `min_images` (INT, default 1)
  - `max_images` (INT, default 5)
  - `banned_words` (JSONB default `[]`)
  - `max_ads_per_user` (INT, default 10)
  - `duplicate_title_threshold` (INT, default 85)
  - `updated_at` (TIMESTAMP)
  - `updated_by` (FK → users.id, nullable, SET_NULL)
- Singleton enforced (exactly one active row); created via migration `RunPython`.
- Django admin inline for runtime editing (US-A11); `updated_by` set on save.
- Cached in Django cache (5-min TTL) for bot/auto-moderation reads (key `moderation_criteria:v1`).
- Uses `ModeratorActionType` StrEnum (REJECT, BAN_ACCOUNT, SOFT_DELETE, CRITERIA_CHANGE, OTHER) defined in Phase 1 Task 1.

**Artifacts:** `apps/moderation/models.py`, `apps/moderation/admin.py`, `apps/core/utils/cache.py`, migration.
**Dependencies:** Phase 1 Task 4
**Risks:** Singleton race on creation; cache invalidation after admin edit.

---

## Task 2: ModeratorActionLog Population

**Goal:** Audit trail for auto-fail + manual reject (zone D8, zone R1).

**Acceptance Criteria:**
- Auto-fail: `ON_MODERATION_FAILED` creates `ModeratorActionLog` with `action_type=OTHER` (auto), auto-generated reason text; `moderated_by` NULL (auto action).
- Manual reject (admin): creates entry `action_type=REJECT`, `reason` chosen from Layer-2 checklist (adult_content, violence_gore, drugs_weapons, hate_speech, counterfeit_goods, illegal_goods, spam_scam, off_topic) + free TEXT; `moderated_by` set.
- `published_by`/`moderated_by` FKs on `ads` populated on manual actions (NULL for auto).
- `reason` is NEVER shown to seller (US-A11).
- On user erasure (zone R1): `user_id` SET NULL, `reason`/`created_at`/`action_type` preserved for audit trail.

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
- Admin access restricted to `is_staff`/`is_superuser` (US-A1 via Phase 1).
- `uv run ruff check` + `uv run basedpyright` pass.

**Artifacts:** `apps/ads/admin.py`, `templates/admin/moderation/review.html`, `apps/moderation/admin_actions.py`.
**Dependencies:** Phase 1 Task 11 (ad detail), Task 2
**Risks:** Photo display perf; permission scoping (admin only).

---

## Task 4: 7-Day Failed-Moderation Purge

**Goal:** Auto-clean ads that failed auto-moderation (decision A, zone C4).

**Acceptance Criteria:**
- `apps/core/management/commands/purge_failed_ads.py`: queries `ads` WHERE `status=ON_MODERATION_FAILED` AND `moderation_failed_at < now() - interval '7 days'`.
- **--dry-run flag:** when set, prints affected count without deletion (idempotent verification).
- Atomically deletes ad + related `ad_images` (CASCADE); logs count to stdout via `logger`.
- Idempotent; safe to re-run. Uses `IX_ads_purge_failed` partial index.
- Hooked into systemd/cron scheduler (Phase 4).

**Artifacts:** `apps/core/management/commands/purge_failed_ads.py`.
**Dependencies:** Phase 1 Task 6, Task 2
**Risks:** Accidental data loss; FK cascade.

---

## Task 5: 90-Day REJECTED Purge

**Goal:** Clean manually-rejected ads after retention window (zone D4).

**Acceptance Criteria:**
- `apps/core/management/commands/purge_rejected_ads.py`: queries `ads` WHERE `status=REJECTED` AND `rejected_at < now() - interval '90 days'`.
- **--dry-run flag:** when set, prints affected count without deletion (idempotent verification).
- Deletes ad + images cascade; preserves `ModeratorActionLog` (`ad_id` SET NULL). Idempotent. Uses `IX_ads_rejected_sweep` partial index.
- Hooked into systemd/cron scheduler (Phase 4).

**Artifacts:** `apps/core/management/commands/purge_rejected_ads.py`.
**Dependencies:** Task 2
**Risks:** Audit retention vs deletion balance.

---

## Task 6: Auto-Moderation Cache Invalidation Signal (wire existing Phase 1 service)

**Goal:** Cache invalidation hook when admin edits moderation criteria; verify bot submit path logs correctly. Phase 1 Task 10 owns the auto-moderation rules; Phase 2 only wires cache-invalidation signal + bot submit call.

**Acceptance Criteria:**
- Signal handler on `ModerationCriteria.save` (post_save) invalidates cache key used by Phase 1 Task 10's `auto_moderation.check()`.
- Bot submit (Phase 1 Task 9) calls `auto_moderation.check(ad)`; on fail sets `moderation_failed_at` + `ON_MODERATION_FAILED` + `ModeratorActionLog`.
- Case-insensitive banned-words check; `price_required` enforced (price present when True); photo count within `min_images..max_images`; duplicate-title via `difflib.ratio`.
- Returns structured, seller-safe error (no specific reason, US-A11).
- No celery/redis; signal uses Django's built-in dispatches (management commands + systemd, not Celery).

**Artifacts:** `apps/moderation/signals.py`, verify `apps/moderation/services/auto_moderation.py`.
**Dependencies:** Tasks 1, 2, Phase 1 Task 10
**Risks:** Cache miss; large banned-words list perf.

---

## Task 7: Documentation Updates

**Goal:** Consolidate moderation spec (English-only per rule 1).

**Acceptance Criteria:**
- `docs/wiki/01_technical_specification.md`: decision A (single auto-gate), US-A3/A4/A10/A11 covered; clarify `ModerationCriteria` has NO min_price/max_price/price-range fields.
- `docs/wiki/04_db_structure.md`: `ModerationCriteria` field list confirmed exact; `ModeratorActionLog.reason` TEXT, never shown to seller; indexes `IX_ads_purge_failed`, `IX_ads_rejected_sweep` documented.
- All docs English-only, frontmatter intact (doc-maintenance-rules).

**Artifacts:** Updated wiki files.
**Dependencies:** Tasks 1-6
**Risks:** Doc drift.

---

## Coverage Audit Summary

| User Story | Covered By Task(s) | Notes |
|------------|-------------------|-------|
| US-A3 (moderation actions: reject/ban/soft-delete) | Task 3 | Admin UI with reject/ban/soft-delete outcomes |
| US-A4 (user block/unblock/delete) | Task 3 | `is_banned` flag + `BAN_ACCOUNT` action_type; delete deferred to Phase 3 (consent revocation) |
| US-A10 (auto-moderation) | Phase 1 Task 10 + Task 6 | Phase 1 owns rules; Phase 2 wires cache-invalidation + verifies logging |
| US-A11 (failed queue + criteria editing) | Tasks 1, 3, 7 | Criteria singleton edit + failed queue UI + criteria fields documented |

## Version Exactness (vs docs/wiki/02_packages.md)

**Phase 2 uses SAME packages as Phase 1 (CONFIRMED):**
- `django>=5.2.16,<6.0`
- `psycopg[binary]>=3.2.0`
- `django-environ>=0.11.0`
- `django-mptt>=0.18.0`
- `django-filter>=26.1`
- `aiogram>=3.15.0`
- `deep-translator>=1.11.0`
- `django-tailwind>=4.4.0`
- `django-htmx>=1.19.0`
- `pillow>=10.4.0`

**Deferred (NOT added in Phase 2):**
- `django-storages`, `boto3` — YAGNI (S3/R2 swap post-MVP)
- `celery`, `redis` — deferred (management commands + cron, not Celery)
- `djangorestframework` — deferred (HTMX MPA in phase 1)

## Rule Compliance Checklist

| Rule | Status | Evidence |
|------|--------|----------|
| 10 (StrEnum for ALL constants) | OK | `ModeratorActionType` defined in Phase 1 Task 1; used in Tasks 1-3. No inline string literals. |
| 15 (Small modules/functions) | OK | All artifacts under `apps/moderation/`, `apps/core/management/commands/`, separated by concern. |
| 13 (Migrations) | OK | Tasks 1, 2, 4, 5 specify migrations for schema changes. |
| 1 (English-only code+docs) | OK | Task 7 explicitly English-only; all task artifacts in English. |
| 12 (Logging not print) | OK | Task 4, 5 specify `logger` for output; no `print()` statements. |
| 11 (Pydantic at boundaries) | N/A | Phase 2 reads cached criteria; no new input boundaries. Phase 1 Task 9 already covers bot message DTOs. |

## DB Structure Consistency (vs 04_db_structure.md)

| Decision | Status | Evidence |
|----------|--------|----------|
| `moderation_failed_at` auto-clear after 7 days | OK | Task 4 purge command with 7-day logic. |
| `rejected_at` manual-purge after 90 days | OK | Task 5 purge command with 90-day logic. |
| `ModeratorActionLog.user_id` SET NULL on erasure (zone R1) | OK | Task 2 preserves reason/admin/timestamp when user_id NULL. |
| `IX_ads_purge_failed` partial index | OK | Task 4 uses this index. |
| `IX_ads_rejected_sweep` partial index | OK | Task 5 uses this index. |
| `moderation_criteria` singleton table | OK | Task 1 enforced; exactly one active row. |

## Purge Command Design

Both purge commands (Tasks 4, 5) follow the same pattern:
- Django management command only (scheduler in Phase 4)
- Exactly one command per retention window
- Idempotent (safe to re-run)
- `--dry-run` flag for safe verification
- Uses partial indexes for performance
- Logs via `logger = logging.getLogger(__name__)` (rule 12)
- Deletes atomically with CASCADE for images
