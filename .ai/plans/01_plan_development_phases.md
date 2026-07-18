# Development Roadmap: Django Telegram-Classifieds MVP

> **Methodology:** Vertical slices deliver working functionality early. Phases minimize coupling.  
> **Rules:** StrEnum constants (rule 10), small modules, migrations, English docs.

---

## Phase 1. Minimal Publish-to-Discover Flow
**Goal:** End-to-end: seller → bot → ad → auto-publish → appears on site.

**Deliverables:**
- `src/backend/config/`, `src/backend/apps/` with core/, users/, ads/, categories/, locations/, moderation/, analytics/
- Enums: `AdStatus`, `AdSource`, `AnalyticsEventType`, `ModeratorActionType` in `apps/core/enums.py`
- Models: User (is_banned, is_deleted, ads_auto_publish, consent_*), `login_tokens` standalone table (token_hash SHA-256, atomic claim), Ad (category_name sync, search_vector trigger), AdImage, ModeratorActionLog, ModerationCriteria, AnalyticsEvent
- Triggers: `sync_category_name()`, `update_search_vector()` (PostgreSQL)
- Indexes: `IX_ads_pub_listing`, `IX_ads_search_gin`, `IX_users_erasure_sweep`, `IX_ads_purge_failed`, `IX_ads_rejected_sweep`
- Telegram bot: aiogram 3.x FSM (category → city → title → description → price → photos → preview), login via `/start login_<token>`
- Settings: TLS-ready (`SESSION_COOKIE_SECURE`, `SECURE_SSL_REDIRECT`), psycopg[binary]>=3.2.0
- docker-compose: db, web, bot, nginx; `media_volume` shared

**Doc updates:** `docs/wiki/01_technical_specification.md`, `docs/wiki/02_packages.md`, `docs/wiki/03_structure.md`, `docs/wiki/04_db_structure.md`

---

## Phase 2. Moderation System
**Goal:** Auto + manual ad review with audit logging.

**Deliverables:**
- `ModerationCriteria` singleton (admin-editable thresholds)
- `ModeratorActionLog` populated (auto-fail + manual reject)
- Admin UI: review failed queue, reject with reason (TEXT), ban user (is_banned=True)
- `purge_failed_ads` management command (7 days)
- Auto-moderation: length checks, banned words, photo count, user ad limit
- Status: ON_MODERATION → PUBLISHED (auto) or ON_MODERATION_FAILED (auto) or REJECTED (manual)

**Doc updates:** `docs/wiki/01_technical_specification.md`, `docs/wiki/04_db_structure.md`

---

## Phase 3. Buyer Contact + Seller Dashboard
**Goal:** Anonymous contact + full seller account lifecycle.

**Deliverables:**
- Contact deep-link: `t.me/<bot>?start=contact_<uuid>` → anonymous bridge
- Seller dashboard: list by status, edit flow (price/photos immediate, text → re-moderation)
- **Account states separated (O1/R4):**
  - `is_banned=True`: no login/publish, PII kept, admin can unban
  - `is_deleted=True` + `consent_revoked_at`: 30-day hard delete (telegram_id nulled)
  - `ads_auto_publish=False`: cannot create new ads, existing ads unaffected
- Archive: 2-month auto-archive, reactivate (text re-checked)
- `consent_hard_delete` job: 30 days after withdrawal

**Doc updates:** `docs/wiki/01_technical_specification.md`, `docs/wiki/04_db_structure.md`

---

## Phase 4. Analytics + Production Hardening
**Goal:** Usage metrics + deployment ready.

**Deliverables:**
- Plausible cookieless JS snippet (EU endpoint)
- `AnalyticsEvent` created on registration/publish/search/contact
- Background jobs: archive_sweep (2 mo), delete_sweep (4 mo), purge_failed_ads (7 days), consent_hard_delete (30 days)
- nginx: `X-Content-Type-Options: nosniff`, script execution blocked, rate limiting
- CI: ruff + basedpyright config

**Doc updates:** `docs/wiki/01_technical_specification.md`, `docs/wiki/03_structure.md`

---

## Phase 5. Scraping Service + UI Translation
**Goal:** Third-party monitoring + Bosnian interface.

**Deliverables:**
- `telegram_message_id` column added to `ads` (Phase 5 migration)
- `scraping_service/`: Telethon MTProto monitors groups, writes via shared ORM
- UI: RU/BOS switcher, `name_i18n` display, query translation (Bosnian → Russian)
- Content invariant confirmed: stored content is Russian, UI may translate

**Doc updates:** `docs/wiki/01_technical_specification.md`, `docs/wiki/02_packages.md`, `docs/wiki/03_structure.md`, `docs/wiki/04_db_structure.md`

---

## Dependency Graph
```
Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5
           └─────┬─────┘
                 ↓
          Vertical slices complete
```

---
## Deferred / Out-of-MVP Scope (per audit F4)

The following spec items are acknowledged but not implemented in the current plan set:
- **US-S6 (seller deletes own ad via dashboard)** — Soft-delete status exists; seller self-delete feature to be added in post-MVP.
- **US-B8 (responsive layout)** — Relies on Tailwind CSS/daisyUI defaults; specific mobile AC to be verified in implementation.
- **US-A6 (inactive-user purge)** — Deferred to post-MVP; no idle detection/deletion in phase set.
- **US-A9 (system-log/event admin view)** — P4 T1 analytics dashboard covers product metrics; explicit system-event log view deferred.
- **US-A7 (explicit admin cat/city management task)** — Implied via Django admin interface in P1 T3/T11; no dedicated task needed for MVP.