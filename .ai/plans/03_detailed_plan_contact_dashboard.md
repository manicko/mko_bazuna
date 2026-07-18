# Phase 3 Detailed Plan: Buyer Contact + Seller Dashboard

**Wave:** Core Features  
**Depends_on:** Phase 1  
**Files_modified:** `src/backend/`, `docs/wiki/*.md`  
**Autonomous:** Yes

---

## Task 1: Anonymous Contact Bridge
**Goal:** Contact seller without revealing PII.
**Acceptance Criteria:**
- `contact_deep_link(ad_id)` generates `t.me/<bot>?start=contact_<uuid>` (prevents enumeration)
- Contact handler: `/start contact_<uuid>` → forward message anonymously
- If seller has `consent_revoked_at` (deleted) or `is_banned=True`: friendly error
**Artifacts:** `services/contact.py`, `bot/handlers/contact.py`
**Dependencies:** Phase 1 Task 9
**Risks:** Seller PII leakage, contact spam

---

## Task 2: Seller Dashboard Views
**Goal:** Ad management (edit + archive + reactivate).
**Acceptance Criteria:**
- `/dashboard/` list grouped by status (published/archived/draft)
- `/dashboard/ad/<id>/edit`:
  - Price/photo edits → immediate publish (status stays PUBLISHED)
  - Text edits → `PUBLISHED → ON_MODERATION` (hide from public immediately per Decision J)
- Reactivate button: ARCHIVED → PUBLISHED (text re-moderated)
**Artifacts:** `ads/views/dashboard.py`, templates
**Dependencies:** Phase 1 Task 11
**Risks:** Unauthorized access, edit race conditions

---

## Task 3: Account States Separation (O1/R4)
**Goal:** Distinguish ban vs delete vs publish restriction.
**Acceptance Criteria:**
- `is_banned=True` (admin): blocks login/publish, keeps PII, admin can unban
- `is_deleted=True` + `consent_revoked_at`: triggers 30-day hard delete
- `ads_auto_publish=False` (US-S9): blocks new ad placement, keeps existing ads + PII
- Clear UI messaging per state
**Artifacts:** `services/account_state.py`, dashboard UI
**Dependencies:** Phase 1 Task 2
**Risks:** Legal compliance (GDPR-equivalent), state conflation

---

## Task 4: Consent Revocation + 30-Day Hard Delete
**Goal:** Proper account erasure flow.
**Acceptance Criteria:**
- "Delete account" button sets `consent_revoked_at = now()`, `is_deleted = True`
- `consent_hard_delete` job (from Phase 1):
  - NULL telegram_id, username
  - DELETE all user's ads + images
  - SET NULL `analytics_events.user_id`, `ModeratorActionLog.user_id` (R1 audit retention)
- 7-day purge job: delete ON_MODERATION_FAILED ads (belongs in Phase 2 Task 4)
**Artifacts:** `services/deletion.py` (calls job), UI button
**Dependencies:** Phase 1 Task 4

---

## Task 5: Documentation Updates
**Goal:** Contact + dashboard spec.
**Acceptance Criteria:**
- `docs/wiki/01`: US-B4/B5, US-S5-S11 with O1/R4 state separation
- `docs/wiki/04`: Account states clarified
**Artifacts:** Wiki updates