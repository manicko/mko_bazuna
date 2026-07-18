# Architecture Audit — Consolidated Key Zones & Open Questions

**Project:** mko_bazuna — Telegram-linked classifieds board (Django MVP)
**Audit basis:** 3 independent auditor passes over `docs/wiki/01..04` + `.kilo/rules/project.md`
**Purpose:** Unified list of zones requiring verification/research before implementation.

Findings are grouped into ZONES. Each zone carries a classification:
- `DOUBTFUL` — proposed design contradicts spec, spec is internally inconsistent, or tech choice is questionable.
- `RESPONSIBLE` — highest-risk area (data loss, security, correctness, compliance, operational reliability).
- `QUESTION` — blocking/unanswered decision.

---

## Z01 — Ad status state machine inconsistent across spec and DB schema  [RESPONSIBLE + DOUBTFUL]
- `04_db_structure.md:48` defines `status (draft | active | blocked | archived)`.
- Spec requires `on_moderation`, `published`, `rejected`/`on_moderation_failed`, `deleted` (01:49, 172, 203, 528, 540) plus the re-moderation cycle in decision J.
- The DB enum cannot represent the spec state machine. Every migration, transition rule, admin action (US-A3), and timer depends on this.
- **Must** reconcile to a single `StrEnum` (rule 10) covering all spec statuses.

## Z02 — One-time-code (OTP) login binding to telegram_id  [RESPONSIBLE]
- Decision H / US-S1 (01:107–113, 149): server-generated code bound to `telegram_id`, valid ≤10 min, stateless, single-use.
- No storage design for codes in `04` (no table/row); `03` shows only `.env.example`.
- Wrong design (guessable/replayable/not invalidated) lets an attacker log in as any seller. Highest auth-risk surface.
- Needs concrete store (DB row w/ TTL vs signed token) + replay protection before build.

## Z03 — GDPR / consent hard-delete timers and PII minimization  [RESPONSIBLE]
- Decision F (01:87–91, 496) + US-A8: soft-delete immediately, hard-delete/`telegram_id` null within 30 days; auto-purge failed-moderation logs at 7 days.
- `04_db_structure.md` has no `consent_at`, `deleted_at`, `hard_delete_at`, `revoked_at` columns; no scheduled-job owner defined.
- `04:31` adds `phone (VARCHAR)` with no US requiring it — contradicts minimal-data/anonymity stance (01:87–88).
- Missed 30-day job = unlawful retention. Needs explicit columns + named idempotent job.

## Z04 — Moderation subsystem has no DB backing  [RESPONSIBLE + DOUBTFUL]
- `03_structure.md:24` has a `moderation` app; US-A10/A11 require auto-check (only gateway), rejection reasons, moderator action journal, and admin-editable criteria (forbidden words, min length, max ads, max images).
- `04` defines no moderation-log/action table, no rejection-reason field on `ads`, no criteria table.
- Rejection reason must be stored but NEVER exposed by the public serializer (01:547).
- Needs log table, reason field, and criteria table before implementation.

## Z05 — Telegram bot lives outside Django but must write ads + run moderation  [RESPONSIBLE]
- `03_structure.md:33` puts `telegram_bot/` as a separate entrypoint; `services/create_ad_from_message` must create `ads`/`ad_images` and trigger moderation against the same Postgres.
- Access layer unspecified: `django.setup()` + shared models vs internal DRF API.
- Wrong choice risks connection-pool leaks, race conditions on `telegram_id` binding, orphaned transactions.
- Decision blocks the OTP + ad-create path integrity.

## Z06 — Search stack conflict: Haystack+Whoosh vs PostgreSQL FTS  [DOUBTFUL]
- `02_packages.md:5,27–28` mandates `django-haystack + whoosh`; `04_db_structure.md:54,148–154` defines `search_vector` (TSVECTOR) + GIN + `pg_trgm`.
- Two competing search layers. Whoosh is file-based (poor concurrency, not cloud-portable) and duplicates PG FTS the schema already relies on.
- For 500k Russian rows + 300/day, PG FTS + `pg_trgm` is sufficient and simpler (rule 5). Pick one.

## Z07 — Query-translation (Bosnian→Russian) mechanism unspecified  [QUESTION]
- Decision G (01:94–95) requires translating Bosnian buyer queries to Russian at search time.
- No translator library/API in `02_packages.md`. Blocks bilingual-search AC (US-B2:273).
- Needs: which translator (offline dict / API / LLM), fallback when translation fails, and composition with chosen search engine (Z06).

