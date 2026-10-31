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
| 2 | FTS search | `apps/search/services/fts.py` (S1.1) | `GET /api/v1/search/?q&category&city&min_price&max_price&listing_purpose&condition&features&sort&page&all_categories` | PUB | fuzzy / did-you-mean / narrowed fields; cap semantics; 429 problem | planned |
| 3 | Ad detail | audience predicate + serialize | `GET /api/v1/ads/{id}/` | PUB | uniform 404; `AD_VIEWED` recorded | planned |
| 4 | Autocomplete | (existing) | unchanged `/api/search/autocomplete` | PUB | stance: not aliased; legacy 429 `{"error":"rate_limit"}` | covered/frozen |
| 5 | Create/publish | `create_draft_ad` + `submit_ad` | `POST /api/v1/ads/{id}/submit/` (existing DRAFT; dialog/photo staging bot-only) | SESS (consent via outcome) | `SubmitAdOutcome` map (§Errors) | planned |
| 6 | Edit | edit-flow helper (S4.2) — five branches | `POST /api/v1/ads/{id}/edit/` | SESS + owner | refusal → 409 `not_editable` (HTML renders 200+form — deliberate machine mapping); price-only and direct-save stay distinct from `submit_ad` | planned |
| 7 | Archive | lifecycle service (S4.1) | `POST /api/v1/ads/{id}/archive/` | SESS + owner + **consent** | 403 `consent_required`; 409 | planned |
| 8 | Reactivate | lifecycle service (S4.1), same `auto_moderate` decision | `POST /api/v1/ads/{id}/reactivate/` | SESS + owner + consent | 200 outcome; 409; 503 lock-timeout | planned |
| 9 | Delete | lifecycle service (S4.1) — gate-free | `POST /api/v1/ads/{id}/delete/` | SESS + owner | 204 | planned |
| 10 | Copy | `copy_ad` (`copy_service.py:39` via `_build_ad_copy:15`) | `POST /api/v1/ads/{id}/copy/` | SESS | 200 `{ad_id}` — new DRAFT owned by seller; max-ads + consent predicates as in the bot flow | planned |
| 11 | Dashboard reads | dashboard grouping (S2.2) + `SellerStats` | `GET /api/v1/dashboard/?time_range=` | SESS + consent | **403 `consent_required` when consent absent — never an empty list** (R-L1) | planned |
| 12 | Moderation queue/review | `PriorityService.get_queued_ads` / `get_priority_counts` | `GET /api/v1/moderation/queue/?priority&page`, `GET /api/v1/moderation/review/{id}/` | STAFF | 401 / 403 / 405 | planned |
| 13 | Single actions | `admin_actions.approve_ad/reject_ad/ban_user_for_ad` | `POST /api/v1/moderation/{approve,reject,ban}/{id}/` | STAFF | §Errors mappings | planned |
| 14 | Bulk | (existing) — **frozen shape** | unchanged `/moderation/api/v1/bulk-action/` | STAFF | no change | covered/frozen |
| 15 | Favorites | extend `apps/ads/services/favorites.py` (list + toggle) | `GET /api/v1/favorites/` · `POST /api/v1/favorites/{ad_id}/toggle/` | SESS | 200 `{active,count}`; uniform 404 | planned |
| 16 | Saved-search CRUD | `apps/search/services/saved_searches.py` (S3.1) on shared `SavedSearchInput` | `GET/POST /api/v1/saved-searches/`, `POST …/{pk}/{toggle,edit,delete}/` | SESS | 422; uniform 404 | planned |
| 17 | Alert delivery | `send_alerts` + services | unchanged (bot digest + scheduler) | — | stance: no HTTP endpoint; agent-visible substitute is `SavedSearchNotification.delivered_at` (read via `verify_parity`/shell tier) | covered/frozen |
| 18 | Search history list/clear | `search_history` service | `GET /api/v1/search-history/` · `POST /api/v1/search-history/clear/` | **SESS** (HTML mirrors are `@login_required`; anon session history is only reachable via autocomplete #4) | 204 clear | planned |
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
