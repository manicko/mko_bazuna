# Phase 05 Audit Findings — Ad Lifecycle, Categories & Moderation

**Executor:** auditor
**Template:** .kilo/commands/audit/phases/05-audit-ad-lifecycle.md
**Status:** complete
**Validated:** no

> `problems-only` mode: only failing checks are reported. Passing rows (R1 side-effect
> fields on `set_published`, R3/C1 public-listing filters on `status=PUBLISHED`, R5
> category-rename trigger propagation, R6 sweep idempotency + retention windows, F3
> timezone-aware datetimes, F4 advisory locks, F5 photo CASCADE) are omitted.
> Runtime evidence: `uv run ruff check` → pass; `uv run basedpyright` → 0 errors;
> `uv run pytest test_sweep_commands.py + test_auto_moderation.py + test_search_triggers.py`
> → 57 passed.

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

**Description:** The Telegram bot publish flow does NOT call the centralized
auto-moderation gate (`auto_moderate` / `set_published`). Instead it re-implements
publish inline: it validates duplicate-title with a different active-ad definition and
publishes directly via `ad.status = AdStatus.PUBLISHED` (lines 556-561), then creates an
`AnalyticsEvent` inline (lines 563-566).

**Evidence:**
- `ad_create.py:556-561` sets `status=PUBLISHED`, `published_at`, `original_published_at`
  directly — never invoking `auto_moderate()` (auto_moderation.py:91) or `set_published()`
  (moderation_log.py:207).
- `ad_create.py:534-539` counts only `status=PUBLISHED` for `max_ads_per_user`, whereas
  `auto_moderate._validate_max_ads_per_user` (auto_moderation.py:196) counts
  `PUBLISHED + ON_MODERATION + ON_MODERATION_FAILED`. The two gates enforce different
  limits, so the bot path can publish ads the web path would reject.
- No `ModeratorActionLog` row is created on bot publish (set_published creates one at
  moderation_log.py:227). The auto-publish audit trail is therefore missing for every
  bot-submitted ad.

**Recommendation:** Route bot submission through the single
`auto_moderate(ad)` / `set_published(ad)` path instead of duplicating publish logic.
This guarantees one gate, identical criteria, and a complete audit trail. Effort: medium.
Priority: mandatory (correctness + moderation integrity).

---

### AD-002: No centralized transition driver — status overwritten in 7+ places

| Field | Value |
|-------|-------|
| **ID** | AD-002 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `ads/views/edit.py`, `ads/views/delete.py`, `moderation/admin_actions.py`, `moderation/services/moderation_log.py`, `telegram_bot/handlers/ad_create.py` |
| **Classification** | mandatory |

**Description:** There is no single guarded `transition_to()` method. Direct
`ad.status = AdStatus.X` assignments appear across views, admin actions, moderation
services, and the bot. TASK_005/006 (add + wire `Ad.transition_to()`) are planned but
**not implemented** (`ad_create.py:367`, `edit.py:105/134/188/222`, `delete.py:50`,
`admin_actions.py:36/57/105`, `moderation_log.py:178/194/216`). Forbidden transitions are
not enforced at the driver; any new code path can set an illegal status (e.g.
`DRAFT → PUBLISHED`).

**Evidence:**
- grep for `ad.status = AdStatus` returns 16 direct assignments; none go through a guard.
- `.ai/tasks/todo/TASK_005_add_ad_transition_to.yaml` and `TASK_006_wire_views_to_transition_to.yaml`
  describe the intended driver but it is absent from `ads/models.py` (no `transition_to`
  method exists).
- `.ai/plans/architecture_testing_plan.md:136/514` already flags this as HIGH and recommends
  a single guarded `transition_to()`.

**Recommendation:** Implement a single guarded `Ad.transition_to(target)` that validates the
allowed matrix (per phase state table) and centralizes side-effects, then route every
single-ad status change through it; keep bulk sweep `.update()` calls outside the guard
(as the task research already decided). Effort: medium. Priority: mandatory (state-machine
integrity, A2).

---

### AD-003: Manual approve does not set `original_published_at` on first publish

