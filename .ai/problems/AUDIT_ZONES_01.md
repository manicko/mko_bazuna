# Audit Zones & Verification Questions — mko_bazuna MVP

> Source: 3x independent auditor passes over the spec (`docs/wiki/01_technical_specification.md`),
> packages (`02_packages.md`), structure (`03_structure.md`), and DB structure (`04_db_structure.md`).
> Classification: **CRITICAL** = core flow must work; **RESPONSIBLE** = mistake causes data loss / security / GDPR-equivalent breach; **DOUBTFUL** = risky, weakly justified, or contradictory design.
> Each zone carries a concrete verification question for the research phase.

---

## CRITICAL ZONES

### C1. Telegram LoginToken atomicity across dual processes
- **Refs:** decision H (01_spec L110–116), US-S1 (L154–161), 03_structure L33, 04_db_structure (table absent).
- **Concern:** `LoginToken` is described as "atomic, one-time, constant-time compare (`select_for_update`)" but the bot is a **separate process** writing `telegram_id` via shared ORM while the web polls readiness. Doc never states the web *consumes/clears* the token under the same lock, nor that the bot claims it transactionally. The `LoginToken` table is **not even listed** in `04_db_structure.md`.
- **Question:** Is `LoginToken` modeled with `expires_at`/`consumed` and a single atomic claim (`UPDATE ... SET telegram_id=?, consumed=true WHERE token=? AND consumed=false RETURNING *`) invoked by BOTH bot and polling web view so exactly one claim wins? Where is the table defined?

### C2. Editorial re-moderation hides ad + transition missing from state machine
- **Refs:** decision J (01_spec L126–127), US-S5 (L198), 04_db_structure AdStatus transitions (L86–90).
- **Concern:** Text edits must return ad to `ON_MODERATION` and hide it immediately; price/photo edits publish instantly (≤5s). The transition table shows `PUBLISHED → ARCHIVED → PUBLISHED` but **omits `PUBLISHED → ON_MODERATION`**, which US-S5/decision J require. A mixed-field edit form could wrongly hide or wrongly publish.
- **Question:** Is `PUBLISHED → ON_MODERATION` a supported transition in code, and is the ad hidden from buyers during that window? Does an instant price/photo edit also reset the archive timer?

### C3. Lifecycle timer reset vs "original publication date" contradiction
- **Refs:** decision J (01_spec L127), US-S7 (L218–223), 04_db_structure `original_published_at` (L61), `IX_ads_sweep(status,published_at)` (L173).
- **Concern:** Spec says archive@2mo / delete@4mo count from "original publication date" AND "any edit resets the timer to the edit moment" — contradictory. Schema has both `published_at` and `original_published_at`. Sweep index keys on `published_at` (reset semantics), leaving `original_published_at` possibly dead/confusing. Must resolve which column drives the sweep.
- **Question:** Which timestamp drives the archive/delete sweep, does it reset on every edit (incl. price/photo per decision J), and is `original_published_at` read anywhere?

### C4. ON_MODERATION_FAILED 7-day purge has no timestamp/index
- **Refs:** decision A (01_spec L50), US-A11 (L550), 04_db_structure (no `failed_at`; `IX_ads_sweep` keyed `published_at` L173).
- **Concern:** Failed-auto-check ads are purged ≤1 week, but such ads were never published (`original_published_at` NULL), so there is **no non-NULL timestamp** set at failure and the sweep index keyed on `published_at` cannot find them. Concrete schema gap.
- **Question:** Which column drives the 7-day purge, is a non-NULL timestamp set at auto-failure, and does `IX_ads_sweep` actually cover that query?

