# Phase 3 Detailed Plan: Buyer Contact + Seller Dashboard

**Wave:** Core Features
**Depends_on:** Phase 1 (Tasks 2, 9, 11), Phase 2 (moderation)
**Files_modified:** `src/backend/apps/users/`, `src/backend/apps/ads/`, `src/telegram_bot/`, `docs/wiki/*.md`
**Autonomous:** Yes

> **Spec source:** `docs/wiki/technical-specification.md` (decision C, F/K, J, O1/R4; US-B4/B5, US-S5/S6/S7/S8/S9, US-A4), `docs/wiki/db-structure.md` (users flags, status transitions, IX_users_erasure_sweep, R1 hard delete).
> **Planner note:** Produced via 3 iterative Planner runs. Coverage audit, zone R2/R3/C2 correctness, sweeps-ownership separation verified in run 3.

---

## Coverage Audit (Verified)

| US | Description | Coverage |
|----|-------------|----------|
| US-B4 | Ad card view | Task 1 — contact button + ad display |
| US-B5 | Contact via Telegram deep-link | Task 1 — deep-link generation and handler |
| US-S5 | Edit w/ immediate hide on text | Task 2 — text edits trigger `ON_MODERATION` + immediate hide; price/photo immediate |
| US-S6 | Self-delete ad | Task 5 — seller ad deletion |
| US-S7 | Auto-archive + reactivate | Task 2 — reactivation; auto-archive referenced to Phase 4 |
| US-S8 | Account deletion + 30-day hard delete | Task 4 — soft-delete + reference to Phase 4 sweep |
| US-S9 | Publish restriction toggle | Task 3 — `ads_auto_publish` flag |
| US-A4 | Ban/unban | Task 3 — `is_banned` flag + admin actions |

---

## Task 1: Anonymous Contact Bridge (decision C)

**Goal:** Buyer reaches seller via deep-link without PII exposure.

**Render Conditions (Zone R2 — verbatim from spec):**
The "Contact" button renders on the site **ONLY** when:
- `ad.status == PUBLISHED`
- `seller.telegram_id IS NOT NULL`
- `NOT seller.is_deleted`
- `NOT seller.is_banned`
- `seller.consent_revoked_at IS NULL` (i.e., consent NOT revoked)

**Acceptance Criteria:**
- Contact deep-link = `t.me/<bot_username>?start=contact_<ad_id>` (uses **`ad_id`**, NOT uuid — per decision C).
- Bot handler `/start contact_<ad_id>`: finds ad → seller via `telegram_id`; forwards buyer→seller anonymously; NEVER reveals seller PII (`telegram_id`/`username`).
- Bot messages:
  - ad missing/not PUBLISHED → "объявление больше недоступно";
  - seller unavailable (deleted/banned/revoked consent) → "продавец больше недоступен для связи".
- `AnalyticsEvent(CONTACT_INITIATED)` recorded (no login required).

**Artifacts:** `apps/core/services/contact.py`, `telegram_bot/handlers/contact.py`, dashboard template button logic.
**Dependencies:** Phase 1 Task 9 (login flow), Task 11
**Risks:** Seller PII leakage; contact spam; wrong identifier (ad_id, not uuid).

---

## Task 2: Seller Dashboard Views

**Goal:** Ad management — list, edit, archive, reactivate (US-S5/S7).

**Acceptance Criteria:**
- `/dashboard/` lists seller's ads grouped by status (PUBLISHED, ON_MODERATION, ARCHIVED, REJECTED, ON_MODERATION_FAILED).
- Edit flow:
  - **Text edits (title/description):** `PUBLISHED → ON_MODERATION`, ad **immediately hidden** from public site (zone C2); `published_at` NOT reset.
  - **Price/photo edits:** save immediately, status stays `PUBLISHED`, `updated_at` set, public within ≤5s; `published_at` NOT reset.
  - **Mixed edits follow text rule** (re-moderation).
