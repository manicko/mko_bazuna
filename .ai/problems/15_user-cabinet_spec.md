# Specification: Unified User Cabinet — Favorites, Saved-Search Alerts & Search History

**File:** `15_user-cabinet_spec.md`
**Status:** Final (ready for implementation planning)
**Date:** 2026-08-18
**Source Decision:** `.ai/problems/Decision_017.md`
**Research:**
- `docs/99-agent/alert-delivery-research.md` (near-real-time alert delivery — Approach 1 recommended)
- `docs/99-agent/alert-unsubscribe-research.md` (Telegram inline callback unsubscribe + deep-link)
- `docs/99-agent/anonymous-history-research.md` (session-scoped anonymous search history)
- `docs/99-agent/favorites-cabinet-research.md` (AdFavorite + HTMX toggle + lightweight cabinet hub)

---

## 1. Problem Statement

Mko Bazuna models its authenticated area around a **"Seller cabinet"** concept. The
product owner (Decision_017) wants to abandon that mental model in favor of a
single unified **User Cabinet**, because one account acts as both buyer and seller
("today searches for a flat → buyer; tomorrow posts a bicycle → seller"). The
cabinet must group ad management, favorites, saved searches, search history, and
settings under one authenticated hub, and it must add two net-new buyer features:

- **US-B11 — Saved search alerts.** A buyer saves a search (query + optional
  city/category/price). When a new matching ad is published, the buyer is
  notified. The same ad must not trigger multiple alerts for the same saved
  search (deduplication). Notifications are delivered via **Telegram**.
- **US-B12 — Search history.** The buyer's recent queries are remembered and
  surfaced as autocomplete suggestions on return visits, deduplicated and capped
  at 50 per user. **Anonymous users also receive search history suggestions
  (session-scoped).**

The PO also added **Favorites** (❤️), explicitly split **"delete search"** from
**"disable notifications"**, and mandated Telegram-native **unsubscribe**
(inline callback button, deep-link as a secondary mechanism) in addition to
cabinet-based management of subscriptions.

### Root causes / gaps (verified against codebase)

| # | Gap | Evidence |
|---|-----|----------|
| G1 | **No favorite entity or any favorites UI** (model, heart toggle, list) | No `Favorite`/`AdFavorite` anywhere in `apps/`; no `AD_FAVORITED` in `apps/core/enums.py` |
| G2 | **No unified cabinet** — ad management is isolated at `/dashboard/`; no hub/section navigation; "Сохраненные поиски"/"Избранное"/"История поиска"/"Настройки" not present | Only `/dashboard/` exists (`apps/ads/urls.py:20`); header links to Dashboard only |
| G3 | **Saved-search web UI is dead** — modal scaffolded but not wired, and no create/list/edit/disable/delete views | `save_search_modal.html` references `search:save-search`/`search:list`; `apps/search/urls.py` has only `search/` + `autocomplete` |
| G4 | **Anonymous search history is a no-op** | `search_history.py:31-32` returns early on `user_id is None`; `search.py:128` gates on `is_authenticated`; `autocomplete.py:62` returns `[]` for anonymous |
| G5 | **Alerts are daily-digest only** (PO Q5 → near-real-time on publish) | `send_alerts.py` is a daily cron command; no publish-time trigger |
| G6 | **No Telegram unsubscribe** — alert messages are plain text with no inline action; no per-search tokens; `SavedSearch` has no `unsubscribe_token`/`updated_at`/`last_notified_at`; no `SITE_URL` for absolute ad links | `send_alerts.py:182-195`; `search/models.py`; Django `Signer` incompatible with deep-link charset (verified) |

---

## 2. Confirmed Requirements & Facts

### 2.1 Facts (verified against codebase)

- **F1.** `SavedSearch` model exists (`apps/search/models.py:47-113`) with `user`,
  `query`, `city`, `category`, `min_price`, `max_price`, `is_active`, `language`,
  `created_at`. It has **no** `updated_at`, `last_notified_at`, or
  `unsubscribe_token`.