### C5. Async bot vs sync Django ORM — pooling, blocking I/O, migrations
- **Refs:** 02_packages (psycopg3 L17, aiogram L41), 03_structure (bot process L33, web gunicorn L85), decision H select_for_update.
- **Concern:** aiogram bot runs an async loop and calls `django.setup()` + shared ORM; downloads Telegram photo bytes (blocking I/O) and ORM writes must not block the loop or starve the web pool. Two processes each open pools against one PG. Migrations must run exactly once — both `web` and `bot` start from `depends_on db (healthy)` with no migration service / ordering guard.
- **Question:** How does the bot do blocking ORM/Telegram downloads without blocking the async loop (sync_to_async/threadpool) or starving the web pool? Where do migrations run (dedicated step vs guarded per entrypoint) to avoid two processes migrating concurrently? Is `CONN_MAX_AGE`/pool sizing documented per process?

### C6. Auto-moderation timing vs "<=5s to published" SLA with no async worker
- **Refs:** US-A10 (01_spec L524–566), 02_packages (Celery deferred L53), 03_structure (cron/management commands).
- **Concern:** Auto-check (min length, banned words, ad count) is the sole gate to `published` with a ≤5s appear SLA, but there is no async worker in phase 1 — only management commands + cron. Synchronous in bot handler ties SLA to bot latency; a sweep makes ≤5s impossible.
- **Question:** Is US-A10 auto-check synchronous in `create_ad_from_message` or a near-real-time sweep, and which component owns the ≤5s SLA given no async workers exist?

### C7. Search response <2s at 500k with category/city/price filters
- **Refs:** US-B2 (≤2s L279), US-B3 (price range), 04_db_structure indexes (L163–177, no price index L177).
- **Concern:** Combined `search_vector @@ query AND city_id AND category_id AND status=PUBLISHED AND price BETWEEN` at 500k rows; `price` has no index (documented "rare"), and `search_vector` GIN assumption is unverified (see D12). SLA risk.
- **Question:** Under 500k ads with realistic category/city skew, does the combined FTS + city + price-range query stay <2s? Is `price` range truly rare enough to skip an index, or should it join a composite listing index?

### C8. Bot draft lifecycle vs DRAFT status + 30-min sweep scope
- **Refs:** decision I (01_spec L122), AdStatus.DRAFT (04_db L78), aiogram FSM SQLStorage (02_packages L42).
- **Concern:** "Abandoned drafts auto-deleted on 30-min idle timeout, no half ads saved" conflicts with a persistent `DRAFT` row in `ads`. Where does draft state live — aiogram FSM memory (lost on restart) or `ads` rows (violates "nothing saved")? Is the 30-min sweep idle (per message) or wall-clock?
- **Question:** Does the implementation persist any `ads` row with `status=DRAFT`, or is draft state purely in aiogram FSM `SQLStorage`? Is the 30-min purge keyed on last-user-activity or dialog-start wall-clock?

---

## RESPONSIBLE ZONES

### R1. GDPR-equivalent hard-delete completeness & telegram_id nulling
- **Refs:** decision F (01_spec L93), US-A8 (L504), 04_db_structure `hard_delete_at` (L38).
- **Concern:** Soft-delete immediate; `telegram_id` nulled 30 days after `consent_revoked_at` via idempotent task. But `username` (also PII per decision F), `analytics_events.user_id` FK, and ad authorship may persist. Nulling `telegram_id` alone may not satisfy erasure. No users-side index on `consent_revoked_at` (the `IX_ads_consent_sweep` is on **ads**, L174).
- **Question:** Does the idempotent task fully erase PII linkage (`username`, `analytics_events`, moderator logs, ad authorship) or only null `telegram_id`? Is there a users-side sweep keyed on `consent_revoked_at + 30d`, idempotent and indexed?

### R2. Active ad + nulled telegram_id breaks contact deep-link
- **Refs:** decision C (01_spec L62–67), US-B5 (L324), decision F (L93).
- **Concern:** Contact flow `start=contact_<ad_id>` resolves seller via `ad_id → user → telegram_id`. If an ad is still `PUBLISHED`/`ARCHIVED` when `telegram_id` is nulled after 30 days, the relay silently fails. Doc never states handling for deleted/consent-revoked sellers in the contact flow.
- **Question:** When a buyer opens a contact link for an ad whose seller deleted account / revoked consent (NULL `telegram_id`), what does the bot return, and is the `contact` link still rendered publicly? Is "active ad + nulled telegram_id" an explicitly handled or forbidden state?

