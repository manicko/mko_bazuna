---
id: audit-resolutions
domain: wiki
tags:
  - audit
  - decisions
  - architecture
related:
  - technical-specification
  - db-structure
  - architecture-structure
---

## Purpose

Consolidated outcome of the MVP architecture audit (zones C1–C8, R1–R9, D1–D12). Each zone passed
3× research + validation. All decisions are mirrored inline in the spec/DB docs by zone ID. This file
is the single source for **owner decisions O1–O5** and the zone-resolution summary.

## Owner Decisions (O1–O5)

| ID | Topic | Decision |
|----|-------|----------|
| **O1** (R4) | Delete / ban / publishing-ban | Three INDEPENDENT states: (1) `ads_auto_publish=False` — reversible, old ads hidden; (2) delete — soft + PII nulled after 30d; (3) ban — `telegram_id`+`username` stop-list, PURGE ads, PII NOT erased. |
| **O2** (R3) | "Decline" vs "Delete" banner | DIFFERENT states. Decline blocks login, does NOT erase, does NOT hide contact. Delete/withdraw — `consent_revoked_at` + full erasure. |
| **O3** (R1) | Erasure completeness | Full erasure: after 30d — DELETE ads (+`ad_images`), NULL `telegram_id`+`username`, SET NULL `analytics_events.user_id` and `ModeratorActionLog.user_id`. |
| **O4** (D3/D4) | Moderation criteria | 2 layers: auto (text/lengths/fields/duplicates in `moderation_criteria`) + manual admin (photos/content, future ML). No versioning. `min_text_length` removed. |
| **O5** (D1/D2) | Category search | REQUIRED (hybrid C): `ads.category_name` + `search_vector` (weight 'C') + fuzzy `category_id` detect. |

## Zone Resolution Summary

| Zone | Resolution |
|------|------------|
| **C1** | `login_tokens`: SHA-256 token_hash, two-phase atomic claim, `hmac.compare_digest`, cookie SECURE/HTTPONLY/SAMESITE=Lax. |
| **C2 / C3** | `PUBLISHED → ON_MODERATION` (text, hidden). Timers on `published_at`; `original_published_at` = audit marker. |
| **C4 / D12** | `moderation_failed_at` + 3 partial sweeps + `IX_ads_rejected_sweep` (90d) + `GinIndex`. |
| **C5 / C7** | `sync_to_async`, per-process pool, PgBouncer, migrations once. Price index after 500k EXPLAIN. deep-translator 500ms + fallback. |
| **R1** | Full erasure (O3) + `IX_users_erasure_sweep`. |
| **R2 / R3** | Contact only when PUBLISHED + telegram_id NOT NULL + not deleted/banned/withdrawn. Decline≠Withdrawal. |
| **R4** | Three states (O1). |
| **R5** | `analytics_events.user_id` SET NULL on erasure. |
| **R6 / R8** | `ad_images.image` ad-scoped + UUID v4. JPEG validation. nginx nosniff/whitelist/inline. |
| **R7** | `API_ID`/`API_HASH` removed from `.env`. |
| **R9** | BANNED keeps telegram_id; DELETED post-30d reuses row. |
| **D1 / D2** | O5. `name_i18n` JSONB ru/bs, `get_name(locale)`. |
| **D3 / D4** | O4. `moderation_criteria` 2 layers. REJECTED 90d, `rejected_at` ⊥ `moderation_failed_at`. |
| **D5 / D6** | Bot translates to Russian on create. GIN. |
| **D7 / D9 / D10** | FSM has separate migration owner; category cache; Web sync WSGI. |
| **D8** | `ModeratorActionLog`: ad_id, user_id SET NULL, action_type, reason, created_at. |
| **D11** | `currency` removed; `price` INT whole BAM. |