- **F2.** `SavedSearchNotification` (`models.py:115-151`) with
  `UniqueConstraint(saved_search, ad)` (`uq_saved_search_ad`) provides built-in
  dedup; `record_notifications(..., ignore_conflicts=True)` is idempotent.
- **F3.** `alert_query.py` provides `find_matching_ads` (saved-search-centric,
  per-language FTS via `LanguageLocale.fts_vector_field`) and `record_notifications`.
  It has **no ad-centric matcher** ("which saved searches match ad X?").
- **F4.** Daily `send_alerts.py` command runs 08:00 UTC (`entrypoint-scheduler.sh:40`),
  advisory-lock gated, filters `is_active=True`, sends Telegram digest outside the
  transaction via `asyncio.run(Bot(settings.BOT_TOKEN))`. `User.chat_id` is the
  stable recipient identifier (`users/models.py:42`); `telegram_id` is nullable
  (GDPR-nulled) — never use it for bot lookups.
- **F5.** All publish paths converge on `Ad.transition_to(PUBLISHED)`
  (`ads/models.py:307`, commit at `:432-433`, `published_at` set at `:381`).
  `apps/moderation/signals.py:32` already uses `post_save(sender=Ad)` — the
  established side-effect idiom.
- **F6.** Django sessions active with default `db` backend (2-week expiry), already
  used for `django_language`. `transaction.on_commit` is unused today.
- **F7.** No task broker (no Celery/RQ); Redis is cache-only. Two processes
  (web gunicorn sync ×3 + bot aiogram) share one DB/Redis.
- **F8.** Telegram deep-link `/start` payload max 64 chars, charset
  `[A-Za-z0-9_-]`. Django `Signer` separator is verified **incompatible** with
  that charset → a custom opaque token is required.
- **F9.** No `SITE_URL`/`SITE_ID`/`django.contrib.sites`; `Ad` has no
  `get_absolute_url` → absolute ad URLs in Telegram need a new setting.
- **F10.** `@login_required` issues a 302 that htmx follows blindly → favorite
  toggle endpoints must do manual auth checks, not `@login_required`.
- **F11.** Project uses `{% include %}` component pattern (header,
  consent_banner, language_switcher); no `base.html`/`{% extends %}`.

