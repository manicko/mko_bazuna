# Phase 3 Detailed Plan: Buyer Contact + Seller Dashboard

**Wave:** Core Features
**Depends_on:** Phase 1 (Tasks 2, 9, 11, 21/22/40), Phase 2 (moderation)
**Files_modified:** `src/backend/apps/users/`, `src/backend/apps/ads/`, `src/telegram_bot/`, `docs/wiki/*.md`
**Autonomous:** Yes

> **Spec source:** `docs/wiki/01_technical_specification.md` (decision C, F/K, J; US-B4/B5, US-S5/S6/S7/S8/S9, US-A4),
> `docs/wiki/04_db_structure.md` (users flags, status transitions, erasure indexes).

---

## Task 1: Anonymous Contact Bridge (decision C — uses `ad_id`)

**Goal:** Buyer reaches seller via deep-link without PII exposure.

**Acceptance Criteria:**
- Contact deep-link = `t.me/<bot_username>?start=contact_<ad_id>` (uses **`ad_id`**, NOT uuid — per decision C; corrected from prior draft).
- Button renders on site ONLY when: `ad.status == PUBLISHED` AND `seller.telegram_id IS NOT NULL` AND `NOT seller.is_deleted` AND `NOT seller.is_banned` AND `seller.consent_revoked_at IS NULL`.
- Bot handler `/start contact_<ad_id>`: finds ad → seller via `telegram_id`; forwards buyer→seller anonymously; NEVER reveals seller PII (`telegram_id`/`username`).
- Bot messages: ad missing/not PUBLISHED → "объявление больше недоступно"; seller unavailable (deleted/banned/revoked) → "продавец больше недоступен для связи".
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
  - Price/photo edits → save immediately, status stays `PUBLISHED`, `updated_at` set, public within ≤5s (decision J).
  - Title/description edits → `PUBLISHED → ON_MODERATION`, ad **immediately hidden** from public site (zone C2).
  - Mixed edits follow the text rule (re-moderation).
- Reactivate (ARCHIVED → PUBLISHED): re-checks text, immediately hidden until pass (decision J).
- `published_at` updated on every transition into PUBLISHED (resets 2/4-month timers, zone C3).
- Unauthorized edit (wrong seller) → 403.

**Artifacts:** `apps/ads/views/dashboard.py`, `apps/ads/views/edit.py`, templates.
**Dependencies:** Phase 1 Task 11
**Risks:** Unauthorized access; edit race conditions; timer reset correctness.

---

## Task 3: Account States Separation (O1/R4)

**Goal:** Distinguish ban vs delete vs publish-restriction (US-S9, US-A4).

**Acceptance Criteria:**
- `is_banned=True` (admin, US-A4): blocks login/publish; PII kept; admin can unban. Applies to both bot (reject new ads) and web.
- `is_deleted=True` + `consent_revoked_at` set: triggers 30-day hard delete (Task 4).
- `ads_auto_publish=False` (US-S9): bot rejects NEW ads; existing ads NOT deleted, hidden from public while flag active; reversible; independent of ban/delete.
- Clear UI messaging per state; bot permission check uses all three flags.

**Artifacts:** `apps/users/services/account_state.py`, bot permission middleware, dashboard UI.
**Dependencies:** Phase 1 Task 2
**Risks:** State conflation (ban vs delete vs restriction); legal compliance (GDPR-equivalent).

---

## Task 4: Consent Revocation + 30-Day Hard Delete (decision F/K, R1)

**Goal:** Proper erasure flow (US-S8).

**Acceptance Criteria:**
- **Decline (browse-only, decision K):** only blocks seller actions; `consent_revoked_at` NOT set; NO deletion; contact button still works.
- **Withdraw/Delete account (decision F):** sets `consent_revoked_at=now()`, `is_deleted=True`, `deleted_at=now()` immediately; all user ads + images soft-deleted; `telegram_id`/`username` NULLed immediately (break chat linkage).
- `consent_hard_delete` job (Phase 4): 30 days after `consent_revoked_at` → NULL `telegram_id`/`username` (already nulled), DELETE ads+images, SET NULL `analytics_events.user_id` + `ModeratorActionLog.user_id` (reason/admin/timestamp preserved, zone R1). Idempotent via `IX_users_erasure_sweep`.

**Artifacts:** `apps/users/services/deletion.py`, dashboard button, Phase 4 job.
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
- `docs/wiki/01`: US-B4/B5, US-S5..S9 with O1/R4 state separation; decision C contact uses `ad_id`; decision F/K two consent states.
- `docs/wiki/04`: account states + erasure clarified.

**Artifacts:** Updated wiki files (English-only).
**Dependencies:** Tasks 1-6
**Risks:** Doc drift.