- Reactivate (ARCHIVED → PUBLISHED): text re-checked via auto-moderation, immediately hidden until pass (decision J).
- `published_at` updated ONLY on: initial publish, reactivate, or price/photo-only edits (zone C3 — timer reset).
- Unauthorized edit (wrong seller) → 403.

**Artifacts:** `apps/ads/views/dashboard.py`, `apps/ads/views/edit.py`, templates.
**Dependencies:** Phase 1 Task 11
**Risks:** Unauthorized access; edit race conditions; timer reset correctness.

---

## Task 3: Account States Separation (O1/R4)

**Goal:** Distinguish ban vs delete vs publish-restriction (US-S9, US-A4).

**Acceptance Criteria:**
- `is_banned=True` (admin, US-A4): blocks login/publish; PII (`telegram_id`/`username`) retained; admin can unban via `/admin/users/`. Bot handler rejects new ads with "account suspended" message.
- `is_deleted=True` + `consent_revoked_at` set (withdrawal, decision F): triggers immediate soft-delete cascade + 30-day hard delete (Phase 4 `consent_hard_delete`). `telegram_id`/`username` nulled immediately (breaks chat linkage).
- `ads_auto_publish=False` (US-S9, reversible): bot rejects NEW ads with "publishing disabled" message; **existing ads hidden from public while flag active**; NOT linked to ban or deletion.
- Dashboard shows clear state badges per account status.
- Bot permission check middleware uses all three flags on every incoming message.

**Artifacts:** `apps/users/services/account_state.py`, bot permission middleware, dashboard UI state display.
**Dependencies:** Phase 1 Task 2
**Risks:** State conflation (ban vs delete vs restriction); legal compliance (GDPR-equivalent).

---

## Task 4: Consent Revocation + Soft Delete (decision F/K, R1)

**Goal:** Proper erasure flow (US-S8) — Phase 3 implements consent state + immediate soft-delete; hard-delete is Phase 4.

**Two Consent States (Zone R3 — verbatim from spec):**
- **Decline (browse-only, decision K):** "Decline" button blocks only seller actions; `consent_revoked_at` NOT set; `is_deleted` NOT set; NO deletion; contact button continues to work.
- **Withdraw/Delete (decision F):** triggers immediate actions:
  - `consent_revoked_at = now()`
  - `is_deleted = True`, `deleted_at = now()`
  - `telegram_id` / `username` NULLed IMMEDIATELY (breaks chat linkage, per decision F / zone R1)
  - all user ads + images soft-deleted (status=DELETED, hidden immediately)

**Phase 4 Handoff (Zone R1):**
- `consent_hard_delete` job (Phase 4): 30 days after `consent_revoked_at` → DELETE user ads+images, SET NULL `analytics_events.user_id` + `ModeratorActionLog.user_id` (reason/admin/timestamp preserved). Idempotent via `IX_users_erasure_sweep`.

**Acceptance Criteria:**
- Decline: only blocks seller actions, no `consent_revoked_at`, no deletion.
- Withdraw: sets `consent_revoked_at` + `is_deleted`, immediately nulls PII, soft-deletes ads.
- **Phase 3 does NOT implement the 30-day sweep** — deferred to Phase 4.

**Artifacts:** `apps/users/services/deletion.py`, dashboard button, UI for consent banner.
**Dependencies:** Phase 1 Task 4
**Risks:** Race with sweep; audit retention after PII gone.

---

## Task 5: Seller Self-Delete Ad (US-S6)

**Goal:** Seller removes own ad.

**Acceptance Criteria:**
- Seller can delete ONLY own ads → status `DELETED`, hidden from public.
- Physical cleanup per lifecycle rules (Phase 4 sweeps).
- `uv run ruff check` passes.

**Artifacts:** `apps/ads/views/delete.py`, dashboard action.
**Dependencies:** Task 2
**Risks:** Wrong-owner deletion (guard by `user_id`).

---

## Task 6: Consent Banner (decision F/K)