### 2.2 Confirmed Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| CR1 | Add `AdFavorite` model (user, ad, created_at; `UniqueConstraint(user, ad)`, index) + migration | Must |
| CR2 | Favorites are authenticated-only. A guest tapping ♡ sees a "Войдите, чтобы сохранить" prompt linking to `/login/issue/` (no guest favorites) | Must |
| CR3 | Instant `♡↔♥` toggle via HTMX (no reload) on listing cards and ad detail | Must |
| CR4 | Favorites list page under the cabinet reusing the ad-card partial, with empty state and remove action | Must |
| CR5 | "🔔 Сохранить поиск" button on search results opens the (existing) modal captured from the current query + city + category + price; POST creates the saved search (with the user's `LANGUAGE_CODE`) | Must |
| CR6 | Saved-search management in the cabinet: list with per-search **enable/disable** (is_active), **edit**, and **delete** (delete ≠ disable) | Must |
| CR7 | `SavedSearch` gains `updated_at`, `last_notified_at`, and `unsubscribe_token` (opaque) | Must |
| CR8 | Alerts fire **near-real-time at ad publish** (post_save PUBLISHED → `transaction.on_commit` → ad-centric match → Telegram send in a background thread); the daily command remains as catch-all/backfill | Must |
| CR9 | Each immediate Telegram alert shows the ad (title, city, price) + `[Посмотреть объявление]` (absolute URL via new `SITE_URL`) + `[🔕 Отключить этот поиск]` inline callback button | Must |
| CR10 | Unsubscribe works from Telegram: callback validates the saving user owns the search, sets `is_active=False`, edits the message button to "enable again"; deep-link `/start` is the secondary mechanism | Must |
| CR11 | Anonymous search history: session-scoped, deduplicated, capped at 50, surfaced in the autocomplete | Must |
| CR12 | "История поиска" cabinet section (authenticated only): list + "clear history" action | Must |
| CR13 | Lightweight cabinet hub `/cabinet/` + shared section nav; `/cabinet/favorites/`, `/cabinet/saved-searches/`, `/cabinet/search-history/`, `/cabinet/settings/` (stub); "Мои объявления" links to existing `/dashboard/` (no refactor) | Must |
| CR14 | Shared header shows the cabinet entry for authenticated users; new `apps/cabinet` app with FBVs + URLs mounted in `config/urls.py` | Must |
| CR15 | `settings.IMMEDIATE_ALERTS_ENABLED` guards the new publish-time delivery path (safe rollout) | Should |
| CR16 | Settings page is a **stub placeholder** this phase (Q9=A); language preference remains on the user/profile; per-search notification control lives in "Сохраненные поиски" | Must |
| CR17 | The dead `save_search_modal.html` is wired to a working `search:save-search` URL | Must |

### 2.3 Product Owner Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **D1 — Scope** (Q1) | **(B)** This spec = Favorites + anonymous search history + saved-search web create/manage, inside a lightweight cabinet hub. "Настройки" and deep `/dashboard/` refactor deferred | Smaller testable increments; favorites/anonymous history are net-new, cabinet is mostly navigation |
| **D2 — Guest favorites** (Q2) | **(A)** Prompt/redirect to login; no guest favorites | Matches «Favorite на MVP — только авторизованным» |
| **D3 — Toggle UX** (Q3) | **(A)** Instant HTMX toggle, no reload, no confirm | Best UX |
| **D4 — Saved-search creation** (Q4) | **(A)** "Сохранить поиск" on results → pre-filled modal; manage in cabinet | One entry point, captures current filters |
| **D5 — Alert cadence** (Q5) | **(B) Near-real-time on publish** | Replaces daily digest as primary (daily remains as backfill) |
| **D6 — Anonymous history** (Q6) | **(A)** Session-scoped, dedup, cap 50, autocomplete | Matches US-B12 |
| **D7 — History section** (Q7) | **(A)** Visible cabinet list + clear action | Beyond autocomplete |
| **D8 — Notifications/settings UX** (Q8) | **(A + mandatory extension)** Telegram-only; **no in-web inbox**; plus cabinet control of each search's subscription AND **unsubscribe from Telegram itself** (callback button + `/start` deep-link fallback) | PO: «нужно выключить из кабинета, отписаться из Telegram, продумать отписку» |
| **D9 — Delete vs. disable** | **Split** — "Delete search" removes the search; "Disable notifications" just toggles `is_active` (search stays saved) | User may want to temporarily pause alerting |
| **D10 — SavedSearch model** | Add `updated_at`, `last_notified_at`, `unsubscribe_token`; keep existing `is_active`, `language`, `min_price`/`max_price` (existing names retained over the informal `price_min`/`price_max`) | PO-specified fields; existing column names kept to avoid churn |
| **D11 — Settings scope** (Q9) | **(A refined)** Full settings page deferred; language stored on profile; per-search notification toggle within "Сохраненные поиски"; Settings = stub | «Полноценная страница настроек откладывается» |
| **D12 — Cabinet URLs** (Q10) | **(A)** Lightweight hub: `/cabinet/`, `/cabinet/favorites/`, `/cabinet/saved-searches/`; reuse existing `/dashboard/` (renamed in nav, no refactor) | «Не требуется переделывать /dashboard/» |

### 2.4 Resolved Questions

| Question | Resolution |
|----------|-----------|
| Q1 — Scope batching | (B) phased; this spec covers favorites, anonymous history, saved-search web flow, lightweight hub |
| Q2 — Guest favorite | (A) login prompt |
| Q3 — Toggle | (A) instant HTMX |
| Q4 — Save-search entry | (A) results modal |
| Q5 — Cadence | (B) near-real-time on publish (+ daily backfill) |
| Q6 — Anonymous history | (A) session-scoped |
| Q7 — History section | (A) list + clear |
| Q8 — Notifications | (A) Telegram-only + cabinet control + Telegram unsubscribe (callback + deep-link) |
| Q9 — Settings | (A) stub; per-search toggles in saved-searches |
| Q10 — Cabinet URLs | (A) lightweight hub, reuse /dashboard/ |

---

## 3. Conceptual Development Tasks

| # | Task | Purpose | Expected Outcome | Dependencies | Effort |
|---|------|---------|------------------|--------------|--------|
| T1 | Extend `SavedSearch` model + migration (`updated_at`, `last_notified_at`, `unsubscribe_token`) | Durable audit + opaque unsubscribe identity | Migration; fields on model; `unsubscribe_token` server-generated opaque value | None | LOW |
| T2 | Add `AdFavorite` model + migration | Persist favorites with dedup | Model (user/ad/created_at, `UniqueConstraint(user,ad)`, index, `db_table="ad_favorites"`); migration | None | LOW |
| T3 | Add `SITE_URL` setting + `Ad.get_absolute_url` | Absolute ad links in Telegram | New `SITE_URL` env-driven setting; `get_absolute_url` on Ad | None | LOW |
| T4 | Favorite toggle: shared `components/favorite_heart.html`, POST view with manual auth gate, `login_prompt.html` fragment | ♡↔♥ via HTMX with guest gate | Heart on cards + detail; toggle endpoint (no `@login_required`; returns prompt for guests / swapped heart for authed); global `hx-headers` for CSRF | T2 | MED |
| T5 | Favorites list view + `/cabinet/favorites/` page (reuse `ad_list` partial, empty state, remove) | Cabinet favorites section | View + template + URL; queries `Ad.objects.filter(favorites__user=user)` | T4, T10 | MED |
| T6 | Saved-search create view + `search:save-search` URL + wire `save_search_modal.html` | Make save-search live | Create view persists filters + `LANGUAGE_CODE`; modal resolved | T1 | MED |
| T7 | Saved-search management views (list/enable-disable/edit/delete) + `/cabinet/saved-searches/` | Cabinet subscription management | CRUD views + URL + template with per-search toggle/edit/delete (delete ≠ disable) | T6, T10 | MED |
| T8 | Near-real-time alert delivery: `post_save(PUBLISHED)` → `transaction.on_commit` → ad-centric matcher → background-thread Telegram send | Alerts at publish | `deliver_immediate_alerts(ad_id)` ad-centric matcher in `alert_query.py`; signal in `moderation/signals.py`; `settings.IMMEDIATE_ALERTS_ENABLED`; semaphore-capped send | T3 | MED–HIGH |
| T9 | Telegram alert message + inline callback unsubscribe | Unsubscribe in chat | `_format_digest`/new per-ad message builder with `[Посмотреть объявление]` + `[🔕 Отключить этот поиск]` (unsub token); callback handler validates ownership, sets `is_active=False`, `edit_reply_markup` swap; deep-link `/start` branch (via login delegation); register router in bot + test conftest | T8, T1, T3 | MED |
| T10 | Anonymous session search history: extend `record_search_history`/`get_user_search_history` with session path; update `search.py` + `autocomplete.py`; update 4 tests | US-B12 anonymous history | Session-backed history (cap 50, dedup) surfaced in autocomplete | None | LOW–MED |
| T11 | Cabinet "История поиска" view + clear + `/cabinet/search-history/` | Authenticated history section | List + POST clear; template reusing `header.html` pattern | T10, T12 | LOW |
| T12 | New `apps/cabinet` app: hub `/cabinet/`, `components/cabinet_nav.html`, header link, section routes, settings stub | Lightweight cabinet hub | App with FBVs + urls mounted in `config/urls.py`; sections wired; "Мои объявления" → existing `/dashboard/` | T5, T7, T11 | MED |
| T13 | Tests + docs | Regression + documentation | Tests for favorites toggle/gate, saved-search CRUD, immediate alert dedup, Telegram unsubscribe, anonymous history; update `01-spec`/user-stories/architecture docs + migrations | T1–T12 | MED |

**Critical path:** T1 → T6 → T7 → T12; T2 → T4 → T5 → T12; T8 → T9; T10 → T11 → T12.

---

## 4. Data Model Design

### AdFavorite (new)
```
user       FK -> users.User      related_name="favorites"
ad         FK -> ads.Ad          related_name="favorites"
created_at DateTime(auto_now_add)
Meta: db_table="ad_favorites"
      UniqueConstraint(fields=["user","ad"], name="uq_user_ad_favorite")
      Index(fields=["user_id", "-created_at"])
```

### SavedSearch (extended)
```
+ updated_at          DateTime(auto_now=True)                 # D9/D10
+ last_notified_at    DateTime(null=True)                     # "last time this search produced a notification"
+ unsubscribe_token   CharField(unique, opaque, 32-40 chars)  # server-generated opaque value (D8/D10)
  (existing fields kept: user, query, city, category, min_price, max_price,
   is_active, language, created_at)
```

---

## 5. Research Summary

- **R1 — Near-real-time delivery (`alert-delivery-research.md`).** All publish paths
  funnel through `Ad.transition_to(PUBLISHED)` (`models.py:432-433`). Recommended:
  `post_save(Ad)` on PUBLISHED → `transaction.on_commit(...)` → new **ad-centric**
  matcher → send via `asyncio.run(Bot(...))` in a daemon thread
  (`asyncio.Semaphore(10)` cap). Idempotent via `uq_saved_search_ad`
  (`ignore_conflicts`), so the daily command never double-sends and acts as the
  backfill/retry for failed immediate sends. Rejected: sub-minute polling (lag +
  load) and hand-rolled coroutine (re-introduces the commit race).
- **R2 — Telegram unsubscribe (`alert-unsubscribe-research.md`).** Django `Signer`
  is **verified incompatible** with the 64-char `[A-Za-z0-9_-]` deep-link charset
  (every Telegram-legal separator char is Django-"unsafe"). Store an **opaque
  `unsubscribe_token`** on `SavedSearch`; inline `callback_data="unsub:<hex>"`
  (~41 B, within 64 B); handler looks up by token, verifies the pressing user owns
  the search (`User` via stable `chat_id`), sets `is_active=False`, and edits the
  reply markup to swap the button to "Включить уведомления". Deep-link `/start`
  branch mirrors the existing `login`/`contact` delegation. Requires new `SITE_URL`
  for absolute ad-detail links.
- **R3 — Anonymous history (`anonymous-history-research.md`).** Use the **Django
  `db` session store** (its 2-week expiry doubles as the privacy retention policy) —
  no migration, no new table, no sweep. Extend the two service functions with an
  optional `session` path used when `user_id is None`; autocomplete passes
  `request.session`. Update the 4 tests asserting the old no-op.
- **R4 — Favorites + cabinet (`favorites-cabinet-research.md`).** `AdFavorite` in
  `apps/ads/models.py` following `SavedSearch` conventions; shared
  `components/favorite_heart.html` include; toggle view must **not** use
  `@login_required` (htmx blindly follows 302) — manual auth check returns a
  `login_prompt` fragment for guests; global `<body hx-headers>` for CSRF (no
  htmx-POST-CSRF precedent exists). New `apps/cabinet` app (FBV + urls) hosting
  hub + sections, reusing `header.html` and a shared `cabinet_nav.html`; favorites
  list reuses `ad_list.html` by selecting `Ad` instances. Defer any new analytics
  event (no consumer yet).

---

## 6. Assumptions

| # | Assumption | Confidence |
|---|-----------|------------|
| A1 | Telegram remains the sole auth channel; no web registration form | HIGH (decision H, spec 12) |
| A2 | The Telegram bot process and web process share the ORM; `post_save(PUBLISHED)` fires in whichever process commits (bot for auto-publish, web for admin approve) — both are valid delivery points; dedup makes overlap safe | HIGH |
| A3 | Near-real-time = **one message per matching ad** per user (per the PO's example message); the consolidated daily digest is retained only as the backfill format | MED — message format confirmed by PO example |
| A4 | `user.chat_id` (stable, never nullified) is the recipient identifier; users without `chat_id` get no alerts (logged and skipped) | HIGH (R2) |
| A5 | The daily `send_alerts` command stays as-is (catch-all/backfill) and is not deleted | HIGH (R1) |
| A6 | Anonymous search history lives in the session store; it is **not** merged into the account on login (PO explicitly deferred) | HIGH (R3/D6) |
| A7 | The new `apps/cabinet` app is the right granularity for a single-responsibility hub | MED (R4) |
| A8 | No new favorites analytics event is added this phase (no consumer yet) | MED (R4) |
| A9 | Existing `min_price`/`max_price` column names are retained (PO's `price_min`/`price_max` treated as informal) | MED (D10) |

---

## 7. Constraints

- **C1.** Two processes (web gunicorn sync + bot aiogram), one DB, one Redis (cache-only). Migrations run exactly once before both start. No new long-running service/broker.
- **C2.** HTMX MPA with `{% include %}` components (no base.html/`{% extends %}`); favor function-based views.
- **C3.** All fixed values use `StrEnum`; no plain-string constants; follow existing patterns, no overengineering.
- **C4.** `@login_required`-redirect + htmx tension: favorite/auth-gated HTMX endpoints use manual auth checks returning fragments, not `@login_required` 302s.
- **C5.** Telegram deep-link `/start` payload ≤ 64 chars, charset `[A-Za-z0-9_-]`; callback_data ≤ 64 bytes. No Django `Signer` for deep-link payloads (use opaque tokens).
- **C6.** English-only code/comments/docstrings/logs; no `print()` — use `logging`.
- **C7.** No third-party auth packages; Telegram deep-link + Django auth only.
- **C8.** Idempotency for alert delivery dictated by `uq_saved_search_ad` + `ignore_conflicts`; the daily command must never double-send.
- **C9.** /dashboard/ is **not** refactored in this spec (Q10=A). "Мои объявления" is a nav link to it.
- **C10.** `SITE_URL` setting must be added (env-driven) for absolute ad links; `Ad.get_absolute_url` new.

---

## 8. Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|-----------|
| R1 | Publish-time send blocks the sync request/worker thread | MED | MED | Background daemon thread around `asyncio.run(...)`; `IMMEDIATE_ALERTS_ENABLED` gate |
| R2 | Telegram rate limits / fan-out on popular ads | LOW | LOW | `asyncio.Semaphore(10)`; rely on dedup; daily backfill catches failures |
| R3 | Double/missed alerts across processes | LOW | MED | `on_commit` ordering + `uq_saved_search_ad`/`ignore_conflicts`; daily backfill |
| R4 | Ad-centric FTS scan perf over many saved searches | LOW–MED | MED | Gate setting; reuse `IX_saved_searches_user_active`; benchmark before enabling |
| R5 | Leaked/forwarded Telegram message or deep link in wrong hands | LOW | HIGH | Opaque token (not raw id); always verify pressing user owns the search server-side |
| R6 | htmx POST CSRF (no existing precedent) | MED | MED | Global `<body hx-headers>{"X-CSRFToken": ...}`; set on the relevant templates |
| R7 | `@login_required` 302 breaking htmx favorites for guests | HIGH | MED | Manual auth check; return `login_prompt.html` fragment (no 302) |
| R8 | Dead `save_search_modal.html` references non-existent URLs | MED | MED | T6 wires `search:save-search`; remove/redirect stale `search:list` ref |
| R9 | Tests assert old anonymous-history no-op | MED | LOW | Update tests per project rule #2 (production over tests) |
| R10 | Missing `SITE_URL` in dev/test breaks absolute links | MED | LOW | Default in dev settings; `.env` template updated |

---

## 9. Open Questions

| # | Question | Status |
|---|----------|--------|
| Q1 | Should immediate near-real-time alerts be one message **per matching ad** (confirmed by PO example) — consolidated per-user immediate digest also considered | Resolved: per-ad message (A3) — confirm during implementation |
| Q2 | Should admin/manual `approve_ad` publishes also fan out immediately, or only bot auto-publishes? | Resolved (research): all paths run through `set_published`→`transition_to(PUBLISHED)` uniformly; no special-casing (R1 §3.6) |
| Q3 | Should the daily `send_alerts` backfill cadence change (e.g., more frequent than daily)? | Deferred — kept at daily this phase (R1 §3.4) |
| Q4 | Deep-link unsubscribe: should the `/start` branch also present a "run search now"/list-others UI, or only the unsubscribe result? | Open — minimal (unsubscribe result + re-enable hint) recommended; confirm during planning |

---

## 10. Out of Scope

1. **In-web notifications inbox** (Q8=A) — Telegram-only; `SavedSearchNotification` stays an internal dedup ledger.
2. **Full "Настройки" page** (Q9=A) — stub placeholder only this phase.
3. **Deep refactor of `/dashboard/`** into `/cabinet/` (Q10=A) — "Мои объявления" is a nav link now.
4. **Bulk ad actions, inbox messaging, wallets, promotions, ratings, lead management, storefronts, scheduling/reactivate-timer** (all Phase 2–5; see `12_seller-cabinet_spec.md` §4.2).
5. **Migrating anonymous history to the account on login** (PO explicitly deferred).
6. **New favorites/analytics event** (`AD_FAVORITED`) — deferred until a dashboard consumes it (R4).
7. **Guest session favorites** (Q2=A) — rejected.
8. **Buyer/Seller role split** — deliberately rejected (single User persona).

---

## 11. Definition of Ready

A task is ready when all of the following hold:

1. **T1/T2/Migrations:** new columns/models applied cleanly on empty + populated DBs; `unsubscribe_token` unique; `uq_user_ad_favorite` enforced.
2. **T3:** `SITE_URL` set in base+prod+.env templates; `Ad.get_absolute_url` returns a working absolute URL.
3. **T4/T5:** guests see the login prompt (no 302) and cannot favorite; authenticated toggle works via HTMX with CSRF; favorites list page renders ads + empty state + remove.
4. **T6/T7:** `search:save-search` and `search:list` resolve; modal creates a saved search with filters + `LANGUAGE_CODE`; cabinet management lists toggles/edit/delete with delete ≠ disable.
5. **T8:** a published ad matching an active saved search produces a Telegram message near-real-time; re-running publish/command does not double-send (`uq_saved_search_ad`); `IMMEDIATE_ALERTS_ENABLED` gate works; daily command still backfills failed sends.
6. **T9:** alert message has `[Посмотреть объявление]` (absolute URL) + `[🔕 Отключить этот поиск]`; callback verifies ownership, flips `is_active`, swaps markup; `/start` deep-link branch works; router registered in bot + test conftest.
7. **T10/T11:** anonymous users get deduped, capped-50 session history in autocomplete; authenticated history section lists + clears.
8. **T12:** `/cabinet/` hub + section routes live under a new `apps/cabinet` app; shared `cabinet_nav.html`; "Мои объявления" → `/dashboard/` (unchanged); shared header shows cabinet link for authenticated users.
9. **T13:** tests pass via the Docker `test` service (`docker compose ... run --rm test`), `ruff`/`basedpyright` clean; docs (`01-spec`, user stories, architecture) updated.
10. Scope boundary respected: no in-web inbox, no full settings page, no /dashboard/ refactor, no guest favorites, no admin-auth change.

---

*Specification produced from Decision_017 and four Researcher reports. All 10 PO questions resolved (D1–D12 captured).*