### R3. Consent "decline" (browse-only) vs "revoke" (soft-delete) state collision
- **Refs:** decision K (01_spec L133), decision F (L93), 04_db_structure `consent_given_at`/`consent_revoked_at` (L36–37).
- **Concern:** K: declining banner only blocks seller actions, contact link keeps working. F: revoking consent triggers immediate soft-delete + 30-day null. DB has no field distinguishing "browse-only decline" from "account-deletion revoke." Risk: a mere banner decline could trigger the deletion cascade.
- **Question:** Are banner-decline (browse-only, no deletion) and consent-revoke/account-delete (soft-delete + 30-day erase) distinct states, or does any `consent_revoked_at` set wrongly trigger deletion?

### R4. US-S8 account deletion vs ads_auto_publish contradiction
- **Refs:** US-S8 (01_spec L226–237), US-S9 (L239–250).
- **Concern:** US-S8 says set `ads_auto_publish=False` then "if not set, account is deleted" — backwards. `ads_auto_publish=False` is a *publishing ban* (US-S9: keeps old ads, reversible). Using it as the delete gate inverts meaning: a seller intending only to pause could lose all data, or a seller intending deletion could leave data intact. Potential silent GDPR breach.
- **Question:** In the shipped `account_delete` flow, does `ads_auto_publish=False` (a) prevent deletion, (b) trigger it, or (c) have no effect — and does US-S8 match US-S9's definition of the same flag?

### R5. analytics_events FK retention after erasure
- **Refs:** decision L (01_spec L138–141), US-A8, 04_db_structure `analytics_events.user_id` (L148).
- **Concern:** `user_id` FK → `users.id`, not `telegram_id` directly. Nulling `telegram_id` does NOT anonymize the event row — the FK still ties it to the soft-deleted user, arguably still personal-data linkage post-revocation. No stated cascade/nulling on consent revoke.
- **Question:** On consent revoke / account soft-delete, are `analytics_events.user_id` rows nulled or retained? Does retained FK after `telegram_id` null satisfy the erasure intent?

### R6. Seller anonymity leakage via templates / image URLs
- **Refs:** decision C (01_spec L62–67), US-B4/B5, 04_db_structure `ad_images.image` (L133).
- **Concern:** Anonymity holds only if templates never render `username`/`telegram_id` and storage keys are ad-scoped (not user-scoped). If django-storages emits a URL with a `user_id`/`telegram_id` segment, identity leaks via the URL. Admin "ban by account" (US-A3) could also expose `telegram_id`.
- **Question:** Do any public templates or generated image URLs embed `user_id`/`telegram_id`/`username`? Is `ad_images.image` keyed purely on `ad_id`, and is the contact deep-link the only seller-linked surface?

### R7. Telethon secrets (API_ID/API_HASH) in phase-1 .env
- **Refs:** 03_structure (L99 .env secrets), 02_packages (L7 "Telethon NOT used in phase 1").
- **Concern:** `API_ID`/`API_HASH` are MTProto/userbot (Telethon) credentials, not needed for aiogram Bot API in phase 1. Listing them in `.env` is dead/confusing and a secret-hygiene risk if real. Also `SECURE_SSL_REDIRECT=True` + Certbot needs renewal automation not described.
- **Question:** Why are `API_ID/API_HASH` present in phase-1 `.env` when only aiogram Bot API is used? Are they real credentials, and is there a documented cert-renewal process for nginx TLS?

