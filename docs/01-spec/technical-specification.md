---
id: technical-specification
domain: spec
tags:
  - specification
  - domain
  - requirements
related:
  - db-schema
  - db-indexes
  - db-enums
  - architecture-structure
  - packages-list
  - user-stories-index
---

## Purpose

Authoritative phase-1 product & domain specification for **Mko Bazuna** — a Telegram-driven classifieds board (Avito-like) with a Django website. This is the single source of truth for product behavior. Technical implementation details live in [`../02-database/db-schema.md`](../02-database/db-schema.md), `architecture-structure.md`, and [`../03-packages/packages-list.md`](../03-packages/packages-list.md).

## Product Summary

- Sellers create ads via a **Telegram bot**; published ads appear on the website.
- Buyers browse/search/filter without registration.
- Launch geography: **Bosnia & Herzegovina**. Target languages: **Russian (content base)** + **Bosnian (UI shell)**.
- Scale targets: ~300 daily users, up to 500k ads, server response < 2s.
- Stack: Python 3.14 + Django 5.2 LTS + PostgreSQL 18 (see [`../03-packages/packages-list.md`](../03-packages/packages-list.md)).

## Fixed Domain Decisions (A–L)

Product decisions taken outside code. Each letter is referenced from other docs as "decision X".
Zone-resolution evidence (C1–C8, R1–R9, D1–D12) is distributed inline by zone ID across the domain
docs ([db-schema.md](../02-database/db-schema.md), [db-indexes.md](../02-database/db-indexes.md),
[architecture-structure.md](architecture-structure.md)). Owner decisions O1–O5 live in
[`../05-owner-decisions/index.md`](../05-owner-decisions/index.md). This file links zones rather than
repeating them.

### A. Moderation model
- Automatic check (US-A10) is the **only** automatic gate before `PUBLISHED`.
- Ads failing auto-check are kept ≤ 1 week, then deleted (`ON_MODERATION_FAILED`).
- **Moderator = admin role** (no separate moderator role).
- Moderator powers: unpublish, review failed ads, **edit moderation criteria** (US-A11), ban all of a user's ads.
- Launch with a moderator from day one.
- Seller rejection path: bot replies "ad failed moderation" + rules link; **no specific reason disclosed**.
- **ModerationCriteria has no price-range fields** (no min_price/max_price); criteria are length, count, and text-based only (zone D3/D4, US-A11, O4).

### B. Third-party group monitoring — OUT OF PHASE 1
Phase 1 accepts ads **only via our Telegram bot** (US-S2). Group/channel monitoring is a separate future phase.

### C. Seller contact & anonymity (US-B4/B5)
- **No seller identity** shown on site (no `@username`, name, or `telegram_id`).
- Only a "Contact seller" button → deep-link `https://t.me/<bot_username>?start=contact_<ad_id>`.
- Bot maps `ad_id` → seller `telegram_id` and relays, never revealing seller PII.
- Contact requires **no login** on our side; interaction moves to Telegram.
- **Button renders on site ONLY if** ad is `PUBLISHED` AND seller `telegram_id` NOT NULL AND seller NOT `is_deleted`/`is_banned` and consent NOT revoked.
- `username` is NOT required for publishing or contact.

### D. Geography & categories (US-B6/B7, US-A7)
- Launch geography: Bosnia & Herzegovina. Languages: Russian + Bosnian (latin).
- **City:** seller picks from a preset closed list of Bosnia/Herzegovina cities. Unrecognized city → "general / no city", not searchable by city.
- **Categories are NOT user-defined.** Closed tree set by admin (django-mptt is the single source of truth). Bot suggests top 3–5 by keyword, requires explicit seller confirmation. Free-text as new category is **rejected**; choice only from suggested or full tree.
- i18n names (zone D2): `name` in Russian; Bosnian in `name_i18n` JSONB — see column detail in [db-schema.md](../02-database/db-schema.md). UI uses `get_name(locale)` with Russian fallback.
- **Category-name search is REQUIRED in phase 1 (zone D1 / O5, hybrid C):** `category_name` is denormalized into `ads.category_name` and included in `search_vector` (weight 'C') + app-level fuzzy detect (`difflib`) sets `category_id` filter for single-word queries. Bosnian query is translated to Russian before search, so it matches the Russian category name.
- Preset tree (recommendation):
  - **Goods:** Electronics, Clothing, Children, Furniture, Tools, Sport, Books, Other
  - **Services:** Repair, Translation, Tutors, Courses, Beauty, Transport, Freelance, Other
  - **Real Estate:** Apartments, Houses, Rooms, Commercial, Parking, Other