## Z08 — Telegram bot library mismatch: telethon vs aiogram  [DOUBTFUL]
- `02_packages.md:35` pins `telethon`; `03_structure.md:34` says "aiogram или telethon".
- Telethon (MTProto) vs aiogram (Bot API) change the entire `handlers/`/`states/`/`FSM` shape.
- Decision H/S2 need `message.photo` vs `message.document` inspection — both support, but one library must be locked.

## Z09 — Bot FSM state persistence undecided  [QUESTION]
- Decision I (01:115–119): step-by-step dialog, abandoned drafts auto-deleted after 30-min idle.
- `03_structure.md:36` lists `states/` but storage unspecified.
- In-memory FSM loses in-progress ads on bot restart; DB-backed re-couples bot to Django models (ties to Z05).
- Blocks bot structure.

## Z10 — Celery + Redis overengineering at this scale  [DOUBTFUL]
- `02_packages.md:8,39–40` adds Celery+Redis for "background jobs".
- Actual jobs: archive@2mo, delete@4mo (US-A5/S7), failed-mod purge@1wk, consent hard-delete@30d, bot draft timeout@30min — all low-frequency scheduled.
- Django management commands + cron (or `django-apscheduler`) suffice; Redis is a second stateful service to operate/back up. Violates rule 5.
- Justify each Celery task or drop it. Intersects Z02 (code storage) and Z11 (timers).

## Z11 — Ad lifecycle timers (decision J) under-specified vs schema  [RESPONSIBLE]
- Decision J (01:121–126): archive@2mo / delete@4mo from ORIGINAL `published_at`, RESET on any edit; independent 1-week and 30-day timers.
- `04` has `published_at` but no `archived_at`, `deleted_at`, `moderation_failed_at`, `consent_revoked_at`.
- US-S7:211 ("2 months after publication") vs 01:124 ("any edit resets") — conflict on edit-reset semantics.
- Four independent timers cannot be computed from proposed columns.

## Z12 — django-allauth contradicts one-time-code Telegram login  [DOUBTFUL]
- `02_packages.md:19` lists `django-allauth`; spec login is custom stateless OTP bound to `telegram_id` (decision H), no OAuth/social provider.
- allauth adds provider machinery conflicting with the custom flow; bloats auth surface (rule 5).
- Either use allauth Telegram provider properly or drop it and implement OTP directly.

## Z13 — Categories: django-mptt vs materialized path/level columns  [DOUBTFUL]
- `02_packages.md:4` adopts `django-mptt`; `04_db_structure.md:60–66` stores `parent_id` + `path` (`electronics.phones.apple`) + `level` as "very important for filtering".
- Maintaining both mptt `lft/rgt/tree_id` AND a manual `path` is redundant/contradictory sync hazard (rule 5).
- Pick one source of truth for category filtering.

## Z14 — EAV attribute model premature for phase 1  [DOUBTFUL]
- `04_db_structure.md:71–99` builds `category_attributes` + `ad_attribute_values` EAV.
- Spec decision D fixes a small closed admin-defined tree; US-S2 collects only title/description/price/photos/city/category — no per-category structured attributes in any US.
- Adds 2 tables + JSONB + migration complexity for zero phase-1 value (rule 5). Confirm scope or defer.

## Z15 — Tags / ad_tags semantic layer unused by any US  [DOUBTFUL]
- `04_db_structure.md:101–123` adds `tags`/`ad_tags` ("mostly automatic") feeding `search_vector`.
- No US defines tag generation; spec search (01:267–273) is title+description only.
- Auto-tagging is unspecified NLP logic — premature subsystem. Confirm scope or cut.

## Z16 — users model missing role/consent fields; custom table vs Django User  [RESPONSIBLE + DOUBTFUL]
- Decision A (01:51): moderator = admin role. US-A8 requires consent timestamps; decision K logs consent time.
- `04:25–35` has only `is_verified`; no `is_staff`/`is_superuser`/consent columns.
- Custom `users` table omits Django auth flags — must reconcile custom table vs Django User (or extend AbstractUser).

## Z17 — Account-delete / ban semantics contradictory  [RESPONSIBLE]
- US-S8 (01:226–228): on delete "all ads unpublished and deleted," but if `ads_auto_publish=False` NOT set "account is deleted" (implying if set, account retained) — backwards vs "delete my account" intent and decision F erasure.
- US-A3/A4 give "ban all ads," "block user," "delete account," but `ads.status` enum (Z01) lacks `deleted`/`rejected` and `users` lacks `is_banned`/`is_active`.
- Re-login could resurrect a banned seller. Needs user-level flag + clarified delete rule.