### R8. Image storage security & nginx /media rules
- **Refs:** decision E-storage (01_spec L85), 03_structure (L99 media deny rule), 04_db_structure `ad_images.image` (L133).
- **Concern:** Only `location ~* /media/.*\.(php|py|cgi)$ { deny all; }` is specified. No `Content-Type` enforcement, no `X-Content-Type-Options: nosniff`, no `Content-Disposition`, and SVG/HTML could bypass the extension list. Telegram "only JPEG" is input-side (bot `message.photo`), not enforced at the storage/serve boundary. Sequential/guessable keys would expose all uploads.
- **Question:** Does nginx set `nosniff`/content-type enforcement for `/media/`, are non-JPEG types (SVG, HTML) blocked at *upload validation*, and are media URLs unguessable (hashed keys) or sequential?

### R9. Re-registration uniqueness vs 30-day nulling window
- **Refs:** US-S8 (re-register via Telegram), US-A4/A6, 04_db_structure `telegram_id UNIQUE, nullable` (L29).
- **Concern:** After deletion + 30-day null, same Telegram user re-registers. Soft-deleted row persists (`is_deleted=True`); a new UNIQUE `telegram_id` insert collides unless old row already nulled. Risk of uniqueness conflict if delete→re-register happens within the 30-day window before null job runs.
- **Question:** On re-registration, is the old soft-deleted row reused (telegram_id re-bound) or a new row created, and does UNIQUE + 30-day nulling guarantee no collision?

---

## DOUBTFUL ZONES

### D1. Categories excluded from search_vector vs US-B2/B3/B6 + did-you-mean
- **Refs:** 04_db_structure (L65–72, L159–161), US-B2/B3/B6, decision G did-you-mean (city only).
- **Concern:** `search_vector` GENERATED column "cannot JOIN" so `category.name` excluded; category search = `category_id` filter. Buyers typing a category word in the search box get no category match, and did-you-mean covers only cities. Silent miss for translated/misspelled category terms.
- **Question:** Is category discoverability through the keyword box an accepted non-goal, or is there a plan (e.g. redirect category tokens to `category_id` filter)? Does did-you-mean ever apply to category names?

### D2. mptt single source of truth + i18n category/city names
- **Refs:** 04_db_structure (L92–103 mptt), decision G (L96 bilingual UI), US-B9.
- **Concern:** django-mptt is the only category truth with a single `name` column, but UI is bilingual (Russian + Bosnian Latin). No i18n model for category/city names; Bosnian users may see Russian category names. Category names are also never indexed in Russian for FTS.
- **Question:** Are category/city `name` fields single-language only, and how does the Bosnian UI render them? Is there any translation layer?

### D3. Moderation criteria storage & "new ads only" versioning
- **Refs:** US-A11 (01_spec L559–565), 04_db_structure (no criteria table; `moderation/` app implied).
- **Concern:** Admin edits criteria (banned words, min length, max images, max ads/user) at runtime, applied to new ads only. No `ModerationRule`/`ModerationCriteria` model in schema; if criteria live in `settings.py`, they are not runtime-editable (contradicts US-A11). No `criteria_version`/`checked_with` column on `ads`, so "new ads only" is unauditable.
- **Question:** Where do criteria physically live (DB table vs settings), is there a runtime admin UI per US-A11, and does each ad record which criteria version evaluated it?

### D4. REJECTED vs ON_MODERATION_FAILED retention gap
- **Refs:** US-A11 (L548–551 "parallel terminal states"), 04_db_structure (7-day only for `ON_MODERATION_FAILED` L82; no REJECTED retention).
- **Concern:** `REJECTED` = "longer storage" (vague, unspecified); `ON_MODERATION_FAILED` = ≤1 week. No sweep/retention defined for `REJECTED` — it can grow unbounded as a permanent graveyard. Split adds state-machine complexity with no clear operational driver.
- **Question:** What is the concrete retention + purge for `REJECTED`? Should the two terminal states be merged?

