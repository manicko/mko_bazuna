# Phase 5 Detailed Plan: Scraping Service + Internationalization (Deferred)

**Wave:** Extensions
**Depends_on:** Phase 1 (ORM, models), Phase 2 (ad workflow)
**Files_modified:** `scraping_service/`, `src/backend/apps/`, `docs/wiki/*.md`
**Autonomous:** Yes

> **Spec source:** `docs/wiki/01_technical_specification.md` (decision B — separate future phase with OWN API, NOT in bot; decision G — content Russian; decision D2 — name_i18n; US-B9 RU/BS UI),
> `docs/wiki/02_packages.md` (telethon deferred), `docs/wiki/03_structure.md` (scraping_service/ separate process), `docs/wiki/04_db_structure.md` (telegram_message_id, AdSource TELEGRAM phase 1).

---

## Task 1: Scraping Schema Migration

**Goal:** Dedicated column for third-party message dedup.

**Acceptance Criteria:**
- Add `telegram_message_id` (BIGINT, nullable, UNIQUE, indexed) to `ads` (Phase 5 migration).
- Phase 1 `AdSource` remains `TELEGRAM` only (decision B: scraping is a SEPARATE future phase with its own API, not merged into the bot's source enum). The scraping service writes via the shared Django ORM but is logically a distinct ingestion path; it does NOT extend the phase-1 `AdSource` enum.
- Migration is online-safe (add nullable column + index concurrently).

**Artifacts:** `apps/ads/migrations/000X_add_scraping_fields.py`.
**Dependencies:** Phase 1 Task 2
**Risks:** Unique-constraint impact on existing rows (NULLs allowed); column naming.

---

## Task 2: Telethon Scraping Service (separate process, decision B)

**Goal:** Monitor third-party Telegram groups via a standalone userbot.

**Acceptance Criteria:**
- `scraping_service/main.py`: Telethon MTProto phone-login (API_ID/API_HASH added to `.env` for this phase — NOT present in phase 1, zone R7), session in `scraping_service/sessions/`.
- Reads messages from configured groups/channels; parses ad structure (photos, text, price).
- Creates ads via shared ORM (`django.setup()`) with `telegram_message_id` for dedup (unique constraint); status starts `ON_MODERATION` (same auto-gate as bot).
- Runs as a separate systemd service, independent of web/bot.
- NOT inside the aiogram bot (decision B) — Telethon absence of FSM is irrelevant for scraping.

**Artifacts:** `scraping_service/` (main.py, parser.py, config.py), systemd unit.
**Dependencies:** Task 1, Phase 1 ORM
**Risks:** Telegram ToS / account ban; parsing reliability; phone-login ops.

---

## Task 3: UI Language Switcher (RU/BOS, decision D2)

**Goal:** Bosnian interface language.

**Acceptance Criteria:**
- Session-scoped locale (`/set-lang/bosnian` | `/set-lang/russian`); middleware sets `request.LANGUAGE_CODE`.
- `get_name(locale)` on `Category`/`City` returns `name_i18n[locale]` when present, else Russian `name` fallback.
- Templates use `{% trans %}` with Russian default; UI chrome translated RU↔BS; **content (ad text) stays Russian-stored** (decision G invariant).
- `name` (Russian) used for storage/search; `name_i18n.bs` only for UI labels.

**Artifacts:** `core/utils/i18n.py`, language middleware, updated templates, locale files.
**Dependencies:** Phase 1 Task 3
**Risks:** Translation sync; session handling.

---

## Task 4: Query Translation Integration (decision G)

**Goal:** Search-time Bosnian → Russian.

**Acceptance Criteria:**
- Translate Bosnian query to Russian via `deep-translator` before FTS (timeout ~500ms, fallback to original query, 5-min cache).
- Search view (Phase 1 Task 11) calls translation service; results marked "переведено с русского" when applicable.
- One-word fuzzy category detect (difflib) still runs on the translated query.

**Artifacts:** `apps/core/services/translation.py`, search view update.
**Dependencies:** Phase 1 Task 11
**Risks:** Translation accuracy; latency; rate limits.

---

## Task 5: Content Language Invariant Check (decision G)

**Goal:** Guarantee Russian-stored content for FTS.

**Acceptance Criteria:**
- Confirm Phase 1 bot translates seller Bosnian input → Russian on ad creation (reuses `deep-translator` + request cache) so `to_tsvector('russian', ...)` is correct.
- Add validation test: `search_vector` built only from Russian; display layer translates RU→BS for BOS locale.
- Document the invariant in `apps/ads/services/content_translate.py`.

**Artifacts:** Validation test, comment/doc in service.
**Dependencies:** Phase 1 Task 9
**Risks:** Existing non-Russian content; translation failures.

---

## Task 6: Documentation Updates

**Goal:** Scraping + i18n spec finalization.

**Acceptance Criteria:**
- `docs/wiki/01`: decision B (scraping as separate API/service), decision G finalized.
- `docs/wiki/02`: `telethon>=1.44.0` added (deferred dep).
- `docs/wiki/03`: `scraping_service/` entrypoint documented.
- `docs/wiki/04`: `telegram_message_id` column; clarify `AdSource` stays `TELEGRAM` in phase 1.

**Artifacts:** Updated wiki files (English-only).
**Dependencies:** Tasks 1-5
**Risks:** Doc drift.

---

## Deferred / Out-of-MVP Scope (consistent with `01_plan_development_phases.md`)
- US-S6 (seller deletes own ad) — addressed in Phase 3 Task 5.
- US-B8 (responsive layout) — Tailwind/daisyUI defaults; AC verified at implementation.
- US-A6 (inactive-user purge) — deferred post-MVP.
- US-A9 (system-log admin view) — AnalyticsEvent covers metrics; full log view deferred.
- Tags (`tags`/`ad_tags`) — fully deferred (no generation source in spec).