## Z18 — `ads.source = web` has no producer in phase 1  [DOUBTFUL]
- `04_db_structure.md:49` `source (web | telegram)`; decision B (01:58–60) scopes phase 1 to bot-only submission.
- `web` is dead until a later phase; avoid building dead branches (rule 5). Drop or justify.

## Z19 — Media storage for 500k ads × 5 photos undecided  [RESPONSIBLE]
- `03_structure.md:53` puts `media/` in repo root; spec E (01:78–85) allows up to 5 photos × 10MB → up to 2.5M files at 500k ads.
- "CDN/прокси" mentioned (01:84) but no object-storage decision.
- Millions of files under git-adjacent `media/` + Docker volumes = operational reliability risk. Need explicit backend (S3/minio).

## Z20 — Project rules (Polars / Pydantic) vs Django ORM/DRF stack conflict  [QUESTION]
- `.kilo/rules/project.md:33` mandates "ALL data processing must use Polars"; rule 9 mandates Pydantic v2 + type hints; rule 11 shares types via OpenAPI with TS frontend.
- Stack is Django ORM + DRF + django-filter + mptt + Haystack — no data-frame workload at this scale.
- Unresolved tension will cause churn. Must reconcile: where (if anywhere) Polars/Pydantic apply vs Django models/serializers.