### D5. Bosnian→Russian query translation dependency & SLA
- **Refs:** decision G (L97), 02_packages (deep-translator L10), US-B2 (≤2s).
- **Concern:** `deep-translator` is a free, rate-limited, network-dependent SaaS wrapper called per search. No fallback if it times out/is throttled — every Bosnian search fails or hangs, threatening ≤2s SLA. Also FTS config is `russian`; if any Bosnian-Latin seller text leaks into `title`/`description`, the Russian stemmer mishandles it (translation fixes the *query*, not stored content).
- **Question:** Is `deep-translator` called synchronously in the search path, is there a cached/fallback (`pg_trgm`) path, and is stored content guaranteed 100% Russian so `russian` config never sees Bosnian-Latin tokens?

### D6. GIN index possibly created as BTREE via models.Index
- **Refs:** 04_db_structure `IX_ads_search_gin` (L172).
- **Concern:** `models.Index(fields=['search_vector'])` creates a BTREE by default; a true GIN requires `GinIndex`/`opclasses=['gin_trgm_ops']`. As written, the "GIN index" may be btree, silently defeating FTS performance at 500k rows and breaking the <2s target.
- **Question:** Does the migration create a true GIN on `search_vector` (verify via `pg_indexes`)? If btree, FTS at 500k will miss SLA.

### D7. aiogram FSM SQLStorage vs Django ORM dual-write ownership
- **Refs:** 02_packages (aiogram SQLStorage L42), 03_structure (bot django.setup + shared ORM L33).
- **Concern:** Bot opens two DB layers: aiogram's own FSM tables and Django ORM (LoginToken/ads). Two transaction contexts, two migration owners for one DB. "Single source of truth" principle quietly violated for bot state. Cross-context race: FSM committed but ad/LoginToken ORM write rolled back (or vice versa).
- **Question:** Are aiogram FSM tables migration-owned (by which app), and are there cross-context transaction races between FSM state commit and `ads`/`LoginToken` writes in the same logical operation?

### D8. ModeratorActionLog missing from schema
- **Refs:** US-A11 (reason "from ModeratorActionLog, never shown to seller"), 04_db_structure (omitted).
- **Concern:** `ModeratorActionLog` is referenced (stores rejection reasons, PII-adjacent) but absent from the schema doc. `published_by`/`moderated_by` NULL semantics depend on it to distinguish auto vs manual. No stated retention bound for the log.
- **Question:** Does `ModeratorActionLog` exist as a concrete table (FK ad + admin + reason + timestamp)? Do NULL `published_by`/`moderated_by` reliably mean "auto"? Is log retention bounded?

### D9. mptt concurrent admin edits vs bot category reads
- **Refs:** 04_db_structure (L92–103 mptt), US-A7 (admin add/edit/deactivate), bot TOP-3-5 suggestions.
- **Concern:** mptt tree rebuilds under concurrent category writes can lock the whole table; the bot reads the tree for suggestions and the listing/filter hot path uses it. No caching/rebuild-locking strategy documented for ~500k ads.
- **Question:** Are category reads in the hot listing/filter path served from mptt queries that could contend with admin `MPTTModel` writes? Is there a caching/rebuild-lock strategy?

### D10. Web tier: sync gunicorn vs ASGI/UvicornWorker
- **Refs:** 03_structure (L85 `gunicorn config.asgi:application [+UvicornWorker]`).
- **Concern:** Doc shows both `asgi:application` + UvicornWorker hints (async) but the HTMX MPA is server-rendered/sync-friendly; the brief calls it "web gunicorn sync." psycopg3 pooling differs between sync and async modes. Authoritative mode unclear.
- **Question:** Is the web tier sync gunicorn (WSGI `wsgi:application`) or async (`asgi:application` + UvicornWorker)? Which is authoritative, and does psycopg3 pooling config match the chosen mode?