### E. Photos & moderation (US-S2, US-A10)
- **1 to 5 photos** per ad.
- Only **compressed Telegram photos** accepted (`message.photo`); `message.document` with `image/*` is rejected.
- Format: JPEG (Telegram-converted). Limit: up to 2560px long side, ~2 MB/photo; ≤ 5 photos / 10 MB per ad.
- Phase-1 moderation is **text-only** (US-A10). Bad photos removed manually by moderator (incl. account ban).
- **No server-side photo optimization in phase 1** — accept Telegram-compressed images, store in our storage (decision E-storage), serve as-is.
- **Storage (E-storage):** phase 1 = local `MEDIA_ROOT` (Docker volume) behind nginx via Django `FileSystemStorage` (the `STORAGES` contract). `django-storages` deferred to S3/R2/MinIO swap (YAGNI); later swap = add `django-storages`+`boto3` + one `STORAGES` line, no code rewrite.
- **Thumbnails:** phase 1 serves full-size compressed photos; Pillow thumbnail generation deferred to phase 1.5.

### F. PII & consent (US-A8)
- Jurisdiction: Bosnia & Herzegovina (GDPR-equivalent). Collect minimum: `telegram_id`, optional `username`.
- Users are maximally anonymous; nothing beyond Telegram login is stored.
- **Privacy policy / Terms required from launch** (visible to buyers without login).
- **Two distinct consent states (zone R3, decision K):** DECLINE (browse-only, no erasure) ≠ WITHDRAW (`consent_revoked_at` → soft-delete + 30-day PII erasure). Banner behavior in decision K.
- **Post-withdrawal erasure:** soft-delete immediately (`is_deleted=True`, `deleted_at=now`) + full PII erasure exactly **30 days** after `consent_revoked_at` (idempotent task, zone R1; index `IX_users_erasure_sweep`):
  - NULL `telegram_id` + `username`; DELETE user's ad rows (+ `ad_images`)
  - SET NULL `analytics_events.user_id` (aggregates kept) and `ModeratorActionLog.user_id` (reason/admin/timestamp kept for audit)
- Failed-check logs auto-purged after 7 days (separate sweep, zone D12).

### K. Consent banner & privacy behavior (zone R3, see O2)
- Browse before consent: buyer freely views published ads before accepting the banner.
- **DECLINE = browse-only:** blocks only seller login/actions. `consent_revoked_at` NOT set, no erasure, external "Contact seller" keeps working.
- **WITHDRAW/delete = WITHDRAW:** sets `consent_revoked_at`, triggers soft-delete + 30-day PII erasure (decision F). NOT the same as "decline".
- After accept, banner stays hidden on return.
- Site banner consent covers all PII processing including the bot; **no separate bot confirmation** required.
- Consent acceptance time recorded; withdrawal/deletion per decision F.

### G. Content language, search, city match (US-B2/B3/B7, US-B9)
- **Content stored in Russian.** UI language switch (ru/bs-latin) translates only the site shell; ad text is shown translated on display.
- **Search (phase 1) is over Russian content.** Bosnian query is translated to Russian at search time (query-translation). Results optionally tagged "translated from Russian".
- **Stored-content-invariant (zone D5):** seller may input in Bosnian/Russian, but the bot MUST translate title+description to Russian on ad creation (reuses `deep-translator` + request cache) so `to_tsvector('russian', …)` is correct. Bosnian UI translates back on display.
- **Result sorting:** buyer chooses — by date (newest first) or by price.
- **City match is exact** against the closed preset list. Unrecognized city → "general / no city", not searchable.
- **City typos:** show "did you mean" suggestion via `difflib.get_close_matches` (no separate fuzzy lib needed for MVP).
- **Empty results:** friendly "nothing found" with a suggestion to broaden filters.

### H. Telegram login behavior (US-S1)
- Site "Login via Telegram" button opens a QR / code page.
- QR encodes deep-link `https://t.me/<bot_username>?start=login_<token>` (32-char URL-safe token, generated on site).
- Completion: user taps "Login" in bot → bot writes sender `telegram_id` into `LoginToken` via shared ORM → site checks token readiness and authenticates by `telegram_id` (create/find).
- Expired/invalid token: clear message + retry path. No silent failures.
- **Session:** persistent cookie, survives browser restart until explicit logout or long idle.
- Re-login reuses existing `telegram_id` (no duplicate account). Token is atomic, one-time, constant-time compare (`select_for_update`).

