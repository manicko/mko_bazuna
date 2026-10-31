---
id: api-surface
domain: spec
tags:
  - api
  - specification
  - agent-reference
related:
  - architecture-structure
  - spec-index
  - technical-specification
---

# Mko Bazuna — JSON API Surface (`/api/v1/`)

> **Single source of truth for the JSON API surface.** This file is the authoritative
> specification for `/api/v1/` — endpoint inventory, auth categories, error taxonomy,
> rate-limit budgets, i18n rules and per-action stances. It supersedes the earlier
> single-consumer framing ("DRF deferred" / "JSON API deliberately not built").
> OpenAPI is deliberately deferred (**D2**), so this document — not a generated schema — is
> the contract. Layout and the mechanical import rule are stated in
> [`architecture-structure.md`](architecture-structure.md#api-surface-contract).

## Purpose

Specify the multi-consumer, machine-readable JSON API exposed at the `/api/v1/` prefix, so that
every user-facing action is reachable programmatically (rule 18 / Agent-First parity) using the
same business logic as the HTMX/MPA site and the Telegram bot.

## Main Concepts

- **Style (D1):** plain Django JSON views + Pydantic `BaseInputModel` DTOs, following the shipped
  `apps/moderation/api_bulk.py` precedent. **No DRF, no django-ninja.**
- **Mount:** `config/urls.py` → `path("api/v1/", include("apps.api.urls"))`; `apps/api/urls.py`
  is a URL-only aggregator (no views/services/models imports; `apps/api` is not in `INSTALLED_APPS`).
- **Routes:** per-app `<app>/api_urls.py` with `app_name = "<app>_api"`; API views under
  `apps/<app>/views/api/…` (single-module apps use one-off modules: `apps/categories/api_tree.py`,
  `apps/locations/api_cities.py`).
- **Writes:** POST-only (`@require_POST` idiom); no PUT/PATCH/DELETE in v1.
- **Errors:** RFC 9457 problem documents (`application/problem+json`) via
  `apps/core/utils/problem.py`.
- **Serialization (D4):** per-app `_serialize_*` helpers inside API view modules; services keep
  returning ORM objects (the service contract is unchanged).
- **Audience parity (D5):** public reads reuse the same `account_state_q` predicate as the HTML
  surface, so visibility matches by construction.

## Status legend

Every endpoint row below carries a **Status**:

- **planned** — not yet shipped; the row is the design contract for a later task.
- **covered/frozen** — behavior exists today and is **not** changed by this program (its shape is
  frozen).

Each endpoint task **appends/updates its row here as it ships** (see *Change log / row status* at
the end). Rows are currently `planned` except for the ones marked `covered/frozen`.

## Endpoint inventory

Auth categories: **PUB** = anonymous + `account_state_q` audience; **SESS** = `login_required_api`
(session cookie); **STAFF** = `staff_required_api`. Pagination envelope:
`{page, per_page, total_count, results_truncated, results[], has_next}`; `total_count` may be
`SEARCH_CACHE_MAX_HITS + 1` on a truncated search — `results_truncated` is the authoritative signal
(O-2b).

| # | Action | Service | Endpoint · Method | Auth | Error notes | Status |
|---|---|---|---|---|---|---|
| 1 | Listings | `ListingsQuery.build_queryset` / `build_listings_context` | `GET /api/v1/ads/` | PUB | 422; 429 problem (§Errors) | shipped (S1.3) |
| 2 | FTS search | `apps/search/services/fts.py` (S1.1) | `GET /api/v1/search/?q&category&city&min_price&max_price&listing_purpose&condition&features&sort&page&all_categories` | PUB | fuzzy / did-you-mean / narrowed fields; cap semantics; 429 problem | shipped (S1.4) |
| 3 | Ad detail | audience predicate + serialize | `GET /api/v1/ads/{id}/` | PUB | uniform 404; `AD_VIEWED` recorded | shipped (S1.5) |
| 4 | Autocomplete | (existing) | unchanged `/api/search/autocomplete` | PUB | stance: not aliased; legacy 429 `{"error":"rate_limit"}` | covered/frozen |
| 5 | Create/publish | `create_draft_ad` + `submit_ad` | `POST /api/v1/ads/{id}/submit/` (existing DRAFT; dialog/photo staging bot-only) | SESS (consent via outcome) | `SubmitAdOutcome` map (§Errors) | planned |
| 6 | Edit | edit-flow helper (S4.2) — five branches | `POST /api/v1/ads/{id}/edit/` | SESS + owner | refusal → 409 `not_editable` (HTML renders 200+form — deliberate machine mapping); price-only and direct-save stay distinct from `submit_ad` | planned |
| 7 | Archive | lifecycle service (S4.1) | `POST /api/v1/ads/{id}/archive/` | SESS + owner + **consent** | 403 `consent_required`; 409 | planned |
| 8 | Reactivate | lifecycle service (S4.1), same `auto_moderate` decision | `POST /api/v1/ads/{id}/reactivate/` | SESS + owner + consent | 200 outcome; 409; 503 lock-timeout | planned |
| 9 | Delete | lifecycle service (S4.1) — gate-free | `POST /api/v1/ads/{id}/delete/` | SESS + owner | 204 | planned |
| 10 | Copy | `copy_ad` (`copy_service.py:39` via `_build_ad_copy:15`) | `POST /api/v1/ads/{id}/copy/` | SESS | 200 `{ad_id}` — new DRAFT owned by seller; max-ads + consent predicates as in the bot flow | planned |
| 11 | Dashboard reads | dashboard grouping (S2.2) + `SellerStats` | `GET /api/v1/dashboard/?time_range=` | SESS + consent | **403 `consent_required` when consent absent — never an empty list** (R-L1) | shipped (S2.3) |
| 12 | Moderation queue/review | `PriorityService.get_queued_ads` / `get_priority_counts` | `GET /api/v1/moderation/queue/?priority&page`, `GET /api/v1/moderation/review/{id}/` | STAFF | 401 / 403 / 405 (problem docs) | shipped (S2.5) |
| 13 | Single actions | `admin_actions.approve_ad/reject_ad/ban_user_for_ad` | `POST /api/v1/moderation/{approve,reject,ban}/{id}/` | STAFF | §Errors mappings | planned |
| 14 | Bulk | (existing) — **frozen shape** | unchanged `/moderation/api/v1/bulk-action/` | STAFF | no change | covered/frozen |
| 15 | Favorites | extend `apps/ads/services/favorites.py` (list + toggle) | `GET /api/v1/favorites/` (shipped S2.4) · `POST /api/v1/favorites/{ad_id}/toggle/` | SESS | 200 `{active,count}`; uniform 404 | partial: list shipped (S2.4) |
| 16 | Saved-search CRUD | `apps/search/services/saved_searches.py` (S3.1) on shared `SavedSearchInput` | `GET/POST /api/v1/saved-searches/`, `POST …/{pk}/{toggle,edit,delete}/` | SESS | 422; uniform 404 | partial: list shipped (S2.7) |
| 17 | Alert delivery | `send_alerts` + services | unchanged (bot digest + scheduler) | — | stance: no HTTP endpoint; agent-visible substitute is `SavedSearchNotification.delivered_at` (read via `verify_parity`/shell tier) | covered/frozen |
| 18 | Search history list/clear | `search_history` service | `GET /api/v1/search-history/` · `POST /api/v1/search-history/clear/` | **SESS** (HTML mirrors are `@login_required`; anon session history is only reachable via autocomplete #4) | 204 clear | partial: list shipped (S2.7) |
| 19 | Preferred-city | (existing) | unchanged `/api/preferred-city/` | anon + consent cookie | stance: not aliased; **no rate limiter exists** | covered/frozen |
| 20 | Consent | `give/decline/withdraw_consent` | `POST /api/v1/consent/{accept,decline,withdraw}/` | accept/decline anon-allowed (HTML parity); withdraw SESS | cookie quartet stays HTML; withdraw still `logout()`s | planned |
| 21 | Login issue/status | `issue/consume_token` (predicates frozen) | **No new endpoint** — `/login/status/` is the machine contract (200/204/410); GET-issuance gap owned by phase 15 | anon | uniform 410, anti-enumeration | planned |
| 22 | Logout | Django `logout` | `POST /api/v1/auth/logout/` | SESS | 204 | planned |
| 23 | Contact seller | bot-only by design | deep-link protocol — detail payload carries the `t.me` link | — | stance: no HTTP endpoint | covered/frozen |
| 24 | Support ticket | bot writer only (06-PII-101) | in-process callable; no HTTP intake in v1 | — | stance: bot-only support intake | covered/frozen |
| 25 | Language | shared middleware | `?lang` works identically on `/api/v1/` URLs; bot `/language` untouched | — | locale parity by construction | planned |
| 26 | Media | `media_gate` | unchanged; **URLs only** in payloads | — | binary protocol | covered/frozen |
| 27 | Ops/metrics | `core/views` | unchanged; deliberately no `/api/v1/` index endpoint (D2) | — | — | covered/frozen |
| 28 | Admin actions | `admin_actions` | unchanged staff-web | — | — | covered/frozen |
| 29 | Category tree read | `Category` models (direct; **no** fragment cache) | `GET /api/v1/categories/` | PUB | full active tree (`{categories:[{slug,name,children}]}`); 429 problem | shipped (S1.6) |
| 30 | Cities read | `City` models (header city query) | `GET /api/v1/cities/` | PUB | `{cities:[{slug,name,region,country_code}]}`, `order_by("name")`; 429 problem | shipped (S1.6) |
| 31 | Seller trust dashboard | `trust_analytics` (`calculate_seller_trust_score` / `get_seller_daily_metrics` / `get_trust_level`) + `seller_stats.SellerStats` | `GET /api/v1/trust/seller/` | SESS | 401 problem (no challenge); 405 | shipped (S2.6) |
| 32 | Moderation trust dashboard | `moderation_analytics` (`get_moderation_stats` / `get_pending_queue_size` / `get_moderator_performance` / `get_rejection_reasons`) | `GET /api/v1/trust/moderation/` | STAFF | 401 / 403 / 405 problem docs (no challenge) | shipped (S2.6) |

## Auth model

| Category | Enforcement | Notes |
|---|---|---|
| **PUB** | anonymous allowed; audience predicate `account_state_q` applied | visibility identical to the HTML surface (withdrawn/banned sellers invisible) |
| **SESS** | `login_required_api` (mirror of `staff_required_api`) | 401 problem document; **no `WWW-Authenticate` challenge** (no bearer scheme exists) |
| **STAFF** | `staff_required_api` (unchanged) | 401 problem document; identity is checked before the method |

- **Sessions are the only credential.** No new auth scheme; the Django session cookie is the sole
  non-staff credential. There is no bearer token, no API key, no secret header (a settings-gated
  secret header is a *contingency only* if a concrete out-of-process writer need ever appears).
- **Writes are POST-only** (`@require_POST`).
- **No CSRF exemption.** API writes follow the standard CSRF contract; browserless tests exercise
  them through Django `Client()`.
- **Browserless testing (D3):** headless verification rides Django `Client()` (CSRF disabled in
  pytest), never a new auth scheme.

## Error taxonomy (RFC 9457)

All `/api/v1/` errors are RFC 9457 problem documents with content-type
`application/problem+json`, built by `apps/core/utils/problem.py`, which extends the existing
`pydantic_errors_json` deposit (`apps/core/utils/sanitize.py:295`).

| Outcome | HTTP + `type` | Notes |
|---|---|---|
| `SubmitAdOutcome.PUBLISHED` / `MODERATION_FAILED` | 200 `{outcome}` | boundary rule (O-2a): 4xx only when the request committed NO state change; `MODERATION_FAILED` parks the ad — a terminal, well-formed outcome (bulk precedent `api_bulk.py:116-122`) |
| `SubmitAdOutcome.CONSENT_REQUIRED` | 403 `consent_required` | same predicate (`can_create_ad`) as the UI |
| `INVALID_TRANSITION` / `DRAFT_GONE` / `PHOTO_UNAVAILABLE` | 409 `invalid_transition` / `draft_gone` / `photo_unavailable` | state-machine family |
| Edit refusal (status outside editable/affordance sets) | 409 `not_editable` | deliberate delta from HTML 200+form — documented (auditor A5) |
| `ApproveOutcome.PUBLISHED` / `CRITERIA_REJECTED` | 200 `{outcome}` / 200 `{outcome:"criteria_rejected"}` | ad parked `ON_MODERATION_FAILED` |
| `ApproveOutcome.TRANSITION_REFUSED` | 409 `transition_refused` | |
| `BanResult` changed ≥ 1 | 200 counts (`changed` / `already_in_state`) | ban idempotent for agents |
| Ban refused (self / privileged) | 403 `ban_refused` | no privileged-row count leak |
| `ConsumeOutcome` (status contract doc only) | 200 / 204 pending / 410 uniform | `not_found` / `gone` / `unbound` / `lost_race` collapse to one problem (anti-enumeration) |
| DTO validation | 422 `validation_failed`, `errors = pydantic_errors_json(exc)` | `api_bulk` precedent |
| 429 on `/api/v1/` (R1) | 429 `rate_limited` problem + `Retry-After` (derived from `RateLimitBudget.period` in `problem.py`) | new surface; legacy surfaces are unchanged and keep emitting NO `Retry-After` (`rate_limit_response.py` is a pure formatter; `retry_after` is caller-supplied and production never passes it) |
| Legacy 429 shapes (frozen) | listings/detail = bare 429 (`json=False`); media gate = its own variant; search/autocomplete = `{"error":"rate_limit"}` | preferred-city has **no** limiter at all |

**Both 429 realities.**

1. **New `/api/v1/`:** a single RFC 9457 `rate_limited` problem with a `Retry-After` header derived
   from the budget's period.
2. **Legacy (frozen, unchanged):** listings/detail emit a bare `429` (no JSON body, `json=False`);
   the media gate emits its own variant; search/autocomplete emit `{"error":"rate_limit"}`;
   preferred-city has no limiter. Legacy 429s carry **no** `Retry-After` today (`rate_limit_response.py`
   is a pure formatter and production never supplies a `retry_after`).

**Generic status mapping.** Malformed request » 400 · unauthenticated » 401 (no `WWW-Authenticate`)
· non-owner / no-consent » 403 · missing-or-invisible » 404 (uniform) · wrong method » 405 ·
lock-timeout (PostgreSQL `55P03`) » 503 `retryable` · unexpected » 500 (generic body; CWE-209
discipline). HTML-vs-API shape differences (edit: HTML 200+form vs API 409; reactivation
lock-timeout: HTML already 503 via middleware) are documented here deliberately.

**Other response contract clauses.** Content-Type is **lenient** (the body is parsed as JSON
regardless of the header — the `api_bulk.py:74` norm; if strictness is ever added it is one shared
415 in `problem.py`, never per-view). `Retry-After` is the only contractual rate-limit header (no
`X-RateLimit-*`). `/api/v1/` reads are **uncacheable by default** (no `Vary` / `Cache-Control`
contract yet — this guards against future locale-merging caches). Analytics side effects (below)
are agent-visible behavior.

**Ordering contract (deterministic ties — R2).** Every plain-listings ordering applies `-id` as a
final tiebreaker (`ListingsQuery._apply_sort`), so ads that share a sort key (`published_at` or
`price_normalized_eur`, including the NULL-price group) have a total, deterministic order and page
boundaries inside a tied group can neither reorder nor duplicate rows. This is the **single
approved ordering delta** of the API-parity program and it lives in the shared service, so it
applies **identically to the HTML listings surface and to `GET /api/v1/ads/`** (HTML == JSON). The
FTS search path (`apps/search/services/fts.py`) carries its own `-rank, … , -id` ordering and is
**not** affected by this change: relevance always ranks first and the tiebreaker never reorders
across different relevance values.

## Rate-limit budgets

Budgets are `RateLimitBudget` StrEnum members (`apps/core/enums.py`); the numbers live in the enum
property dicts, never in environment variables. The shared `rate_limit_check` + `RateLimitBudget`
mechanism remains the single enforcement point (R1); only the *rendering* of the 429 differs on
`/api/v1/`.

| Budget | Limit | Namespaces | Notes |
|---|---|---|---|
| `API_PUBLIC_READ` | 60 req / 60 s | per-route namespaces `api_listings`, `api_search`, `api_detail`, `api_categories`, `api_cities` | **shipped** (S0.5) |
| `API_WRITE` | 30 req / 60 s | shared `api_write` | **shipped** (S0.5) |

## i18n rules

- `type` is a **stable ASCII token** and is **never translated** (it is part of the machine
  contract).
- `detail` is an **English msgid** cataloged in the `ru` / `bs` / `en` message catalogs (non-empty
  for `ru`/`bs`; `en` may be empty because the msgid is English).
- Locale is resolved via the **shared middleware chain** — `?lang` > `lang_pref` cookie >
  `Accept-Language` — with **no per-view locale code**. `?lang` works identically on `/api/v1/`
  URLs as on HTML URLs.

## Planned stances

Stances for actions that are deliberately **not** given a new HTTP endpoint or that have a
non-obvious machine contract (plan §2.4 rows 4, 17, 19, 21–28 and §2.3/§5):

- **#4 autocomplete — not aliased.** The existing `/api/search/autocomplete` JSON endpoint stays
  as-is (legacy `{"error":"rate_limit"}` 429 shape frozen). It is not re-mounted under `/api/v1/`.
- **#17 alert delivery — bot + scheduler only, no HTTP endpoint.** The agent-visible substitute is
  the delivery receipt `SavedSearchNotification.delivered_at`, readable through `verify_parity` or
  the shell tier.
- **#19 preferred-city — not aliased.** The existing `/api/preferred-city/` endpoint stays; it is
  the one JSON route with **no rate limiter**.
- **#21 login — machine contract, no new endpoint.** `/login/status/` is documented as the machine
  contract (200 issued / 204 pending / 410 uniform). The GET-issuance gap is owned by phase 15.
- **#23 contact seller — deep-link protocol.** Bot-only by design (seller anonymity); the ad-detail
  payload carries the `t.me` deep link, and there is no HTTP contact endpoint.
- **#24 support ticket — bot-only intake.** The bot handler is the only writer (06-PII-101 signed
  identity); v1 exposes an in-process callable, not an HTTP intake.
- **#25 `?lang` parity.** Language selection is provided by the shared middleware on both HTML and
  API URLs; the bot `/language` flow is untouched. No per-route locale code.
- **#26 media — URLs only.** Media access stays the binary nginx `X-Accel`-gated protocol; payloads
  carry media URLs only, never bytes.
- **#27 ops/metrics — no index endpoint (D2).** Ops health/metrics endpoints are unchanged, and
  there is deliberately **no** `GET /api/v1/` index/discovery endpoint (docs are the ratified D2
  default; an index is a deferred optional item).
- **#28 admin actions — unchanged staff-web.** The Django admin action surface (the 4th consumer of
  `admin_actions`) is unchanged.