### D11. currency column / price INT speculative
- **Refs:** 04_db_structure `currency VARCHAR(3) DEFAULT 'BAM'` (L64), `price INT` (L53), decision D/G.
- **Concern:** Single currency phase 1; `currency` column implies multi-currency readiness the rest of the schema doesn't support — speculative per "avoid overengineering." INT price fine for whole-BAM.
- **Question:** Is `price` INT sufficient for all realistic BAM listings, and is `currency` dead-weight until a second currency appears? Recommend dropping `currency` until actually needed.

### D12. Failed-check 7-day sweep vs log 7-day sweep — one or two?
- **Refs:** decision A (L50 ad purge ≤1wk), decision F (L93 "logs of failed checks auto-clean 7 days").
- **Concern:** Two different 7-day timers mentioned (failed-check ad rows vs logs). Are they the same sweep or distinct? Unclear.
- **Question:** Are there one or two 7-day sweeps (ad rows vs logs), and what is the retention/hard-delete for `REJECTED` (see D4)?

---

## OWNER CLARIFICATION NEEDED (BLOCKING — legal/data-loss/GDPR)

These must be answered by the system owner before/within research. They block correct
resolution of the responsible zones. Until answered, research phases assume the SAFEST
default (no silent data loss, full erasure scope) and flag the assumption.

- **O1 (R4 / US-S8 vs US-S9) — RESOLVED by owner:** Three independent states confirmed:
  1. **Publishing ban** (`ads_auto_publish=False`, US-S9): reversible toggle; bot rejects NEW ads; OLD ads are HIDDEN (stored, not displayed) while ban active; can be lifted anytime.
  2. **Account deletion** (US-S8): explicit confirmed action; `is_deleted=True` + `deleted_at`; all ads → `DELETED`; `telegram_id` nulled after 30d via decision-F path. NOT linked to publishing-ban flag.
  3. **Account ban** (NEW 3rd state, admin-only, US-A4): keep `telegram_id` + `username` as a blocklist memory; HIDE and PURGE the user's ads (delete ad rows, keep user row + PII); does NOT erase PII so re-entry is blocked. Distinct from deletion (which erases PII after 30d).
  - Implication for R9 re-registration: a BANNED user must NOT be able to re-register (telegram_id kept, UNIQUE blocks re-bind); only DELETED (post 30-day null) users can re-register by row reuse.
- **O2 (R3 / decision K vs F):** PENDING owner.
- **O3 (R1 / decision F):** PENDING owner — erasure scope (analytics_events, moderator logs, ad text) after 30-day null.
- **O4 (D3 / US-A11):** PENDING owner — moderation criteria storage + runtime editing scope.
- **O5 (D1 / D2 / decision G):** **RESOLVED by owner** — search by category NAME is mandatory in phase 1 (hybrid approach C: denormalized `category_name` in `search_vector` + app-level fuzzy `category_id` filter). Category-name search is NOT a non-goal.

---

## RESEARCH PRIORITY ORDER (highest blast radius first)

1. R4 (O1) — account deletion contradiction (legal/data-loss)
2. R1 (O3) — GDPR erasure completeness
3. C4 / D12 — 7-day purge schema gap + GIN-vs-btree (silent break at scale)
4. C1 — LoginToken atomicity (core auth flow)
5. C3 / C2 — lifecycle timer + re-moderation transition
6. R2 / R3 (O2) — consent vs contact-link interaction
7. C5 / C7 — async bot pooling + search SLA
8. D3 / D4 / D8 — moderation criteria, REJECTED retention, ModeratorActionLog
9. R6 / R8 — anonymity leakage + image storage security
10. Remaining DOUBTFUL zones (D1,D2,D5,D6,D7,D9,D10,D11,D12)

---

## RESOLUTIONS (validated: 3x researcher + validator ACCEPT per zone)

Each zone below was resolved by 3 independent researchers and confirmed by a validator. The solution is the agreed PRIORITY SOLUTION. Doc fixes are applied in step 7 per `docs/00-overview/doc-maintenance-rules.md`.