### I. Bot ad-creation dialog (US-S2)
- Strictly step-by-step, one field at a time: category → city → title → description → price (if applicable) → photos, each confirmed.
- Category: closed admin tree; bot suggests top 3–5; free-text-as-new-category rejected.
- Photos: 1–5 mandatory, **Telegram-compressed only**; document/file upload rejected with clear message; cannot publish without ≥1 photo.
- Preview before send; seller can fix mismatches (incl. city/category mapping).
- Abandoned draft auto-deleted on idle timeout (e.g. 30 min). No partial ads saved.

### J. Ad lifecycle & re-moderation (US-S5, US-S7, decision A)
- **Edits requiring re-moderation:** text edits (title/description) return ad to `ON_MODERATION` (`PUBLISHED → ON_MODERATION`, zone C2). Price/photo edits publish immediately.
- **Visibility on re-check:** ad pulled from public site immediately until it passes.
- **Archive/delete timers count from `published_at` (zone C3):** `published_at` updates on EVERY transition to `PUBLISHED` (incl. reactivation, price/photo edits) — this is the "timer reset on edit". `original_published_at` is a separate IMMUTABLE first-publish marker for audit only (does NOT drive sweep).
- **Reactivation:** seller can reactivate `ARCHIVED` ad from dashboard; re-publishes (text re-checked).
- **Independent timers:** failed-auto-check deletion (1 week, decision A, `moderation_failed_at`) and consent-withdrawal hard-delete (30 days, decision F) are separate from the archive/delete timers above.

### L. Usage analytics (phase 1)
- **Web traffic:** Plausible (cookieless, <1KB JS, EU-hosted SaaS) — JS snippet only, no Python dep, no consent banner needed (legitimate interest). Fallback: self-host Plausible CE / Umami via Docker.
- **Product metrics:** internal `AnalyticsEvent` model — `event_type` (StrEnum: `REGISTRATION_CREATED`, `AD_PUBLISHED`, `SEARCH_PERFORMED`, `CONTACT_INITIATED`), `timestamp`, optional `user_id`. Aggregated via ORM; admin/CLI `show_metrics` access.
- Privacy: Plausible collects no PII; mention traffic measurement in privacy policy. `user_id` references already-collected `telegram_id`.

## Functional Stories by Role

Full user stories (acceptance behavior per role) are the single source of truth in
[../04-user-stories/index.md](../04-user-stories/index.md):

- [Seller stories](../04-user-stories/seller-stories.md) — US-S1, S2, S5, S6, S7, S8, S9
- [Buyer stories](../04-user-stories/buyer-stories.md) — US-B1–B9
- [Admin stories](../04-user-stories/admin-stories.md) — US-A1–A11

## Owner Decisions (O1–O5)

Owner-level decisions are **owned by the product owner** and recorded in plain, owner-readable
language in [`../05-owner-decisions/index.md`](../05-owner-decisions/index.md) (single source of
truth). That file holds the full Decision / Technical-consequence split; this spec only links to it to
avoid duplicating owner decisions.

Each owner decision maps to one or more audit zones resolved inline above and in the database docs:

| Owner decision | Resolves audit zone(s) |
|----------------|------------------------|
| **O1** — turn-off-posting vs. delete vs. ban | R4 |
| **O2** — decline banner ≠ delete account | R3 |
| **O3** — full erasure 30 days after account deletion | R1 |
| **O4** — automated + manual moderation criteria | D3 / D4 |
| **O5** — category-name search in phase 1 | D1 / D2 |

### Account State Separation (O1/R4)

Phase 3 introduces three distinct account states that must not be conflated (zone R4):

| State | Field | Effect | Reversible | Phase 3 Implementation |
|-------|-------|--------|-----------|------------------------|
| **Publish restriction** | `ads_auto_publish = False` | Bot rejects NEW ads; existing ads hidden from public while active | Yes | Toggle via dashboard or admin; no deletion triggered |
| **Account ban** | `is_banned = True` | Blocks login and ALL ad actions; `telegram_id`/`username` retained for enforcement | Yes (admin unban) | Admin sets via `/admin/users/` |
| **Account deletion** | `is_deleted = True`, `consent_revoked_at = now()` | Triggers immediate soft-delete cascade + 30-day hard delete (Phase 4) | No | `telegram_id`/`username` nulled immediately; Phase 4 sweep handles final erasure |