**Goal:** Site-wide privacy banner implementing the two consent states.

**Acceptance Criteria:**
- Banner shown to visitors who have not yet acted; "Accept" sets `consent_given_at` (covers all processing incl. bot, decision F — no separate bot prompt).
- "Decline" (browse-only, decision K): blocks only seller actions; `consent_revoked_at` NOT set; NO deletion; contact button still works.
- After acceptance, banner stays hidden (persisted); not re-shown on return.
- Buyer may browse `PUBLISHED` ads before any action (decision K: browse-only allowed).
- Plausible snippet needs NO banner (cookieless legitimate interest, decision L).

**Artifacts:** `templates/components/consent_banner.html`, consent view/handler, dashboard state display.
**Dependencies:** Phase 1 Task 7 (settings), Task 2
**Risks:** Banner vs browsing gating confusion; re-show logic.

---

## Task 7: Documentation Updates

**Goal:** Contact + dashboard spec sync.

**Acceptance Criteria:**
- `docs/wiki/technical-specification.md`: US-B4/B5, US-S5..S9 with O1/R4 state separation; decision C contact uses `ad_id`; decision F/K two consent states.
- `docs/wiki/db-structure.md`: account states + erasure clarified (soft-delete in Phase 3, hard-delete in Phase 4).

**Artifacts:** Updated wiki files (English-only per rule 1).
**Dependencies:** Tasks 1-6
**Risks:** Doc drift.

---

## Version Exactness (vs docs/wiki/packages.md)

| Package | Phase 3 Status | Notes |
|---------|---------------|-------|
| django | `>=5.2.16,<6.0` | Per docs/wiki/packages.md |
| psycopg[binary] | `>=3.2.0` | Per docs/wiki/packages.md |
| aiogram | `>=3.15.0` | Bot handlers; no PG FSM storage |
| deep-translator | `>=1.11.0` | Query translation; timeout+fallback required |
| django-mptt | `>=0.18.0` | Categories tree |
| celery | DEFERRED | Phase 4 sweep; Phase 3 uses mgmt commands + cron |
| redis | DEFERRED | Not used until Phase 4 |
| django-storages / boto3 | DEFERRED | Phase 1 uses built-in FileSystemStorage |

## Rule Compliance Checklist

| Rule | Status | Evidence |
|------|--------|----------|
| 10 (StrEnum for ALL constants) | OK | `AdStatus`, `AnalyticsEventType` reused; no inline literals |
| 13 (Migrations) | OK | User/ad changes via migrations |
| 15 (Small modules/functions) | OK | Per-concern split: `apps/users/services/`, `apps/ads/views/` |
| 1 (English-only) | OK | All code/docs English |
| 11 (Pydantic v2 at boundaries) | OK | Bot input DTOs (Phase 1); form DTOs for dashboard edits |
| 12 (Logging not print) | OK | `logger = logging.getLogger(__name__)` everywhere |

## Sweeps NOT in Phase 3 (Zone R1 handoff to Phase 4)

Phase 3 references but does NOT implement:
- `archive_sweep` (Phase 4)
- `delete_sweep` (Phase 4)
- `consent_hard_delete` (Phase 4)
- `purge_failed_ads` (Phase 2)
- `purge_rejected_ads` (Phase 2)
- `sweep_drafts` (Phase 4)
- `cleanup_login_tokens` (Phase 4)

Phase 3 implements only the trigger conditions (`consent_revoked_at`, `is_deleted`, `ads_auto_publish`) that Phase 4 sweeps consume.

## Cross-Plan Consistency Check

| Item | Phase 3 | Phase 4 | Consistent? |
|------|---------|---------|-------------|
| Contact deep-link | uses `ad_id` | N/A | OK |
| `consent_hard_delete` | referenced only | implemented | OK |
| AnalyticsEvent | referenced (Task 1) | implemented (Phase 4 T1) | OK |
| Lifecycle timers | reactivation logic | archive/delete sweeps | OK |
