# Phase 5 Detailed Plan: Scraping Service + Internationalization

**Wave:** Extensions  
**Depends_on:** Phase 1 (ORM), Phase 2 (ad workflow)  
**Files_modified:** `scraping_service/`, `docs/wiki/*.md`  
**Autonomous:** Yes

---

## Task 1: Telethon Scraping Service Schema
**Goal:** Dedicated field for third-party message dedup.
**Acceptance Criteria:**
- Add `telegram_message_id` (BIGINT, nullable, UNIQUE, indexed) to `ads` model (Phase 5 migration)
- `source` field indicates `TELEGRAM_SCRAPED` (extend AdSource enum)
- Migration adds column without downtime
**Artifacts:** `apps/ads/migrations/000X_add_scraping_fields.py`
**Dependencies:** Phase 1 Task 2
**Risks:** Column naming, unique constraint impact

---

## Task 2: Telethon Scraping Service Implementation
**Goal:** Monitor third-party Telegram groups.
**Acceptance Criteria:**
- `scraping_service/main.py`: Telethon MTProto login (phone code), session stored in `scraping_service/sessions/`
- Read messages from configured groups/channels
- Parse ad structure (photos, text, price)
- Create ads via shared ORM (insert source=TELEGRAM_SCRAPED)
- Dedup by `telegram_message_id` (unique constraint)
- Runs as separate systemd service
**Artifacts:** `scraping_service/`, systemd unit
**Dependencies:** Task 1, shared ORM from Phase 1
**Risks:** Telegram ToS, account ban, parsing reliability

---

## Task 3: UI Language Switcher (RU/BOS)
**Goal:** Bosnian interface language.
**Acceptance Criteria:**
- `/set-lang/bosnian` sets session locale
- Templates: `{% trans "key" %}` with Russian default fallback
- `name_i18n` used for category/city display when locale=BOS
- `name` (Russian) used everywhere else (content storage invariant)
**Artifacts:** `core/locale/`, templates updated, middleware
**Dependencies:** Phase 1 Task 3

---

## Task 4: Query Translation Integration
**Goal:** Search-time Bosnian → Russian.
**Acceptance Criteria:**
- Translate Bosnian query to Russian before FTS (deep-translator)
- Timeout ~500ms, fallback to original query
- Cache translations (5 min TTL)
**Artifacts:** `services/translation.py`, search view update
**Dependencies:** Phase 1 Task 11

---

## Task 5: Content Language Invariant Check (Decision G)
**Goal:** Ensure Russian content for FTS compatibility.
**Acceptance Criteria:**
- Verify Phase 1 already translates seller input to Russian on creation (if Bosnian)
- Confirm `search_vector` works on Russian content only
- Display translates Russian → Bosnian for BOS locale
**Artifacts:** Validation test, comment in `services/content_translate.py`
**Dependencies:** Phase 1 Task 9

---

## Task 6: Documentation Updates
**Goal:** Scraping + i18n spec.
**Acceptance Criteria:**
- `docs/wiki/01`: Decision B (scraping), Decision G (translation) finalized
- `docs/wiki/02`: telethon>=1.44.0 dependency
- `docs/wiki/03`: scraping_service entrypoint
- `docs/wiki/04`: `telegram_message_id` column added
**Artifacts:** Wiki updates

---

## Tags System Note
Tagged per spec: Tags (`tags`, `ad_tags`) are fully deferred (see `docs/wiki/04_db_structure.md` lines 145-149). No implementation in this phase.

---
## Deferred / Out-of-MVP Scope
- US-S6 (seller deletes own ad) — Soft-delete status exists; feature deferred to post-MVP
- US-B8 (responsive layout) — Tailwind CSS default; specific AC to verify in implementation
- US-A6 (inactive-user purge) — No idle detection/deletion in this plan set
- US-A9 (system-log event admin view) — AnalyticsEvent covers metrics; full log view deferred