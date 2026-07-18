# Phase 5 Detailed Plan: Scraping Service + Internationalization (Deferred)

**Wave:** Extensions
**Depends_on:** Phase 1 (ORM, models, translation infrastructure)
**Files_modified:** `scraping_service/`, `src/backend/apps/`, `docs/wiki/*.md`
**Autonomous:** Yes

> **Spec source:** `docs/wiki/01_technical_specification.md` (decision B — scraping separate process/API, NOT in bot; decision G — content Russian + query/UI translation; decision D2 — name_i18n; US-B9 RU/BS UI), `docs/wiki/02_packages.md` (telethon deferred), `docs/wiki/03_structure.md` (scraping_service/ separate process), `docs/wiki/04_db_structure.md` (telegram_message_id for dedup).
> **Planner note:** Produced via 3 iterative Planner runs. Coverage audit, decision B strictness, zone R7, decision G invariant verified in run 3.

---

## Task 1: Scraping Schema Migration (telegram_message_id)

**Goal:** Dedicated column for third-party message deduplication.

**Acceptance Criteria:**
- Add `telegram_message_id` (BIGINT, nullable, UNIQUE, indexed) to `ads` table via Phase 5 migration.
- Phase 1 `AdSource` remains `TELEGRAM` only (decision B: scraping is a SEPARATE future phase with its own ingestion path, not merged into the bot's source enum). Both bot and scraping service write `source=TELEGRAM`, distinguished by `telegram_message_id IS NOT NULL` for scraped content.
- Migration is online-safe: nullable column addition, then `CREATE INDEX CONCURRENTLY` via Django `AddIndexConcurrently` (PostgreSQL 17 compatible).
- UNIQUE constraint allows multiple NULL values (PostgreSQL behavior), ensuring no conflicts with existing rows.

**Artifacts:** `apps/ads/migrations/000X_add_telegram_message_id.py`.
**Dependencies:** Phase 1 Task 2 (Ad model).
**Risks:** Unique-constraint impact on existing rows; migration ordering.

---

## Task 2: Telethon Scraping Service (separate process, decision B)

**Goal:** Monitor third-party Telegram groups via a standalone userbot.

**Acceptance Criteria:**
- `scraping_service/main.py`: Telethon MTProto phone-login (API_ID/API_HASH added to `.env` for this phase — NOT present in phase 1 per zone R7). Sessions stored in `scraping_service/sessions/`.
- **Rationale:** Telethon is required because bot accounts (aiogram) CANNOT read third-party groups/channels. Only MTProto userbot with phone-login can access external content. Telethon's lack of FSM is irrelevant for scraping (no multi-step dialog needed).
- Reads messages from configured groups/channels; parses ad structure (photos, text, price).
- Creates ads via shared ORM (`django.setup()`) with `telegram_message_id` populated for deduplication. Status starts `ON_MODERATION` (same auto-moderation gate as bot).
- Runs as a separate systemd service, independent of web/bot.
- NOT inside the aiogram bot (decision B) — standalone Telethon process.

**Artifacts:** `scraping_service/main.py`, `scraping_service/parsers/`, `scraping_service/config.py`, systemd unit file.
**Dependencies:** Task 1, Phase 1 ORM.
**Risks:** Telegram ToS / account ban; parsing reliability; phone-login ops.

---

## Task 3: UI Language Switcher (RU/BOS, decision D2)

**Goal:** Bosnian interface language for UI chrome (not ad content).

**Acceptance Criteria:**
- Session-scoped locale (`?lang=bs` | `?lang=ru`); middleware sets `request.LANGUAGE_CODE`.
- `get_name(locale)` method on `Category`/`City` models: returns `name_i18n[locale]` when present, else Russian `name` fallback (decision D2).
- Templates use `{% trans %}` with Russian default; UI chrome translated RU↔BS.
- **Content invariant (decision G):** `title` and `description` fields remain Russian-stored; `name_i18n.bs` ONLY for UI labels (category/city names in interface).
- Language preference persists across sessions via cookie.

**Artifacts:** `core/middleware/locale.py`, language switcher template fragment, updated templates.
**Dependencies:** Phase 1 Task 3 (Categories/Locations models with `name_i18n`).
**Risks:** Translation sync; session handling.

---

## Task 4: Query Translation Integration (decision G)

**Goal:** Search-time Bosnian → Russian translation for FTS.

**Acceptance Criteria:**
- Translate Bosnian query to Russian via existing `deep-translator` infrastructure (reused from Phase 1) before FTS lookup.
- Translation service: hard timeout ~500ms, mandatory fallback to original query on failure, 5-min in-memory cache (same as Phase 1 search view).
- Search view calls translation service; results marked "переведено с русского" when applicable.
- One-word fuzzy category detect (difflib) runs on translated query (existing pattern from Phase 1).

**Artifacts:** Update `apps/search/services/query_translator.py` to expose reusable `translate_query(text, source_lang='bs', target_lang='ru')`.
**Dependencies:** Phase 1 Task 11 (search view exists).
**Risks:** Translation accuracy; latency; rate limits.

---

## Task 5: Content Language Invariant Validation Test (decision G)

**Goal:** Guarantee Russian-stored content for FTS correctness.

**Acceptance Criteria:**
- Validation test confirms: Bosnian input to bot → stored as Russian → `search_vector` uses Russian tokens → UI displays translated to Bosnian.
- Test scenario: create ad via bot with Bosnian title/description; verify `ads.title` and `ads.description` are Russian (translated); verify `search_vector` tsvectorizes Russian; verify `get_name('bs')` uses `name_i18n.bs` fallback.
- Document invariant: "All ad content is stored in Russian. Query translation (BS→RU) happens at search time. Display translation (RU→BS) happens at render time."
- Utilize existing Phase 1 infrastructure — no new translation code, only tests.

**Artifacts:** `apps/ads/tests/test_content_invariant.py`, doc update in `apps/ads/services/content_translate.py`.
**Dependencies:** Phase 1 Task 9 (bot translation), Phase 1 Task 11 (search).
**Risks:** Existing non-Russian content; translation failures.

---

## Task 6: Documentation Updates

**Goal:** Finalize scraping + i18n spec in wiki.

**Acceptance Criteria:**
- `docs/wiki/02_packages.md`: Add `telethon>=1.44.0` to package list under "Deferred Packages" section (not runtime).
- `docs/wiki/03_structure.md`: Document `scraping_service/` entrypoint structure and that API_ID/API_HASH are phase-5 additions to `.env`.
- `docs/wiki/04_db_structure.md`: Document `telegram_message_id` column purpose; clarify `AdSource` remains `TELEGRAM` in phase 1 (scraping uses same value with message_id for distinction).

**Artifacts:** Updated wiki files (English-only per rule 1).
**Dependencies:** Tasks 1-5.
**Risks:** Doc drift.

---

## Coverage Audit Summary

| Requirement | Covered By Task | Notes |
|-------------|-----------------|-------|
| US-B9 (RU/BOS UI) | Task 3 | Language switcher + `get_name(locale)` |
| Decision B (scraping separate) | Task 2 | Standalone Telethon userbot, NOT in aiogram bot |
| Decision G (content Russian + translation) | Tasks 4+5 | BS→RU at search (reuse), RU→BS at display, invariant test |
| Decision D2 (name_i18n) | Task 3 | `name_i18n` JSONB on Category/City models |
| Zone R7 (API_ID/API_HASH) | Task 2 | Added in phase 5 only; removed from phase 1 |
| telegram_message_id migration | Task 1 | Nullable BIGINT UNIQUE, CONCURRENTLY index, AdSource=TELEGRAM only |

## Version Exactness (vs docs/wiki/02_packages.md)

- `telethon>=1.44.0` — **ADDED** in Phase 5 (was deferred in phase 1)
- `deep-translator>=1.11.0` — **REUSED** (existing from Phase 1)
- `django-storages>=1.14.6` — **DEFERRED** (no code change needed; STORAGES contract)
- `boto3>=1.35.0` — **DEFERRED** (YAGNI until S3/R2 swap)

## Rule Compliance Checklist

| Rule | Status | Evidence |
|------|--------|----------|
| 10 (StrEnum) | OK | No new enums; uses Phase 1's `AdSource`, `AdStatus` |
| 15 (Small modules) | OK | Tasks split by concern; `scraping_service/` separate |
| 13 (Migrations) | OK | Task 1 explicit about migrations |
| 1 (English-only) | OK | All artifacts specified English; doc-maintenance-rules apply |

## Deferred / Out-of-MVP Scope (consistent with `01_plan_development_phases.md`)

- US-S6 (seller deletes own ad) — addressed in Phase 3 Task 5.
- US-B8 (responsive layout) — Tailwind/daisyUI defaults; AC verified at implementation.
- US-A6 (inactive-user purge) — deferred post-MVP.
- US-A9 (system-log admin view) — AnalyticsEvent covers metrics; full log view deferred.
- Tags (`tags`/`ad_tags`) — fully deferred (no generation source in spec).