| Zone | Resolution (summary) |
|------|----------------------|
| **R4** (O1 RESOLVED) | Three independent states: (1) Publishing ban `ads_auto_publish=False` = reversible, bot rejects NEW ads, OLD ads HIDDEN while banned; (2) Account deletion = explicit confirmed action → `is_deleted`, all ads→`DELETED`, `telegram_id` nulled 30d (decision F); (3) Account ban (admin) = keep `telegram_id`+`username` as blocklist, PURGE ads, no PII erasure. `is_banned` already exists in schema. No relationship between ban flag and deletion. |
| **R1** (O3 SAFEST-DEFAULT) | Full erasure scope: at `consent_revoked_at`+30d sweep → null `telegram_id`, null `username`, DELETE user's ad rows (+ad_images), SET NULL `analytics_events.user_id` (keep counts), SET NULL `ModeratorActionLog.user_id` (keep reason/admin/timestamp). Add `IX_users_erasure_sweep(consent_revoked_at)` on users. Define `ModeratorActionLog` (D8). No `gdpr_erasure_log` table. |
| **C4 / D12** | Add `moderation_failed_at` timestamp (set at ON_MODERATION_FAILED). Replace single `IX_ads_sweep` with three partial indexes: `IX_ads_archive_sweep(status,published_at, PUBLISHED)`, `IX_ads_delete_sweep(status,published_at, ARCHIVED)`, `IX_ads_purge_failed(status,moderation_failed_at, ON_MODERATION_FAILED)`. Remove misattributed ads-side `IX_ads_consent_sweep` (becomes `IX_users_erasure_sweep`). Replace `models.Index(search_vector)` with `GinIndex(search_vector)` (true GIN on TSVECTOR). |
| **C1** | Define `login_tokens`: `token_hash` SHA-256 UNIQUE indexed (raw never stored), `telegram_id` nullable, `created_at`, `expires_at`(+5min), `consumed_at` nullable. Two-phase atomic claim: bot `UPDATE ... SET telegram_id=<tg> WHERE token_hash=? AND telegram_id IS NULL AND consumed_at IS NULL AND expires_at>now()`; web `UPDATE ... SET consumed_at=now() WHERE token_hash=? AND telegram_id IS NOT NULL AND consumed_at IS NULL AND expires_at>now()`. Constant-time via `hmac.compare_digest`. Sweep deletes expired. Session cookies SECURE/HTTPONLY/SAMESITE=Lax. |
| **C2 / C3** | Add `PUBLISHED → ON_MODERATION` to transition table (text edits only, hidden immediately). US-S5 branching note: text→moderation, price/photo→instant, mixed→text rule. Decision J clarified: timers key on `published_at` (reset baseline, updated on every PUBLISH transition); `original_published_at` is immutable audit-only. No new column. |
| **R2 / R3** (O2 SAFEST-DEFAULT) | R3: banner decline = REFUSAL (`consent_given_at` NULL, no erasure); revoke = WITHDRAWAL (sets `consent_revoked_at`, erasure). Fix decision F wording. R2: contact link rendered ONLY when ad PUBLISHED + seller `telegram_id` NOT NULL + not `is_deleted`/`is_banned`/`consent_revoked_at` NULL. Bot: ad missing/non-PUBLISHED → "ad no longer available"; seller null/deleted/banned/revoked → "seller no longer reachable"; never reveal PII. |
| **C5 / C7** | C5: bot wraps ORM + Telegram blocking I/O in `sync_to_async` (default thread-sensitivity for ORM); per-process psycopg3 pool (`CONN_MAX_AGE=0`); recommend PgBouncer (transaction mode) as shared pool; migrations run once before both processes start. C7: benchmark-first price index (no index for MVP, EXPLAIN ANALYZE gate at 500k); deep-translator hard timeout (500ms) + fallback = search ORIGINAL query on GIN `search_vector` (fast near-empty for Bosnian, preserves <2s). |
| **D3 / D4** (O4 RESOLVED) | D3: `moderation_criteria` singleton (runtime-editable, applied to new ads). Auto layer: title_min/max_length, description_min/max_length, price_required, min_images, max_images, banned_words (JSONB), max_ads_per_user, duplicate_title_threshold. Manual layer (admin): photo prohibited-content review (adult/violence/drugs/hate/counterfeit/illegal/spam/off_topic), future ML. `min_text_length` removed (dup of per-field mins). D4: keep both terminal states; REJECTED bound with `rejected_at` + `IX_ads_rejected_sweep` purging at 90d (mutually exclusive with `moderation_failed_at`). |
| **R6 / R8** | R6: `ad_images.image` keys ad-scoped + unguessable (UUID v4); public templates never render user PII (only contact deep-link); admin may see `telegram_id`. R8: validate JPEG at storage boundary (magic bytes/PIL, reject non-JPEG with 415); nginx `/media/` sets `X-Content-Type-Options: nosniff`, `image/jpeg` whitelist, default `application/octet-stream`, keeps script-ext deny, `Content-Disposition: inline`. |
| **D1 / D2** (O5 RESOLVED) | D2: add `name_i18n` JSONB ({"ru","bs"}) to categories + cities; `get_name(locale)` with Russian fallback; mptt stays tree source. D1: per OWNER requirement, search by category NAME is MANDATORY in phase 1 (hybrid approach C, validated): denormalize `category_name` (Russian) onto `ads`, include it in `search_vector` (weight 'C') maintained by triggers; app-level fuzzy detection (difflib) applies `category_id` filter for single-word queries. Bosnian query translated to Russian first (decision G) so it matches the Russian category name. |
| **D5 / D6** | D5: bot MUST translate seller title+description to Russian at creation (reuse deep-translator + cache) to enforce "stored content is Russian" invariant so `to_tsvector('russian',...)` is correct; display translates back for Bosnian viewers. D6/GIN resolved in C4/D12 (GinIndex). |
| **D7 / D9 / D10** | D7: aiogram FSM tables independent (own migration ownership); domain writes in one Django transaction; clear FSM after success; no 2PC. D9: cache active category tree (~30 nodes), invalidate on admin write. D10: phase-1 web = sync WSGI (`config.wsgi:application`); remove `[+UvicornWorker]` ambiguity; ASGI reserved for future. |
| **D11** | Drop speculative `currency` column (single BAM phase 1, YAGNI); `price` INT = whole BAM (no decimals in UI); document post-MVP StrEnum Currency if multi-currency added. |

**STATUS: ALL 28 ZONES RESEARCHED, VALIDATED (3x researcher + validator ACCEPT), AND DOC FIXES APPLIED.**
See `docs/wiki/01_technical_specification.md`, `02_packages.md`, `03_structure.md`, `04_db_structure.md` for the applied changes (tagged with zone IDs inline).

**Owner pending clarifications (safe-defaults applied; awaiting owner confirmation):**
- **O2 (R3):** PENDING. Applied safe-default: banner-decline = REFUSAL (no erasure), revoke = WITHDRAWAL (erasure). Owner should confirm the two states are distinct in the product UX.
- **O3 (R1):** PENDING. Applied safe-default: full erasure scope (null telegram_id+username, DELETE ads, SET NULL analytics/ModeratorActionLog). Owner should confirm this is the intended GDPR-equivalent scope.
- **O4 (D3 / US-A11):** **RESOLVED by owner** — two-layer moderation: automatic (text/length/required-fields/duplicates in `moderation_criteria` singleton) + manual photo-review (8 prohibited-content categories, future ML). `min_text_length` removed as redundant.
- **O5 (D1/D2):** **RESOLVED by owner** — search by category name is mandatory in phase 1 (hybrid C applied).