| Field | Value |
|-------|-------|
| **ID** | AD-003 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/moderation/admin_actions.py` (`approve_ad`) |
| **Classification** | mandatory |

**Description:** `approve_ad` sets `published_at` but omits `original_published_at`
(lines 36-39). The model docstring states `original_published_at` is "Set once on FIRST
publish; IMMUTABLE, audit only" (models.py:94-98), and the auto-path (`set_published`,
moderation_log.py:218) sets it. Manual approve therefore leaves `original_published_at`
NULL for manually-published ads, breaking the "first publish" audit invariant (A4).

**Evidence:**
- `admin_actions.py:36-39`: `ad.status = PUBLISHED; ad.published_at = now; ad.published_by_id = ...; save(update_fields=[status, published_at, published_by])` — `original_published_at` is never written.
- Contrast `moderation_log.py:216-222` (`set_published`) which writes `original_published_at` when None.

**Recommendation:** In `approve_ad`, set `original_published_at` from `published_at` when
`original_published_at is None`, mirroring `set_published`. Effort: trivial. Priority:
mandatory (data-integrity; audit field inconsistent between publish paths).

---

### AD-004: Bot DRAFT cleanup leaves physical image files orphaned

| Field | Value |
|-------|-------|-------|
| **ID** | AD-004 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/telegram_bot/handlers/ad_create.py` (`delete_draft`, `save_photo`) |
| **Classification** | advisory |

**Description:** During the FSM, photos are written to the filesystem immediately
(`save_photo`, line 431-437) but the `AdImage` rows and `ad_id` linkage are created only at
confirm time (`update_ad_and_moderate`, lines 548-554). If the dialog is cancelled/aborted
(`cmd_cancel` → `delete_draft`, lines 372-380) or crashes before confirm, the ad row is
deleted but the already-written media files on disk are never removed. No cleanup of
`media/` orphan files exists in the DRAFT sweep either (sweep_drafts.py only deletes DB
rows with `status=DRAFT`).

**Evidence:**
- `ad_create.py:281-282` writes `storage_key` to `media/` before any `AdImage` row exists.
- `ad_create.py:378` `Ad.objects.filter(id=ad_id, status=DRAFT).delete()` removes the row;
  no filesystem unlink.
- `sweep_drafts.py:59` `queryset.delete()` deletes DB rows only.

**Recommendation:** Track pending `storage_key`s in FSM state and unlink them on cancel; or
store uploaded bytes transiently and only persist to `media/` at confirm. Effort: small.
Priority: advisory (operational hygiene; orphaned files accumulate, MEDIUM for B4 per phase
taxonomy).

---

### AD-005: No seller-facing error returned on bot moderation failure

| Field | Value |
|-------|-------|
| **ID** | AD-005 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/telegram_bot/handlers/ad_create.py` (`process_preview`, `update_ad_and_moderate`) |
| **Classification** | advisory |

**Description:** The bot path returns generic `errors` (e.g. "Title too short",
"Must have 1-5 photos") from `update_ad_and_moderate` (lines 517-545) and the seller sees
"Ad failed moderation. Please check your content and try again." (lines 348-350). The
reason is generic (good, C4), but the bot ignores the specific `errors` list it already
computed, so the seller gets no actionable hint — unlike the web `check()` which also
returns generic text. Minor UX inconsistency, not a leak.

**Evidence:** `ad_create.py:343-352` ignores the `errors` list returned by
`update_ad_and_moderate` (line 332).

**Recommendation:** Optionally surface the generic category of failure (length/photo
count) without leaking internal reasons. Effort: trivial. Priority: advisory.

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1 |
| HIGH | 1 |
| MEDIUM | 2 |
| LOW | 1 |

## Mandatory Fixes

- **AD-001** (CRITICAL): Bot publish bypasses moderation gate + audit log.
- **AD-002** (HIGH): No centralized `transition_to()` driver; direct status overwrites.
- **AD-003** (MEDIUM): Manual approve omits `original_published_at` first-publish audit field.

## Advisory Recommendations

- **AD-004** (MEDIUM): Orphaned media files on bot DRAFT cancel/crash.
- **AD-005** (LOW): Bot discards actionable (generic) failure hints on moderation failure.

## Doc Updates Needed

- **AD-002 / AD-003**: Docs (`docs/99-agent/architecture.md`, `docs/01-spec`) describe a
  single moderation gate and lifecycle timestamps set on every publish path, but code has
  divergent publish paths (bot inline + `approve_ad`) that do not match. Update docs or fix
  code — fix code (route through `auto_moderate`/`set_published` and `transition_to`).