- **#1–#3, #11, #12 — HTML-only reads that gain JSON parity** by this program: listings, search, ad
  detail, dashboard, moderation queue/review (plus the S2.6 trust/analytics dashboards, favorites
  list #15, saved-searches list #16, search history #18).

## Analytics side effects (agent-visible)

API reads record analytics **identically** to their HTML mirrors: ad detail records `AD_VIEWED`;
search records `SEARCH_PERFORMED` plus popular-search and search-history entries. There is **no**
`track=` opt-out in v1 (deferred with a documented trigger). Verification loops that must avoid
side effects should use the service tier or the `verify_parity` command (the poll-safe tier).

## Change log / row status

- **Every endpoint task appends or updates its own row** in the *Endpoint inventory* table (and,
  where applicable, adds its pairing row to `apps/api/tests/test_import_rule.py`) **in the same
  task that ships it** (§4.4 DoD: "api-surface.md row + import-rule pairing row updated in the same
  stage").
- All rows are therefore **`planned`** at the time this skeleton lands, except the
  **`covered/frozen`** rows (#4 autocomplete, #14 bulk, #19 preferred-city, #26 media, #27 ops,
  #28 admin), which describe already-shipped behavior that this program does not change.
- **This file is finalized at S5.3** (docs close-out): all rows become `shipped`/`stanced`,
  the compliance section is recorded, and the dual-429, five-branch-edit and lock-timeout
  HTML-shape differences are confirmed.
- **S0.2:** `/api/v1/` mounted; URL-only aggregator + import-rule harness shipped (no endpoints yet).
- **S0.3:** RFC 9457 problem helper shipped — `apps/core/utils/problem.py` (`problem`, `validation_problem`,
  `rate_limited_problem`) plus `apps/core/tests/test_problem_response.py`. Every §Errors outcome family is
  constructible; the helper mints `application/problem+json` documents with a stable ASCII `type`. The
  `Retry-After` header is derived here from `RateLimitBudget.period`. The legacy 429 renderer
  (`rate_limit_response.py`) is **untouched** — legacy 429s carry **no** `Retry-After`; only `/api/v1/`
  adds it (R1).
- **S0.4:** session-auth decorator shipped — `apps/core/utils/api_auth.py` (`login_required_api`) plus
  `apps/core/tests/test_api_auth.py`. Anonymous requests are refused with a 401 `unauthenticated`
  problem document and **no** `WWW-Authenticate` header; identity is checked before the method
  (anonymous `POST` → 401, not 405), mirroring `staff_required_api` exactly (phase 15 owns any reorder).
- **S0.5:** `RateLimitBudget.API_PUBLIC_READ` (60 req / 60 s) and `RateLimitBudget.API_WRITE`
  (30 req / 60 s) shipped as StrEnum members in `apps/core/enums.py`; pins extended in
  `apps/core/tests/test_rate_limit_budget.py`. Numbers live in the enum property dicts — no env vars.
- **S1.1:** the FTS search pipeline is extracted verbatim from `apps/search/views/search.py` into
  `apps/search/services/fts.py` (endpoint #2's service, "planned" above). The one approved
  de-coupling is the explicit `LanguageLocale` parameter (locale resolved once from
  `request.LANGUAGE_CODE` in the view and threaded down); vectors are accessed only via
  `LanguageLocale.fts_vector_field` / `LanguageLocale.fts_config`. The view is now a thin caller and
  the pre-existing search suites pass unmodified (regression proof). `alert_query.py`,
  `apps/search/services/__init__.py` and the rate-limit entry block are untouched
  (`apps/search/tests/test_fts_service.py` adds the service-tier coverage).
- **S1.2:** the shared listings sort gained a final `-id` tiebreaker on every branch of
  `ListingsQuery._apply_sort` (**R2** — the single approved ordering delta of this program). Equal
  sort keys now order deterministically, so a page boundary inside a tied group can neither reorder
  nor duplicate rows; the change is in the shared service, so HTML listings and `GET /api/v1/ads/`
  gain it from one place (HTML == JSON). The FTS search path keeps its own rank-first
  `-rank, …, -id` ordering and is unaffected — relevance ranking stays rank-first and the tiebreaker
  never reorders across different relevance values
  (`apps/ads/tests/test_relevance_tiebreaker.py` pins this). See the *Ordering contract* clause in
  §"Other response contract clauses".
- **S1.3:** `GET /api/v1/ads/` shipped (endpoint row #1 → `shipped`). New
  `apps/ads/api_urls.py` (`app_name="ads_api"`, one route `""` → `listings`), `apps/ads/views/api/`
  (`__init__`, `listings.py` with `_serialize_ad`), and the aggregator include in `apps/api/urls.py`.
  The endpoint mirrors the HTML listings view 1:1 (same `category`/`city`/`listing_purpose`/
  `condition`/`features`/`min_price`/`max_price`/`sort`/`page`/`per_page` GET dimensions) and calls
  the **same** `ListingsQuery`/`build_listings_context` service tier, so audience parity
  (`account_state_q`) and ordering (the R2 `-id` tiebreaker) hold by construction. Pagination
  envelope `{page, per_page, total_count, results_truncated, results[], has_next}`. Errors: 422
  `validation_failed` via `validation_problem`; 429 `rate_limited` problem + `Retry-After` via
  `rate_limit_check(namespace="api_listings", budget=API_PUBLIC_READ)` + `rate_limited_problem`. The
  HTML listings view is **untouched** (zero diff). Pairing row
  `("apps.ads.views.api.listings", "apps.ads.views.listings")` registered in
  `apps/api/tests/test_import_rule.py`; the shared rate-limit seam
  `apps.search.services.rate_limit` is added to that harness's ALLOWLIST (it is the mandated
  `/api/v1/` enforcement point and is not imported by the HTML mirror). Tests:
  `apps/ads/tests/test_listings_api.py` (incl. `TestExhaustiveFilterSortPageMatrix` — the rule-18
  matrix owner — audience parity, 429/422 problems, HTML/JSON parity incl. warm-cache, and the
  pagination envelope).
- **S1.4:** `GET /api/v1/search/` shipped (endpoint row #2 → `shipped`). New
  `apps/search/api_urls.py` (`app_name="search_api"`, one route `""` → `search`),
  `apps/search/views/api/` (`__init__`, `search.py` with `_serialize_ad`) and the aggregator
  include in `apps/api/urls.py` (route `/api/v1/search/`). The endpoint mirrors the HTML search
  view 1:1 (same `q`/`category`/`city`/`min_price`/`max_price`/`listing_purpose`/`condition`/
  `features`/`sort`/`page`/`all_categories` GET dimensions; `city` is documented-accepted while the
  real filter city comes from the middleware-resolved `request.current_city`; **`per_page` is fixed
  at 24 — `ListingsQuery.PER_PAGE` — exactly like the HTML search view**) and calls the **same**
  `apps.search.services.fts` pipeline + shared cache + `ListingsQuery`/`build_listings_context`
  service tier, so audience parity (`account_state_q`), ordering and the cache-hit rank restore
  (`_rank_cache_hit_page`) hold by construction. Envelope = the pagination envelope
  `{page, per_page, total_count, results_truncated, results[], has_next}` plus `narrowed_category`
  (`{slug,name}` or null), `suggested_category` (slug or null), `suggested_city` (slug or null) and
  `search_cache_max_hits`. `total_count` may be `SEARCH_CACHE_MAX_HITS + 1` on a truncated search —
  `results_truncated` stays the authoritative signal (**O-2b**, §"Endpoint inventory" envelope note
  above). Analytics/history — `SEARCH_PERFORMED` + popular-search + search-history — are recorded
  inline (same three calls, same order, and the same session arg as the HTML view), so an API and
  an HTML search for the same query have identical side effects (incl. warm cache). Errors: 422
  `validation_failed` via `validation_problem` (the single 422 trigger is a `features` list over
  `MAX_FEATURE_FILTER_SLUGS`); 429 `rate_limited` problem + `Retry-After` via
  `rate_limit_check(namespace="api_search", budget=API_PUBLIC_READ)` + `rate_limited_problem`. The
  HTML search view is **untouched** (zero diff; its legacy `{"error":"rate_limit"}` 429 shape is
  frozen). Pairing row `("apps.search.views.api.search", "apps.search.views.search")` registered in
  `apps/api/tests/test_import_rule.py`; the mandated `apps.core.schemas` (`BaseInputModel`) is added
  to that harness's ALLOWLIST (the shared DTO base the API adapters use). Tests:
  `apps/search/tests/test_search_api.py` (param parity across every dimension, cap/truncation
  through the warm-cache seam, HTML/JSON parity incl. warm-cache, analytics/history parity, `?lang`
  locale parity, and the 422/429 problems).
- **S1.5:** `GET /api/v1/ads/{id}/` shipped (endpoint row #3 → `shipped`). New
  `apps/ads/views/api/detail.py` and a second route in `apps/ads/api_urls.py`
  (`<int:ad_id>/` → `ad_detail`; the listings `""` route is untouched). The endpoint mirrors the
  HTML `ad_detail` view (which lives in `apps.ads.views.listings`) with the **same** audience
  predicate (`account_state_q("user__")` + `status=PUBLISHED`) and the **same** `AD_VIEWED`
  side effect (seller attribution), so audience parity and the analytics side effect hold by
  construction. A **missing** id and every audience-blocked cause (draft / unpublished, deleted /
  declined / banned / consent-withdrawn seller) answer the **identical** uniform 404 problem
  document (`type="not_found"`, English detail `"Ad not found."`) — the distinction is never
  leaked (CWE-209). Payload extends the listings `_serialize_ad` shape with `description`
  (localized), `is_favorited` (the same `ad.favorites.filter(...)` source the HTML view uses;
  anonymous reads `False`) and `contact_url` — the Telegram deep-link
  `https://t.me/<bot_username>?start=contact_<ad_id>` assembled from the shared `SiteConfig` bot
  username (plan stance #23), `null` when the seller is not contactable (the inlined Zone R2
  predicate: PUBLISHED, seller has a `telegram_id`, not deleted, not banned, consent not
  withdrawn). Media stays URLs-only (plan stance #26). Errors: 429 `rate_limited` problem +
  `Retry-After` via `rate_limit_check(namespace="api_detail", budget=API_PUBLIC_READ)` +
  `rate_limited_problem`. The   HTML detail view / `apps.ads.views.listings` are **untouched** (zero
  diff). Pairing row `("apps.ads.views.api.detail", "apps.ads.views.listings")` registered in
  `apps/api/tests/test_import_rule.py`. Tests: `apps/ads/tests/test_ad_detail_api.py` (audience
  matrix incl. identical-404-shape, HTML/API `AD_VIEWED` parity, favorites tri-state, media-URLs-
  only, contact-deep-link presence/absence matrix, and the 429 problem).
- **S1.6:** `GET /api/v1/categories/` and `GET /api/v1/cities/` shipped (endpoint rows #29 and #30 →
  `shipped`). New single modules per auditor A2 (never a `views/` package beside the existing
  `apps/categories/views.py` **module**): `apps/categories/api_tree.py` and
  `apps/locations/api_cities.py`, plus `apps/categories/api_urls.py` (`app_name="categories_api"`,
  route `""` → tree) and `apps/locations/api_urls.py` (`app_name="locations_api"`, route `""` →
  cities); both mounted in `apps/api/urls.py` (`categories/`, `cities/`).
  - **Categories:** returns the full **active** tree — parents with nested `children`,
    `{cat: slug, name, children}` — assembled in one ORM query from the `Category` models
    directly. **SWR verdict honoured (auditor Check-5):** the JSON tree does **not** route through
    the submenu rendered-fragment cache in `apps.categories.views` / `apps.categories.cache`; it
    reads the models itself, so it can never serve a stale rendered fragment. For the same reason
    it does **not** expose the fragment-cache tree version — that counter versions rendered
    fragments, not the tree data, so publishing it would falsely couple the JSON contract to a
    render-cache seam. Parity with the header menu is by construction (same active-only filter at
    every level, same `order_by("name")`; an active node under an inactive/absent parent is
    unreachable and omitted), proven browserlessly in `test_categories_api.py`. `name` is localized
    for the request locale and never translated at runtime for errors.
  - **Cities:** mirrors the header city selector (`apps.core.context_processors.header_context`
    `cities`); the declared import-rule mirror is `apps.core.context_processors` (the HTML consumer
    of the `locations` models), and the API module imports the `locations` models **only**. Returns
    `{cities:[{slug, name, region, country_code}]}` in the same `order_by("name")` order;
    `region`/`country_code` come from the same row the header query already loads and help agents
    disambiguate identically named cities.
  - Errors: 429 `rate_limited` problem + `Retry-After` via
    `rate_limit_check(namespace="api_categories"|"api_cities", budget=API_PUBLIC_READ)` +
    `rate_limited_problem`. HTML sources are **untouched** (zero diff: `apps.categories.views`,
    `apps.core.context_processors`). Pairing rows
    `("apps.categories.api_tree", "apps.categories.views")` and
    `("apps.locations.api_cities", "apps.core.context_processors")` registered in
    `apps/api/tests/test_import_rule.py`. Tests: `apps/categories/tests/test_categories_api.py`
    (shape/structure, active-only filtering, per-locale names, orphan omission, HTML menu parity,
    429 problem) and `apps/locations/tests/test_cities_api.py` (shape/order, per-locale names,
    header-context parity, 429 problem).
- **S1.7:** Stage S1 i18n batch applied. The Stage S1 API surface's user-visible `detail`/`title`
  strings are now cataloged as English msgids and translatable in `ru`/`bs`/`en`
  (`apps/core/utils/problem.py` — the 10 status titles, `"Error"`,
  `"Request body failed validation."`, `"Too many requests; retry after the indicated delay."`;
  `apps/core/utils/api_auth.py` — `"Authentication required."`;
  `apps/ads/views/api/detail.py` — `"Ad not found."`). `type` tokens stay stable ASCII (never
  translated, Q6); no JSON key, status code or response shape changed. Catalogs hand-applied from a
  safe scratch extraction (`--no-location --no-obsolete`); `ru`/`bs` `msgstr` are non-empty, `en`
  stays empty (the English msgid is the source). `apps/ads/tests/test_i18n_completeness.py` green.
- **S2.1:** the favorites service `apps/ads/services/favorites.py` is **extended** (plan Q2/A1 —
  one shared favorites stack, no new module) with a list function and a toggle function; no new
  endpoint ships in this task. `favorites_queryset(user)` reproduces the cabinet list contract
  exactly (PUBLISHED + `account_state_q("user__")` audience, `.select_related("category","city",
  "user")`, `.prefetch_related("images","features","user__trust_score")`,
  `.order_by("-favorites__created_at")`, `annotate_favorites` applied) and is the future
  `GET /api/v1/favorites/` service; `toggle_favorite(user, ad_id)` returns a
  `FavoriteToggleResult(ad, is_favorited, count)` — the post-toggle state and the caller's total
  count, i.e. the `{active,count}` facts the future `POST /api/v1/favorites/{ad_id}/toggle/`
  endpoint (#15) will serialize. `annotate_favorites` is untouched. The HTML callers
  `apps/ads/views/favorite.py` and `apps/cabinet/views/favorites.py` are rewired to thin callers;
  their fragments are byte-identical (pinned by the untouched pre-existing suites). The toggle's
  `Http404` mapping (`Ad.DoesNotExist` → 404) stays view-side.
- **S2.2:** the dashboard grouping block is extracted verbatim from `apps/ads/views/dashboard.py`
  into `apps/ads/services/dashboard_query.py` — `ads_by_status(user_id)` returns the grouped `Ad`
  querysets keyed by `AdStatus` (PUBLISHED / ON_MODERATION / ON_MODERATION_FAILED / ARCHIVED /
  REJECTED, same key order) with the same `.select_related("category","city")` and the same
  `.prefetch_related("images")` on PUBLISHED/ARCHIVED; the view is rewired to consume it
  (request-free, returns ORM objects). The create-time storage-consent gate
  `_seller_may_create_ad` **stays view-side** (A14 — it is **not** relocated, and the shared
  `apps.users.services.account_state.can_create_ad` seam is **not** imported by the service or the
  view here; the later S2.3 endpoint re-asserts consent via that shared seam with an equivalence
  test). No new endpoint ships in this task.
- **S2.3:** `GET /api/v1/dashboard/` shipped (endpoint row #11 → `shipped`). New
  `apps/ads/views/api/dashboard.py` and a **second** URL module
  `apps/ads/api_dashboard_urls.py` (`app_name="dashboard_api"`, route `""` → `dashboard`), mounted in
  `apps/api/urls.py` (`dashboard/`). **Layout extension note:** the dashboard is hosted in the
  `ads` app but the plan's URL is `GET /api/v1/dashboard/` (row 11) with **no** `/ads/` prefix; per
  the plan's S2.6 principle (*"URLs keep the trust prefix… prefix orthogonal to module host"*) the
  route got its own ads URL module rather than a divergent `/ads/dashboard/` prefix. The existing
  `apps/ads/api_urls.py` (`ads/` listings + detail) is **unchanged**.
  **Response shape:** `{time_range, time_range_options, groups, stats}` where `groups` is keyed by
  `AdStatus` in the dashboard's canonical order (published / on_moderation / on_moderation_failed /
  archived / rejected), each `{count, results[]}`, and `results[]` uses the same ad fields the
  listings serializer exposes (D4). `stats` is the `SellerStats` block the HTML dashboard renders
  (`total_views` / `total_contacts` / `ads_published` / `per_ad_stats`).
  **Consent gate (A14 / R-L1):** consent is re-asserted through the shared
  `apps.users.services.account_state.can_create_ad` seam (the same predicate the HTML view's
  `_seller_may_create_ad` wraps) — the API view never imports the HTML view's private. Absent /
  withdrawn consent and banned sellers are refused with a **403 `consent_required`** problem
  **before** any grouping is built, so a forbidden account can never receive a silent empty
  grouping. `apps.users.services.account_state` is added to the import-rule ALLOWLIST (the A14
  shared seam — the allowlist's exact purpose). **Rate limit:** none — the HTML dashboard mirror has
  no rate-limit check and the plan assigns no private-read budget namespace to this route, so
  adding one would be drift rather than parity. **`?time_range=`:** accepted values are `all_time`
  (default), `30_days`, `7_days`; a missing or invalid value falls back to `all_time` (byte-identical
  to the HTML view's `TimeRange` parse). Pairing row
  `("apps.ads.views.api.dashboard", "apps.ads.views.dashboard")` registered in
  `apps/api/tests/test_import_rule.py`. Tests: `apps/ads/tests/test_dashboard_api.py` (auth matrix,
  R-L1 403-never-empty-groups, API↔HTML gate-equivalence parametrized over
  consented/never-consented/withdrawn/banned, `?time_range=` parity incl. invalid/empty fallback,
  grouped/stats payload shape).
- **S2.4:** `GET /api/v1/favorites/` list half shipped (endpoint row #15 → list half `shipped`; the
  toggle `POST …/{ad_id}/toggle/` half lands at S3.2). New `apps/cabinet/api_urls.py`
  (`app_name="cabinet_api"`, route `""` → `favorites`) and
  `apps/cabinet/views/api/{__init__,favorites}.py`, mounted in `apps/api/urls.py` (`favorites/`).
  The endpoint mirrors the HTML cabinet favorites list 1:1: the **same** shared
  `favorites_queryset(request.user)` (S2.1 — PUBLISHED + `account_state_q("user__")` audience,
  most-recently-favorited first), paginated at the **same** `PER_PAGE` (24), in the standard
  pagination envelope `{page, per_page, total_count, results_truncated, results[], has_next}`.
  **Ownership scoping** is inherent in the queryset (the caller's own favorites relation only), so
  another user's favorites are never visible. `results[]` uses the same ad fields the listings
  serializer exposes (D4). **Rate limit:** none — the HTML cabinet favorites mirror has no
  rate-limit check and the plan assigns no budget namespace to this session-gated read.
  **Ordering (R2 / tie note):** no `-id` tiebreaker is added to `favorites_queryset` (R2 lives only
  in `ListingsQuery._apply_sort`, the program's single approved ordering delta); the S2.1
  equal-key `-favorites__created_at` tie observation is carried unchanged, and because both surfaces
  run the one shared queryset the tie resolves identically on HTML and JSON (proven by the parity
  test). Pairing row `("apps.cabinet.views.api.favorites", "apps.cabinet.views.favorites")` registered
  in `apps/api/tests/test_import_rule.py`. Tests: `apps/cabinet/tests/test_favorites_list_api.py`
  (401 matrix, ownership scoping, multi-page envelope, HTML `page_obj` id/ordering parity).
- **S2.5:** `GET /api/v1/moderation/queue/?priority&page` and
  `GET /api/v1/moderation/review/{id}/` shipped (endpoint row #12 → `shipped`). New
  `apps/moderation/api_urls.py` (`app_name="moderation_api"`; routes `queue/` → `queue`, `review/<int:ad_id>/`
  → `review`), `apps/moderation/views/api/{__init__,queue,review}.py`, mounted in `apps/api/urls.py`
  (`moderation/`). **Layout drift:** the plan's file list named a single
  `apps/moderation/views/api/reads.py`; the module is split into `queue.py` + `review.py` because the
  import-subset rule pairs each API module against **one** HTML mirror, and no single mirror imports both
  `PriorityService` (queue mirror `apps/moderation/views/queue.py`) and `Ad` (review mirror
  `apps/moderation/views/review.py`) — one row per API module with the correct mirror is the harness-clean
  form. **Queue:** consumes the **same** `PriorityService.get_queued_ads` + `get_priority_counts`; `?priority=`
  accepts the `PriorityFilter` members and the `ALL` sentinel (and any missing/unknown value) maps to **no**
  filter, exactly as the HTML view's `PriorityFilter` parse does; ordering is the service's
  `-base_score, -created_at`; response is the standard pagination envelope
  `{page, per_page, total_count, results_truncated, results[], has_next}` plus `selected_priority` and
  `priority_counts`. `results[]` carries the shared ad fields (D4) plus the queue-specific
  `telegram_id`, `base_score`, `priority_level`. **Review:** the **same** lookup
  (`.select_related("user","category","city").prefetch_related("images")`, status ∈ {`ON_MODERATION`,
  `ON_MODERATION_FAILED`}) the HTML `moderation_review` uses; payload = the template-visible fields
  (`id`, localized `title`/`description`, `status`/`status_display`, `price`/`currency`, localized
  `category`/`city` `{slug,name}`, `telegram_id`, `image_urls`, timestamps, `absolute_url`). A missing id
  and an out-of-pair status answer the **identical** uniform 404 `type="not_found"` problem (CWE-209).
  **Auth:** STAFF via the new `staff_required_api_problem` (see the gap-fill line below) — 401 anon / 403
  non-staff / 405 wrong method, all problem documents, **no** `WWW-Authenticate`. **Rate limit:** none —
  the HTML moderation mirrors have no rate-limit check and the plan assigns no budget namespace here.
  Pairing rows `("apps.moderation.views.api.queue", "apps.moderation.views.queue")` and
  `("apps.moderation.views.api.review", "apps.moderation.views.review")` registered in
  `apps/api/tests/test_import_rule.py`. Tests: `apps/moderation/tests/test_moderation_api_reads.py`
  (401/403/405 matrix no-challenge, priority-filter parity incl. `ALL`/missing/unknown, envelope +
  counts + ordering, review payload parity, uniform 404).
- **Gap-fill (S2.5):** RFC 9457 staff gate `staff_required_api_problem` added to
  `apps/core/utils/api_auth.py` for GET reads; frozen legacy `staff_required_api`
  (`apps/moderation/views/decorators.py`, POST-only, plain `{"error": …}` body) is untouched. It refuses
  anon with a 401 `unauthenticated`, non-staff with a 403 `forbidden`, and a wrong method with a 405
  `method_not_allowed` (with an `Allow` header) — all problem documents, identity before method, **no**
  `WWW-Authenticate` (09-API-010). Same session-cookie credential; no new scheme. Serves S2.5, S2.6, and
  later S4.7 writes. `apps/core/utils/api_auth` is already in the import-rule ALLOWLIST (no new entry).
  Unit tests appended to `apps/core/tests/test_api_auth.py` (`TestStaffRequiredApiProblem`).
- **S2.6:** `GET /api/v1/trust/seller/` (endpoint row #31 → `shipped`) and
  `GET /api/v1/trust/moderation/` (endpoint row #32 → `shipped`) shipped. New
  `apps/analytics/api_urls.py` (`app_name="analytics_api"`; routes `seller/` → `seller`, `moderation/`
  → `moderation`), `apps/analytics/views/api/{__init__,seller,moderation}.py`, mounted in
  `apps/api/urls.py` (`trust/`). **Host vs prefix (A3):** both dashboards are **hosted in
  `apps/analytics`** (they mirror `apps/analytics/views/{seller_dashboard,moderation_dashboard}.py`) but
  their URLs keep the `trust/` prefix — the plan's S2.6 principle (*"URLs keep the trust prefix… prefix
  orthogonal to module host"*). **Layout drift:** the plan's file list named a single
  `apps/analytics/views/api/dashboards.py`; the module is split into `seller.py` + `moderation.py`
  because the import-subset rule pairs each API module against **one** HTML mirror, and the seller mirror
  imports only `trust_analytics` while the moderation mirror imports only `moderation_analytics` — one
  row per API module with the correct mirror is the harness-clean form. **Seller payload:**
  `{trust_score, trust_level, daily_metrics[], total_views, total_contacts}` — the same `trust_analytics`
  service tier the HTML view calls (`calculate_seller_trust_score`, `get_trust_level`,
  `get_seller_daily_metrics(days=30)`) and the same totals the view sums from the daily rows;
  `trust_score` is rounded to one decimal exactly as the view does; `daily_metrics[]` rows expose the
  `DailyAdMetrics` fields (date / ad_id / views_count / contacts_count / trust_score / avg_response_time).
  **Moderation payload:** `{stats, pending_queue_size, moderator_performance[], rejection_reasons, days}`
  — the same `moderation_analytics` service tier (`get_moderation_stats`, `get_pending_queue_size`,
  `get_moderator_performance`, `get_rejection_reasons`, all `days=30`) and the same context keys the HTML
  view sets. **No duplicated analytics logic** — both endpoints call the services the HTML mirrors use.
  **Auth:** seller = SESS via `login_required_api` (anon → 401 `unauthenticated` problem, no
  `WWW-Authenticate`) with an **inline GET-only method gate** (non-GET → 405 `method_not_allowed` problem
  + `Allow: GET`); identity runs first (anon POST → 401). Moderation = STAFF via
  `staff_required_api_problem` (401 anon / 403 non-staff / 405 wrong method, all problem documents, no
  `WWW-Authenticate`) — mirroring the HTML mirror's `@staff_required` audience as a problem document
  rather than the HTML 404. **Rate limit:** none — the HTML analytics dashboards have no rate-limit check
  and the plan assigns no budget namespace here. Pairing rows
  `("apps.analytics.views.api.seller", "apps.analytics.views.seller_dashboard")` and
  `("apps.analytics.views.api.moderation", "apps.analytics.views.moderation_dashboard")` registered in
  `apps/api/tests/test_import_rule.py`. Tests: `apps/analytics/tests/test_analytics_api.py` (auth matrix
  no-challenge incl. the seller 405 + `Allow`, payload parity vs the HTML dashboards' context for the
  same fixtures).

- **S2.7:** `GET /api/v1/saved-searches/` (endpoint row #16 → read half `shipped`; the
  create/toggle/edit/delete write halves land at S3.4) and `GET /api/v1/search-history/`
  (endpoint row #18 → read half `shipped`; the clear half lands at S3.5) shipped. New
  `apps/cabinet/views/api/{saved_searches,search_history}.py`, mounted in
  `apps/api/urls.py`.
  - **URL restructure (Tech Lead ruling).** `apps/cabinet/api_urls.py` is now
    **prefix-based**, hosting all cabinet endpoints in one module per the plan's Q1
    file inventory: `path("favorites/", …)`, `path("saved-searches/", …)`,
    `path("search-history/", …)`. The aggregator line changed from
    `path("favorites/", include("apps.cabinet.api_urls"))` to
    `path("", include("apps.cabinet.api_urls"))`, so the public URLs are exactly
    `GET /api/v1/favorites/` (**unchanged**), `GET /api/v1/saved-searches/` and
    `GET /api/v1/search-history/`. No `test_urls.py` constant entry became live
    (`/api/v1/` itself still has no route and stays 404).
  - **Saved searches.** Mirrors the HTML cabinet saved-searches list 1:1: the **same**
    `SavedSearch.objects.filter(user=request.user).select_related("city",
    "category").order_by("-created_at")` queryset and the **same** per-row facts the HTML
    row renders (query, localized `city`/`category` `{id,slug,name}`, `min_price`/
    `max_price`, `is_active` toggle) plus the model timestamps (`created_at`/
    `updated_at`/`last_notified_at`). The `unsubscribe_token` capability token is
    deliberately never exposed. The HTML mirror is **unpaginated** (it renders every
    saved search on one page), so there is no HTML page size to mirror; `PER_PAGE` (24)
    is the one addition the mandated pagination envelope requires. **Ownership scoping**
    is the `user=request.user` filter — another user's rows are never visible.
  - **Search history — SESS-only (A6).** The HTML mirror is `@login_required` and the
    cabinet docstring states anonymous (session) search history is never shown there, so
    this endpoint is **session-only** and mirrors that gate exactly: anonymous requests
    answer the 401 `unauthenticated` problem and anonymous session history is **never**
    exposed. **The earlier "anon readback" claim is dropped** — anonymous session history
    remains machine-reachable only through the autocomplete endpoint (#4, out of scope).
    Payload = the template fields `{query, created_at}` with the same `-created_at`
    ordering and the same 100-entry cap (`_HISTORY_LIMIT`) as the HTML view; the caller's
    own history only.
  - **Auth:** both reads are SESS via `login_required_api` (anonymous → 401
    `unauthenticated` problem, **no** `WWW-Authenticate`). **Rate limit:** none — neither
    HTML cabinet mirror has a rate-limit check and the plan assigns no budget namespace to
    these session-gated reads. Pairing rows
    `("apps.cabinet.views.api.saved_searches", "apps.cabinet.views.saved_searches")` and
    `("apps.cabinet.views.api.search_history", "apps.cabinet.views.search_history")`
    registered in `apps/api/tests/test_import_rule.py`. Tests:
    `apps/cabinet/tests/test_saved_searches_api.py` (401 matrix for both endpoints no
    challenge, ownership scoping for both, pagination envelope + ordering parity with the
    HTML mirrors, the A6 anon-history assertion, and a restructure guard that
    `GET /api/v1/favorites/` still works exactly as after S2.4).
- **S2.8 — M2 gate:** Stage S2 i18n batch applied. The Stage S2 API surface's
  user-visible `detail` strings are now cataloged as English msgids and translatable in
  `ru`/`bs`/`en` (`apps/core/utils/api_auth.py` — `"Staff access required."`,
  `"Method not allowed."`; `apps/analytics/views/api/seller.py` — `"Method not allowed."`;
  `apps/ads/views/api/dashboard.py` — `"Storage consent is required to view the seller
  dashboard."`). `apps/moderation/views/api/review.py`'s `"Ad not found."` reuses the
  already-cataloged S1.7 msgid (no new entry). `type` tokens stay stable ASCII (never
  translated, Q6); no JSON key, status code or response shape changed. Catalogs
  hand-applied from a safe scratch extraction (`--no-location --no-obsolete`);
  `ru`/`bs` `msgstr` are non-empty, `en` stays empty (the English msgid is the source).
  **M2 gate verified:** fast gate green (3871 passed) with the pre-existing
  favorites/cabinet/consent HTML suites untouched-green; the S2 API test files
  (`test_dashboard_api.py`, `test_dashboard_stats.py`, `test_favorites_list_api.py`,
  `test_saved_searches_api.py`, `test_moderation_api_reads.py`, `test_analytics_api.py`,
  `test_api_auth.py`) green; `401/403/405` auth matrices green for every private
  endpoint; `apps/ads/tests/test_i18n_completeness.py` green (30 passed). Gaps 11
  (dashboard) and 12 (moderation reads) covered; gap 15/16/18 read halves covered.
- **S3.1:** saved-search mutator service extracted — `apps/search/services/saved_searches.py`
  now owns every `SavedSearch` write (`bound_query`, `create_saved_search`, `update_saved_search`,
  `toggle_saved_search`, `delete_saved_search`). The two HTML callers
  (`apps/search/views/save_search.py`, `apps/cabinet/views/saved_searches.py`) are rewired as thin
  callers; their rendered fragments / 400 / 302 shapes are **byte-identical** (proven by the
  untouched HTML-flow suites `test_saved_search_create.py`, `test_saved_search_input_boundary.py`,
  `test_cabinet_sections.py`). **No endpoint ships in this task** — row #16's create/toggle/edit/delete
  write halves land at S3.4 on this service. **Contract:** request-free (a `User` + the shared
  `SavedSearchInput` DTO, never an `HttpRequest`); ownership is enforced per row and reported as
  `SavedSearch.DoesNotExist` (the HTML views map it to `Http404`, the future API to a uniform 404
  problem). **Token semantics preserved:** the opaque `unsubscribe_token` is generated once on create
  by `SavedSearch.save()` and never regenerated by update/toggle/delete.
  `apps/search/services/__init__.py` gained no imports; `telegram_bot/services/alerts.py` is untouched
  (its token protocol is by design). Tests: new `apps/search/tests/test_saved_search_service.py`
  (service-tier CRUD, ownership refusals, token stability across update/toggle, the query bound).