## Z21 — Frontend form undecided: Templates+HTMX vs SPA-on-DRF  [QUESTION]
- `02_packages.md:9` and `03_structure.md:26` leave "или SPA на DRF API" open.
- Dictates whether DRF is even built in phase 1 (rule 5: don't build unused API).
- HTMX + MPA likely covers 300/day with far less surface. Decide before scaffolding.

## Z22 — Currency hard-coded EUR vs Bosnia (BAM)  [DOUBTFUL]
- `04_db_structure.md:53` `currency VARCHAR(3) DEFAULT 'EUR'`; Bosnia & Herzegovina currency is BAM (KM).
- Spec never mentions currency. Silent assumption → every price display defect. Conscious decision needed.

## Z23 — Contact-seller link requires @username but users may lack one  [RESPONSIBLE]
- Decision C (01:67): publish blocked without public username (for `t.me/@username`).
- `users.username` (04:32) is nullable; OTP login (US-S1) only binds `telegram_id`.
- No validation enforcing non-null username before publish; no handling for users who later remove username. Define enforcement point + rejected path.

## Z24 — No enum/migration/StrEnum strategy defined  [QUESTION]
- Rule 10 (StrEnum) + rule 13 (versioned migrations), but none of the docs show how `ads.status`, `ads.source`, attribute `type`, `currency` are realized (Postgres enum vs Django `TextChoices` vs `StrEnum`).
- With 500k rows + timer sweeps, status field type affects query plans + migration safety. Settle before any model written.

---

## VALIDATED SOLUTIONS (researcher ×3 + validator APPROVED per zone)

Each zone below was researched by 3 independent researchers → priority solution formed → validator APPROVED.
Spec/doc corrections have been applied to `docs/wiki/02_packages.md`, `03_structure.md`, `04_db_structure.md`,
`01_technical_specification.md` and `.kilo/rules/project.md` (rule 11).

| Zone | Verdict | Priority solution (summary) |
|------|---------|-----------------------------|
| Z20/Z12/Z21 | APPROVED | Django ORM persistence; Pydantic v2 at boundaries; Polars only >10k-row batches. DROP allauth → Login by Telegram. DEFER DRF/SPA → HTMX MPA. Rule 11 revised. |
| Z01/Z04/Z11/Z17 | APPROVED | `AdStatus` StrEnum (DRAFT, ON_MODERATION, PUBLISHED, REJECTED, ON_MODERATION_FAILED, ARCHIVED, DELETED). Reason in `ModeratorActionLog` only. Reset-on-edit timers (decision J prevails over US-S7). User flags is_banned/is_deleted/consent/deleted_at. |
| Z02/Z03/Z16 | APPROVED | `LoginToken` model, atomic single-use (telegram_id set on bot completion via shared ORM). Consent columns + idempotent sweep (30d hard-delete, 7d purge). Username OPTIONAL, NOT enforced. User extends AbstractUser (remove phone/is_verified). |
| Z05/Z08/Z09 | APPROVED | Bot = separate process + `django.setup()` + shared ORM (no DRF). aiogram 3.x. PostgreSQL FSM (SQLStorage) + 30-min sweep. Bot downloads Telegram photos and stores in OUR storage (see Z27/Z19); served via own `<img src>`. |
| Z06/Z07/Z15 | APPROVED | PostgreSQL FTS only (drop Haystack/Whoosh). `deep-translator` Bosnian→Russian at query time (fallback original). Tags deferred. |
| Z10/Z13/Z14/Z18/Z22/Z24 | APPROVED | DEFER Celery+Redis (management commands + cron). mptt-only categories (drop path/level). EAV deferred. source=telegram only. currency=BAM. TextChoices (varchar+index) for all enums. |
| **Z25 Login-by-Telegram** | APPROVED | NEW flow replacing OTP-code-paste: site shows QR/deep-link `t.me/<bot>?start=login_<token>`; user presses "Войти" in bot → bot writes `telegram_id` to `LoginToken` (shared ORM) → site logs in. `telegram_id` is the ONLY identity; username not required/used. Contact via `t.me/<bot>?start=contact_<ad_id>` (bot-mediated, anonymous). Replaces decision H, US-S1, decision C. |
| **Z26 Bot library: aiogram (phase 1) + Telethon userbot (phase 2)** | APPROVED | Owner asked: if we depend on Telethon userbot for group-scraping, why keep aiogram? Research CORRECTED the prior wrong premise: Telethon CAN run a bot account (bot-token login) and DOES serve `t.me/<bot_username>?start=` deep links — so deep links are NOT aiogram-only. However, Telethon has NO built-in FSM; the validated Z05/Z09 US-S2 dialog + PostgreSQL FSM would be hand-built (~100 LOC). **Owner rule: if the bot is harder in Telethon, choose aiogram.** => aiogram stays for phase 1 (free FSM, simpler). Telethon is reserved for the phase-2 scraping userbot (decision B: out of phase-1 scope) where userbot is mandatory and FSM doesn't matter. Docs corrected: 02_packages.md, 03_structure.md. |
| **Z19/Z27 Media storage** | APPROVED | Owner rejected the "no storage / Telegram CDN" note — CORRECT: `file_id` is NOT a URL and cannot go in `<img src>`; Telegram CDN hotlink embeds bot token + expires ~1h + no caching. **Storage is mandatory in phase 1.** Bot downloads bytes (getFile/download) → saves to OUR storage → served via own URL. Phase 1: local `MEDIA_ROOT` (Docker volume) behind nginx, wrapped in `django-storages` (abstraction `DEFAULT_FILE_STORAGE`) for later S3/R2/MinIO swap without code rewrite. `ad_images.image` stores served URL/key (ImageField); `telegram_file_id` kept as optional metadata column. Thumbnails deferred to phase 1.5. Docs corrected: 01 (decision E), 02_packages.md (django-storages + boto3 added), 03_structure.md (media/ note), 04_db_structure.md (ad_images schema). |

### Spec contradictions fixed in `01_technical_specification.md`
- Decision C (line 67): username enforcement REMOVED; contact now via bot-mediated deep link `t.me/<bot>?start=contact_<ad_id>` (anonymous, no @username needed).
- Decision F (line 90-91): consent revocation trigger (`consent_given_at`/`consent_revoked_at`) + 30-day `telegram_id` null via idempotent job.
- US-S7 (line 211): "2 месяца после публикации" → "after LAST publish/edit (reset on edit, decision J)".
- US-A11 (line 540): `rejected` vs `on_moderation_failed` are parallel terminal states with different retention; reason sourced from `ModeratorActionLog`, never shown to seller.
- Decision H + US-S1: replaced OTP-code-paste with Login-by-Telegram (QR/deep-link + bot "Войти" button); `telegram_id` is the only identity, username not required.
- Z26 (bot library): corrected 02_packages.md + 03_structure.md. **Final owner ruling:** aiogram stays for phase 1 (free built-in FSM makes the US-S2 dialog simpler than Telethon, which has no FSM — per owner rule "if bot is harder in Telethon, choose aiogram"). Telethon is reserved for the phase-2 scraping userbot (decision B). NOTE: the earlier Z26 rationale ("only aiogram can serve deep links") was WRONG — Telethon bot-mode also serves deep links; the decisive factor is FSM simplicity + owner rule, not deep-link capability.
