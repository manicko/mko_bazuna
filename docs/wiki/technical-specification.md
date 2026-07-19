---
id: technical-specification
domain: wiki
tags:
  - specification
  - domain
  - requirements
related:
  - db-structure
  - architecture-structure
  - packages
  - audit-resolutions
---

## Purpose

Authoritative phase-1 product & domain specification for **Mko Bazuna** — a Telegram-driven
classifieds board (Avito-like) with a Django website. This is the single source of truth for
product behavior. Technical implementation details live in `db-structure.md`, `architecture-structure.md`,
and `packages.md`.

## Product Summary

- Sellers create ads via a **Telegram bot**; published ads appear on the website.
- Buyers browse/search/filter without registration.
- Launch geography: **Bosnia & Herzegovina**. Target languages: **Russian (content base)** + **Bosnian (UI shell)**.
- Scale targets: ~300 daily users, up to 500k ads, server response < 2s.
- Stack: Python 3.14 + Django 5.2 LTS + PostgreSQL 18 (see `packages.md`).

## Fixed Domain Decisions (A–L)

These are product decisions taken outside code. Each letter is referenced from other docs as "decision X".

### A. Moderation model
- Automatic check (US-A10) is the **only** automatic gate before `PUBLISHED`.
- Ads failing auto-check are kept ≤ 1 week, then deleted (`ON_MODERATION_FAILED`).
- **Moderator = admin role** (no separate moderator role).
- Moderator powers: unpublish, review failed ads, **edit moderation criteria** (US-A11), ban all of a user's ads.
- Launch with a moderator from day one.
- Seller rejection path: bot replies "ad failed moderation" + rules link; **no specific reason disclosed**.

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
- i18n names (zone D2): base `name` in Russian; Bosnian in `name_i18n` (JSONB `{"ru","bs"}`). UI uses `get_name(locale)` with Russian fallback.
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
- **Two distinct consent states (zone R3):**
  - **DECLINE (browse-only, decision K):** banner "Decline" only blocks seller login/actions. `consent_given_at` stays NULL, `consent_revoked_at` NOT set — no deletion/erase; "Contact seller" keeps working.
  - **WITHDRAW (account deletion, decision F):** sets `consent_revoked_at` and triggers soft-delete immediately. The ONLY state that triggers cascade erasure.
- **Post-withdrawal erasure:** soft-delete immediately (`is_deleted=True`, `deleted_at=now`) + full PII erasure exactly **30 days** after `consent_revoked_at` (idempotent background task, zone R1; index `IX_users_erasure_sweep` on users):
  - NULL `telegram_id` and `username`
  - DELETE user's ad rows (+ `ad_images`)
  - SET NULL `analytics_events.user_id` (aggregates kept)
  - SET NULL `ModeratorActionLog.user_id` (reason/admin/timestamp kept for audit)
- Failed-check logs auto-purged after 7 days (separate sweep, zone D12).

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

### K. Consent banner & privacy behavior (decision F)
- Browse before consent: buyer freely views published ads before accepting banner.
- **Decline = DECLINE (browse-only, zone R3):** blocks only seller login/actions. `consent_revoked_at` NOT set, no erasure. External "Contact seller" (`t.me/<bot_username>?start=contact_<ad_id>`) keeps working.
- **Withdraw/delete = WITHDRAW:** sets `consent_revoked_at`, triggers soft-delete + 30-day PII erasure (decision F). NOT the same as "decline".
- After accept, banner stays hidden on return.
- Site banner consent covers all PII processing including the bot; **no separate bot confirmation** required.
- Logging: consent acceptance time recorded; withdrawal/deletion per decision F.

### L. Usage analytics (phase 1)
- **Web traffic:** Plausible (cookieless, <1KB JS, EU-hosted SaaS) — JS snippet only, no Python dep, no consent banner needed (legitimate interest). Fallback: self-host Plausible CE / Umami via Docker.
- **Product metrics:** internal `AnalyticsEvent` model — `event_type` (StrEnum: `REGISTRATION_CREATED`, `AD_PUBLISHED`, `SEARCH_PERFORMED`, `CONTACT_INITIATED`), `timestamp`, optional `user_id`. Aggregated via ORM; admin/CLI `show_metrics` access.
- Privacy: Plausible collects no PII; mention traffic measurement in privacy policy. `user_id` references already-collected `telegram_id`.

## Functional Stories by Role

### Seller
- **US-S1** Login & Telegram binding (see decision H).
- **US-S2** Create ad via bot (see decision I); on submit → `ON_MODERATION`, not visible until checks pass. Multi-ad posts out of scope.
- **US-S5** Edit ad: description/price/photos; text edits → `PUBLISHED → ON_MODERATION` + immediate hide (zone C2); mixed edit follows text rule. Updated within ≤5s for instant price/photo edits.
- **US-S6** Delete own ad → `DELETED` (soft), hidden from site.
- **US-S7** Auto-archive: 2 months after last publish/edit → `ARCHIVED`; 4 months → permanently removed. Seller sees archived ads in dashboard.
- **US-S8** Delete account: confirm on site; ads soft-deleted; `telegram_id`/`username` nulled exactly 30 days after `consent_revoked_at` (decision F / zone R1). NOT tied to `ads_auto_publish` flag (US-S9). Re-registration only after 30-day null (zone R9).
- **US-S9** Publishing ban: `ads_auto_publish=False` blocks new ads, hides old ads (not deleted); reversible, independent of account deletion/ban.

### Buyer
- **US-B1** Browse without registration (status `PUBLISHED`).
- **US-B2** Search by keyword over title+description, `PUBLISHED` only, ≤2s. Sort by date/price. Bosnian query translated to Russian. Friendly empty state.
- **US-B3** Filter by category/subcategory/city/price range; combinable; no full reload. Exact city match + "did you mean".
- **US-B4** Ad card shows full details + "Contact seller" only (no seller identity).
- **US-B5** Contact via deep-link to our bot (decision C); seller contact never shown in plaintext.
- **US-B6** Browse by category (hierarchy supported).
- **US-B7** Browse by city; exact match; "did you mean" on typos; city saved in session.
- **US-B8** Responsive (mobile/tablet/desktop).
- **US-B9** Multilingual UI switch (ru / bs-latin), persisted across sessions.

### Admin
- **US-A1** Admin auth (separate login or Telegram with confirmed role); unauthorized attempts logged.
- **US-A2** List all ads (ID, title, category, city, status, published date); filter by status/category/city/date.
- **US-A3** Moderate: unpublish, delete, change status, ban all of a user's ads; actions instant + logged.
- **US-A4** Manage users: block/unblock/delete; blocked user cannot post but may browse.
- **US-A5** Auto-remove stale ads (archive@2mo, delete@4mo); logged.
- **US-A6** Delete inactive users (configurable threshold); deactivates their ads.
- **US-A7** Manage categories & cities (add/edit/deactivate; used entities not deletable).
- **US-A8** Manage consent: view fact, revoke (triggers decision F flow).
- **US-A9** View system logs/events (admin-only); filter by type/date.
- **US-A10** Automatic ad check at submit against `moderation_criteria` (see decision O4); on fail → `ON_MODERATION_FAILED` + bot message (no reason). On pass → `PUBLISHED` within ≤5s.
- **US-A11** View failed/rejected lists + edit `moderation_criteria` at runtime; manual photo review (Layer 2) with categories logged to `ModeratorActionLog` (never shown to seller).
