# Agent-First / API Parity — Final Consolidated Migration Plan

**Project:** Mko Bazuna · **Date:** 2026-10-31 · **Author:** planner (Phases 3–5) · **Status:** implementation-ready
**Supersedes for execution:** `phase3-strategy.md` + `phase4-roadmap.md` (kept in `.ai\tmp\api-parity\` as working history — Appendix B). All Phase-5 validation findings (auditor: 12 required edits + advisories; researcher: R-F2, R-L1 + optionals) are incorporated; ledger in Appendix A.
**Canonical commands (Windows):** fast gate `.\Makefile.ps1 test` · full `.\Makefile.ps1 test-all` · targeted `$dc run --rm -e PYTEST_OPTS="src/backend/apps/<app>/tests/test_x.py --tb=short" test` (`$dc`/`$dev` aliases per `.kilo\rules\commands.md`; `PYTEST_OPTS` is word-split — bare paths/`-k` only — and replaces xdist defaults) · lint `uv run ruff check <path>` · typecheck `uv run basedpyright <path>` · **migration tripwire (pinned form, per auditor A12):** `$dev run --rm --no-deps --entrypoint "" web python src/backend/manage.py makemigrations --check` — never a bare local invocation (defaults to `config.settings.prod`, which fail-fasts on `REDIS_URL` outside Docker). Local `uv run pytest` never (Docker test service only). `.mo` files compile automatically; catalogs only via the scratch-extract recipe (`.kilo\rules\commands.md`).

---

## 1. Current-state assessment and parity gaps

**Assessment (Phase-1 audit, code-verified).** The service layer is the project's strength: co-located, request-free services (`submit_ad`, `ListingsQuery`, `account_state_q`, `admin_actions`, `PriorityService`, `copy_ad`, `SellerStats`, trust/analytics services) are already shared by HTMX views, bot handlers, and the one shipped JSON write surface (`/moderation/api/v1/bulk-action/`). What rule 18 lacks is the *boundary*: nearly every buyer/seller/moderator read exists only as rendered HTML; writes are POST-form-or-bot only. Filters, sorting, pagination and search behavior are individually browserless-testable today (ORM/`Client()`), but no external machine-readable surface exists for any read. The auth model is deliberately session-only — the only credential bootstrap is Telegram-mediated (`issue_token` web half, bot claim, web consume; two frozen predicates), and `staff_required_api` explicitly refuses a `WWW-Authenticate` challenge (09-API-010); headless functional verification therefore rides Django `Client()` (CSRF off in pytest), never a new auth scheme. The bot FSM persists drafts as real `Ad(DRAFT)` rows with staged photo files — any API write must play by the same `AdStatus` state machine. Tests are HTML-coupled in places (~68 `response.content` assertions; `test_filter_url_reset.py`, `test_sort_on_search_results.py`, `test_auth_nav.py` pin rendering contracts, which is legitimate UI-intent coverage that stays).

**Gap register (28 actions, ranked; coverage before this program):**

| # | Action | Before | Effort/risk note |
|---|---|---|---|
| 1 | Browse listings + filters + sort + pagination | uncovered (no HTTP surface; `ListingsQuery` callable) | small — DTO/service exist; JSON adapter + rate-limit/cache-cap semantics |
| 2 | FTS search (locale vectors, fuzzy) | uncovered — pipeline view-local; `alert_query.py` sibling deviates by design | HIGH — extraction precedes endpoint |
| 3 | Ad detail read | uncovered — favorites state + `AD_VIEWED` side effect in view | small/medium — side-effect stance (§2.4) |
| 4 | Autocomplete | covered (JSON) | unchanged; not aliased |
| 5 | Create/publish ad (bot dialog) | partial — `submit_ad` service shared; dialog bot-only | submit-on-draft endpoint closes the HTTP tier |
| 6 | Edit ad | partial — `submit_ad` for two paths; price-only + direct-save view-embedded | HIGH — five outcome branches (§2.6) |
| 7 | Archive ad | uncovered — orchestration in view; **consent-gated** (`edit.py:445-446`) | small |
| 8 | Reactivate ad | uncovered — `transition_to` + `auto_moderate` in view | small — must reuse same moderation decision |
| 9 | Delete ad (soft) | uncovered — trivial ownership+transition (gate-free) | small |
| 10 | Copy ad | covered at service tier (`copy_ad`), no JSON | small |
| 11 | Dashboard reads | uncovered — grouping view-local; consent-gated | medium |
| 12 | Moderation queue/review reads | service-covered, HTML-only | medium |
| 13 | Approve/reject/ban single | partial — service+admin, no JSON single-action | medium (S4) |
| 14 | Bulk moderation | covered (frozen public shape) | none — untouched |
| 15 | Favorites list/toggle | uncovered — two hand-built queries; toggle answers HTML fragment | small |
| 16 | Saved-search CRUD/toggle | uncovered — two mutator stacks (web vs bot) + shared DTO | medium — one shared mutator stack |
| 17 | Alert delivery | partial (CLI + services; Telegram-only push) | stance (§6/§S5.3) |
| 18 | Search history list/clear | uncovered — recording view-coupled; cabinet surfaces `login_required` | small — SESS-only API |
| 19 | Preferred-city set/clear | covered (JSON; cookie/consent HTTP-shaped) | unchanged |
| 20 | Consent accept/decline/withdraw | partial — services request-free; cookies/audit/flush view-layer | medium |
| 21 | Login issue/status | partial — services shared; status endpoint already a status-code contract | stance — machine contract documented, no new endpoint |
| 22 | Logout | covered (Django logout) | small — JSON alias completes lifecycle |
| 23 | Contact seller | by-design bot-only (anonymity, decision C) | stance — deep-link protocol |
| 24 | Support ticket | bot handler is the only writer (06-PII-101 signed identity) | stance — callable service, no HTTP |
| 25 | Language preference | bot writes `telegram_language`; web `?lang` middleware | stance — `?lang` on API URLs |
| 26 | Media access | by-design binary (nginx `X-Accel` gate) | stance — URLs only in payloads |
| 27 | Ops healths/metrics | covered | unchanged; deliberately no JSON inventory endpoint (D2) |
| 28 | Django admin actions | covered (staff-web; 4th consumer of `admin_actions`) | unchanged |

**HTML-only reads that gained JSON parity by this plan:** listings (#1), search (#2), ad detail (#3), dashboard (#11), moderation queue/review (#12), trust/analytics dashboards (S2.6 surfaces), favorites list (#15), saved-searches list (#16), search history (#18).

---

## 2. Target architecture and key design decisions

### 2.1 Layered view

```
            HTMX views (MPA, untouched)   /api/v1/ JSON views (new)   Telegram bot (as-is)
                    └──────────── calls the same services ────────────┘
                                                ▼
      Service layer — co-located, request-free, returns ORM objects (unchanged contract;
      new extractions: search FTS pipeline, saved-searches mutators, favorites extend,
      dashboard grouping, ad lifecycle, edit flow — all shared by HTML + API)
                                                ▼
      ORM + PostgreSQL (no new tables/migrations anywhere)      CLI tier: ops commands +
      new read-only `verify_parity`
```

### 2.2 Ratified decisions (one line each)

| ID | Decision | Rationale |
|---|---|---|
| D1 | Plain Django JSON views + Pydantic `BaseInputModel` DTOs, `api_bulk.py` precedent (422 `pydantic_errors_json`, `@require_POST`); no DRF/ninja | shipped precedent, zero new framework |
| D2 | OpenAPI deferred; `docs/01-spec/api-surface.md` is the single source of truth | schema-only gain would add framework + RFC-9457 rework |
| D3 | No new auth, no CSRF exemption; browserless tests via `Client()`; settings-gated secret-header only as contingency (§6) | the shipped credential model is session-cookie only; headless tests need no new auth surface |
| D4 | Serialization = per-app `_serialize_*` in API view modules; services keep returning ORM objects | keeps the service contract unchanged |
| D5 | Public reads anonymous + same `account_state_q` audience; private session/staff; writes honor consent/ban/deletion predicates | visibility parity by construction |
| D6 | Separate `/api/v1/` URLs; never dual-format HTMX; MIDDLEWARE untouched | MPA stays intact; header-driven partial swaps would fork |
| D7 | Playwright only for a11y/visual/HTMX-swap/Telegram login round-trip; opt-in `e2e` marker; never in the fast gate | all functional behavior provable browserlessly |
| R1 | Shared `rate_limit_check`+`RateLimitBudget` stays the single enforcement point; **/api/v1/ renders 429 as RFC 9457 problem** (`type:"rate_limited"`, `Retry-After` from the budget window); legacy surfaces keep their shapes | rule 18 mandates RFC 9457; /api/v1/ has no legacy consumers |
| R2 | `-id` tiebreaker added to `_apply_sort` | deterministic pages; the single approved ordering delta (HTML == JSON) |
| R3 | `django-filter` stays out of scope | dead dep; owner decision (§6) |
| R4 | Correct the stale scheduler-pins sentence in `architecture.md` | doc-accuracy DoD (S5.4) |

### 2.3 Open-question resolutions (Q1–Q6)

- **Q1 layout:** per-app API views + URL-only aggregator `apps/api/urls.py` (imports zero views/services/models; `apps/api` is NOT in `INSTALLED_APPS`). Neutralizes the audit's new-top-level-importer cycle risk by construction; dead DRF dirs deleted; explicit `apps/api/__init__.py` created (auditor Check-2). Module layout convention (corrected):

| Module | Role |
|---|---|
| `src/backend/config/urls.py` | `path("api/v1/", include("apps.api.urls"))` + rewritten contract comment |
| `src/backend/apps/api/__init__.py`, `apps/api/urls.py`, `apps/api/tests/{__init__,test_urls,test_import_rule}.py` | aggregator + purity/import-rule tests (R-F2); empty `apps/api/serializers/`, `apps/api/views/` deleted |
| `apps/<app>/api_urls.py` | routes; `app_name = "<app>_api"` (no collision — existing namespaces verified: ads/analytics/cabinet/categories/core/locations/moderation/search/"consent") |
| `apps/<app>/views/api/…` | API views where the app has a `views/` package (ads, search, moderation, cabinet, users, analytics) |
| one-off single modules for single-endpoint apps | `apps/categories/api_tree.py`, `apps/locations/api_cities.py` (auditor A2: `categories/views.py` is a module — a `views/` package beside it is an import collision) |
| `apps/core/utils/problem.py`, `apps/core/utils/api_auth.py` | shared RFC 9457 helper + `login_required_api` (mirror of `staff_required_api`; its tests `apps/moderation/tests/test_decorators.py` are the precedent) |

- **Q2 duplications:** FTS pipeline → `apps/search/services/fts.py` (prerequisite of the search endpoint); `alert_query.py` NOT unified (documented divergence: persisted language, `-rank`-only order); saved-search mutators → `apps/search/services/saved_searches.py` for web+API (bot token stack untouched); favorites → **extend** `apps/ads/services/favorites.py` (already hosts `annotate_favorites`).
- **Q3 side effects:** API reads record analytics identically (AD_VIEWED; SEARCH_PERFORMED + popular-search + history). No `track=` opt-out in v1 (revisit trigger documented). Guidance: verification loops use the service tier / `verify_parity` (no side effects).
- **Q4 rate limiting:** new `RateLimitBudget` members `API_PUBLIC_READ` (60/60s, per-route namespaces `api_listings`, `api_search`, `api_detail`, `api_categories`, `api_cities`) and `API_WRITE` (30/60s, shared `api_write`); numbers in the StrEnum property dicts; no env vars. 429 rendering per R1.
- **Q5 doc overturn (first-class S0.1):** `config/urls.py:15-18` comment, `docs/01-spec/architecture-structure.md` §API Surface Contract, `docs/01-spec/spec-index.md`, `README.md` + new `docs/01-spec/api-surface.md`.
- **Q6 errors:** taxonomy in §2.5; helper `apps/core/utils/problem.py` extending the `pydantic_errors_json` deposit (`apps/core/utils/sanitize.py:295`); `type` = stable ASCII token (never translated); `detail` = English msgid in ru/bs/en catalogs; locale via the shared middleware chain (`?lang` > `lang_pref` cookie > `Accept-Language` — no per-view locale code).
- **Consent-gate re-assertion (auditor A14 resolution):** API views for dashboard/archive/submit re-assert consent through the shared `apps.users.services.account_state.can_create_ad` seam — the same underlying predicate `_seller_may_create_ad` wraps — NOT by importing view privates from `apps/ads/views/edit.py`. The HTML wrapper stays where it is; equivalence is pinned by a test asserting both gates agree for non-consented/withdrawn/banned fixtures (S2.3/S4.3).
- **Import rule (mechanically enforced, researcher R-F2):** *an API view module's imports must be a subset of its mirrored HTML view module's imports* (plus an explicit allowlist: `apps.core.utils.problem`, `apps.core.utils.api_auth`, stdlib/django). Where the mirror itself imports another app — cabinet→search, ads→analytics (`seller_stats`), analytics→moderation decorators — the API view mirrors those same imports. Enforced by `apps/api/tests/test_import_rule.py`: an `ast`-based harness with a declared pairing table (API module → mirror module); each endpoint task registers its row. The cities endpoint's "mirror" is `apps/core/context_processors/header_context` (city query — locations models only); declared in the pairing table. Aggregator purity (no non-django imports in `apps.api.urls`) checked in the same file.

### 2.4 Endpoint inventory (audit # → corrected plan)

Auth: **PUB** = anonymous + `account_state_q`; **SESS** = `login_required_api`; **STAFF** = `staff_required_api`. Writes POST-only (matches 18×`@require_POST` idiom; no PUT/PATCH/DELETE in v1). Pagination envelope: `{page, per_page, total_count, results_truncated, results[], has_next}`; `total_count` may be `SEARCH_CACHE_MAX_HITS + 1` on truncated search — `results_truncated` is the authoritative signal.

| # | Action | Service | Endpoint · Method | Auth | Error notes |
|---|---|---|---|---|---|
| 1 | Listings | `ListingsQuery.build_queryset` / `build_listings_context` (E) | `GET /api/v1/ads/` | PUB | 422; 429 problem |
| 2 | FTS search | `apps/search/services/fts.py` (X, S1.1) | `GET /api/v1/search/?q&category&city&min_price&max_price&listing_purpose&condition&features&sort&page&all_categories` | PUB | fuzzy/did-you-mean/narrowed fields; cap semantics; 429 problem |
| 3 | Ad detail | audience predicate (E) + serialize | `GET /api/v1/ads/{id}/` | PUB | uniform 404; `AD_VIEWED` recorded |
| 4 | Autocomplete | E | unchanged `/api/search/autocomplete` | PUB | stance: not aliased |
| 5 | Create/publish | `create_draft_ad` + `submit_ad` (E) | `POST /api/v1/ads/{id}/submit/` (existing DRAFT; dialog/photo staging bot-only) | SESS (consent via outcome) | `SubmitAdOutcome` map §2.5 |
| 6 | Edit | edit-flow helper (X, S4.2) — **five branches**: ARCHIVED-reactivation→`submit_ad` (`edit.py:248-290`); PUBLISHED-text→`submit_ad` (`:296-334`); PUBLISHED-price-only direct (`:335-353`); DRAFT/ON_MODERATION direct-save via `EDITABLE_DIRECT_SAVE_STATUSES` (`:63-65`, branch `:364-379`); defined refusal (`:380-397`) | `POST /api/v1/ads/{id}/edit/` | SESS+owner | refusal → 409 `not_editable` (HTML renders 200+form — deliberate machine mapping, documented); price-only and direct-save stay distinct from `submit_ad` (frozen rule) |
| 7 | Archive | lifecycle service (X, S4.1) | `POST /api/v1/ads/{id}/archive/` | SESS+owner+**consent** (`edit.py:445-446`) | 403 `consent_required`; 409 |
| 8 | Reactivate | lifecycle service (X), same `auto_moderate` decision | `POST /api/v1/ads/{id}/reactivate/` | SESS+owner+consent | 200 outcome; 409; 503 lock-timeout (already middleware-routed in HTML) |
| 9 | Delete | lifecycle service (X) — gate-free | `POST /api/v1/ads/{id}/delete/` | SESS+owner | 204 |
| 10 | Copy | `copy_ad` (`copy_service.py:39` via `_build_ad_copy:15`) | `POST /api/v1/ads/{id}/copy/` | SESS | 200 `{ad_id}` — new DRAFT owned by seller; max-ads + consent predicates as in the bot flow |
| 11 | Dashboard reads | dashboard grouping (X, S2.2) + `SellerStats` (E) | `GET /api/v1/dashboard/?time_range=` | SESS+consent | **403 `consent_required` when consent absent — never an empty list** (R-L1) |
| 12 | Moderation queue/review | `PriorityService.get_queued_ads` / `get_priority_counts` (`priority.py:54,84`) | `GET /api/v1/moderation/queue/?priority&page`, `GET /api/v1/moderation/review/{id}/` | STAFF | 401/403/405 |
| 13 | Single actions | `admin_actions.approve_ad/reject_ad/ban_user_for_ad` (E) | `POST /api/v1/moderation/{approve,reject,ban}/{id}/` | STAFF | §2.5 mappings |
| 14 | Bulk | E, **frozen shape** | unchanged `/moderation/api/v1/bulk-action/` | STAFF | no change |
| 15 | Favorites | extend `apps/ads/services/favorites.py` (list+toggle) | `GET /api/v1/favorites/` · `POST /api/v1/favorites/{ad_id}/toggle/` | SESS | 200 `{active,count}`; uniform 404 |
| 16 | Saved-search CRUD | `apps/search/services/saved_searches.py` (X, S3.1) on shared `SavedSearchInput` | `GET/POST /api/v1/saved-searches/`, `POST …/{pk}/{toggle,edit,delete}/` | SESS | 422; uniform 404 |
| 17 | Alert delivery | `send_alerts` + services (E) | unchanged (bot digest + scheduler) | — | stance §6 |
| 18 | Search history list/clear | `search_history` service (E) | `GET /api/v1/search-history/` · `POST /api/v1/search-history/clear/` | **SESS** (HTML mirrors are `@login_required`; anon session history visible only via autocomplete #4) | 204 clear |
| 19 | Preferred-city | E | unchanged `/api/preferred-city/` | anon+consent cookie | stance: not aliased; **no rate limiter exists** |
| 20 | Consent | `give/decline/withdraw_consent` (E) | `POST /api/v1/consent/{accept,decline,withdraw}/` | accept/decline anon-allowed (HTML parity); withdraw SESS | cookie quartet stays HTML; withdraw still `logout()`s |
| 21 | Login issue/status | `issue/consume_token` (E; predicates frozen) | **No new endpoint** — `/login/status/` documented as the machine contract (200/204/410); GET-issuance gap owned by phase 15 | anon | uniform 410, anti-enumeration |
| 22 | Logout | Django `logout` (E) | `POST /api/v1/auth/logout/` | SESS | 204 |
| 23 | Contact seller | bot-only by design | deep-link protocol — detail payload carries the `t.me` link | — | stance §6 |
| 24 | Support ticket | bot writer only (06-PII-101) | in-process callable; no HTTP intake in v1 | — | stance §6 |
| 25 | Language | shared middleware | `?lang` works identically on `/api/v1/` URLs; bot `/language` untouched | — | locale parity by construction |
| 26 | Media | `media_gate` (E) | unchanged; URLs only in payloads | — | binary protocol |
| 27 | Ops/metrics | `core/views` (E) | unchanged; deliberately no `/api/v1/` index endpoint (D2; optional item §6) | — | — |
| 28 | Admin actions | `admin_actions` (E) | unchanged staff-web | — | — |

### 2.5 Error taxonomy (RFC 9457; helper `apps/core/utils/problem.py`, content-type `application/problem+json`)

| Outcome | HTTP + `type` | Notes |
|---|---|---|
| `SubmitAdOutcome.PUBLISHED` / `MODERATION_FAILED` | 200 `{outcome}` | boundary rule (O-2a): 4xx only when the request committed NO state change; `MODERATION_FAILED` parks the ad — a terminal, well-formed outcome (bulk precedent `api_bulk.py:116-122`) |
| `SubmitAdOutcome.CONSENT_REQUIRED` | 403 `consent_required` | same predicate (`can_create_ad`) as UI |
| `INVALID_TRANSITION` / `DRAFT_GONE` / `PHOTO_UNAVAILABLE` | 409 `invalid_transition` / `draft_gone` / `photo_unavailable` | state-machine family |
| Edit refusal (status outside editable/affordance sets) | 409 `not_editable` | deliberate delta from HTML 200+form — documented (auditor A5) |
| `ApproveOutcome.PUBLISHED` / `CRITERIA_REJECTED` | 200 `{outcome}` / 200 `{outcome:"criteria_rejected"}` | ad parked `ON_MODERATION_FAILED` |
| `ApproveOutcome.TRANSITION_REFUSED` | 409 `transition_refused` | |
| `BanResult` changed≥1 | 200 counts (`changed/already_in_state`) | ban idempotent for agents |
| Ban refused (self/privileged) | 403 `ban_refused` | no privileged-row count leak |
| `ConsumeOutcome` (status contract doc only) | 200 / 204 pending / 410 uniform | `not_found|gone|unbound|lost_race` → one problem (anti-enumeration) |
| DTO validation | 422 `validation_failed`, `errors = pydantic_errors_json(exc)` | `api_bulk` precedent |
| 429 on `/api/v1/` (R1) | 429 `rate_limited` problem + `Retry-After` (derived from `RateLimitBudget.period` in `problem.py`) | legacy surfaces unchanged and keep emitting NO `Retry-After` (verified: `rate_limit_response.py` is a pure formatter; `retry_after` is caller-supplied, production never passes it) |
| Legacy 429 shapes (frozen) | listings/detail = bare 429 (`json=False`), media gate variant, search/autocomplete = `{"error":"rate_limit"}` | preferred-city has no limiter at all |
| Malformed » 400 · unauthenticated » 401 (no `WWW-Authenticate`) · non-owner/consent » 403 · missing-or-invisible » 404 uniform · method » 405 · lock-timeout (55P03) » 503 `retryable` · unexpected » 500 generic | | CWE-209 discipline; HTML-vs-API shape differences (edit 200-form vs 409; reactivation lock-timeout already 503 via middleware) documented in api-surface.md |

Other response contract clauses (folded into api-surface.md at S5.3): lenient Content-Type (body parsed as JSON regardless of header — `api_bulk.py:74` norm; if strictness is ever added, one shared 415 in `problem.py`, never per-view); only `Retry-After` contractually on 429 (no `X-RateLimit-*`); `/api/v1/` reads uncacheable-by-default (no `Vary`/`Cache-Control` contract yet — guard against future locale-merging caches); analytics side effects listed as agent-visible behavior.

---

## 3. Prioritized, phased implementation roadmap

39 tasks = 38 mandatory + 1 optional (S5.2). Every task: fast gate green at handoff, `ruff` + `basedpyright` clean on its paths, migration tripwire clean, i18n completeness green when strings land, api-surface.md row appended, pairing table row registered in `test_import_rule.py` (endpoint tasks). Extraction tasks prove byte-identical behavior via untouched existing tests. No task edits an existing HTML-parsing test. Effort: S/M/L.

### Stage S0 — Contract overturn + scaffolding (2M+3S)

**S0.1 — Overturn the single-consumer doc contract [M]** · Rewrite `config/urls.py:15-18` comment; rewrite `docs/01-spec/architecture-structure.md` §API Surface Contract; update `spec-index.md` + `README.md`; create `docs/01-spec/api-surface.md` skeleton (endpoint table, auth model, error taxonomy incl. both 429 realities, budgets, i18n rules, planned stances). Deps: —. Verify: doc-rules check; fast gate. AC: no stale "single consumer"/"DRF deferred" phrasing; doc-maintenance checklist passes.

**S0.2 — Mount /api/v1/; URL-only aggregator; import-rule harness [M]** · Create `apps/api/__init__.py`, `apps/api/urls.py` (empty, docstring: URL-aggregator-only), `apps/api/tests/{__init__.py, test_urls.py (404 smoke + aggregator purity), test_import_rule.py (R-F2 ast harness: declared API→mirror pairing table + allowlist {problem, api_auth, stdlib/django}; empty at S0, rows added per endpoint)}` · modify `config/urls.py` (include) · delete empty `apps/api/serializers/`, `apps/api/views/`. Deps: S0.1. Verify: targeted `test_urls.py`; fast gate. AC: `/api/v1/*` 404; `apps.api.urls` has no non-django imports (tested); `INSTALLED_APPS` unchanged; harness runs with zero rows green.

**S0.3 — `apps/core/utils/problem.py` [M]** · `problem(status, type, detail)` + `validation_problem(exc)` (422, wraps `pydantic_errors_json`) + `rate_limited_problem(budget)` (429 problem, `Retry-After` from `RateLimitBudget.period` — computed here, per A8; **`rate_limit_response.py` untouched, zero diff**). Tests `apps/core/tests/test_problem_response.py` (unit). Deps: —. AC: all §2.5 outcomes constructible; legacy renderer byte-identical with its existing tests untouched; documented: legacy 429s carry no `Retry-After` today, `/api/v1/` adds it (R1 enhancement).

**S0.4 — `apps/core/utils/api_auth.py`: `login_required_api` [S]** · 401 problem for anonymous; identity-before-method ordering mirroring `staff_required_api` (precedent tests: `apps/moderation/tests/test_decorators.py`); no `WWW-Authenticate`. Tests `apps/core/tests/test_api_auth.py` (unit). Deps: S0.3. AC: 401 is a problem document; ordering pinned with phase-15 comment.

**S0.5 — `RateLimitBudget` members `API_PUBLIC_READ`/`API_WRITE` [S]** · `apps/core/enums.py` + docstring rationale; extend `apps/core/tests/test_rate_limit_budget.py` pins; api-surface budget rows. Deps: —. AC: numbers pinned like existing members; no `.env` change.

▸ **M0 GATE:** fast gate green; `/api/v1/` 404-smoked; 5 docs landed; helpers + budgets tested; no HTML diff.

### Stage S1 — Public reads (1L+3M+3S)

**S1.1 — Extract FTS pipeline to `apps/search/services/fts.py` [L]** · Verbatim move (auditor-verified set): `_apply_fts_filtering` (`:326-387`), `_resolve_search_count` (`:390-425`), `_rank_cache_hit_page` (`:428-454`), `_is_single_word` (`:493-507`), `_ids_for_exact_name` (`:510-533`), `_resolve_unique_category` (`:536-552`), `_fuzzy_category_match` (`:555`), **`_fuzzy_match_by_name` (`:579-603`) — added per A4**; `LanguageLocale` becomes an explicit param (the only de-coupling; verified the sole request use is `request.LANGUAGE_CODE` at `:349`). Cache composition (`build_search_cache_key:98`, `get_cached_search_ids:152`, `SEARCH_CACHE_MAX_HITS=1000`), `all_categories` handling, count-cap semantics move unchanged; `_all_categories_requested`, `_record_search_analytics`, city/category suggestion resolution stay view-side. `search()` view becomes a thin caller. `alert_query.py` untouched. `listings.py` untouched (its `_suggest_category` already builds on `apps.categories.services.fuzzy.match_category` directly). Tests `apps/search/tests/test_fts_service.py`; regression proof = untouched search suites. Deps: M0. AC: all pre-existing search tests green unmodified (`test_search_view/fuzzy/cache/rank_page`, `test_fts_sort_order`); vectors only via `LanguageLocale.fts_vector_field`; `apps/search/services/__init__.py` gains NO imports; note lands in `docs/01-spec/api-surface.md` (A9 fix). **Stage close requires `.\Makefile.ps1 test-all`.**

**S1.2 — `-id` tiebreaker in `_apply_sort` [S]** · `apps/ads/services/listings_query.py:278-287` (verified: no unique tiebreaker today → pages genuinely non-deterministic for equal keys); regression note + api-surface ordering note. Tests: equal-key fixtures in `test_listings_sort.py`/`test_price_sort.py`; `test_relevance_tiebreaker.py` proves FTS ranking unaffected. Deps: M0. AC: stable ties in BOTH surfaces via the single shared service; documented as the one approved ordering delta.

**S1.3 — `GET /api/v1/ads/` + exhaustive matrix + parity test [M]** · `apps/ads/api_urls.py` (`app_name="ads_api"`), `apps/ads/views/api/{__init__,listings}.py` + `_serialize_ad`; tests `apps/ads/tests/test_listings_api.py` incl. **`TestExhaustiveFilterSortPageMatrix`** — the single citable owner of the rule-18 "all filters, sorting, pagination" service-matrix clause (O-F5: every `ListingsQueryParams` dimension: category/city/purpose/condition/features × 4 sorts × pages, via the endpoint), the audience-parity case (withdrawn/banned seller invisible), the 429 problem case, and the parity assertion: identical params → JSON `results[].id` == HTML `page_obj` ids (incl. warm-cache path), cap/truncation envelope (`total_count` may be cap+1; `results_truncated` authoritative — O-2b). Register pairing row in `test_import_rule.py`. Deps: S0.2, S0.3, S0.5, S1.2. Verify: targeted + fast gate.

**S1.4 — `GET /api/v1/search/` [M]** · `apps/search/api_urls.py`, `apps/search/views/api/search.py`; consumes `fts.py`; same params incl. `all_categories`; fields: results envelope + `narrowed_category`/`suggested_category`/`suggested_city` + `total_count`/`results_truncated`/`search_cache_max_hits`; analytics + history recorded exactly like HTML (`record_search_history` takes the explicit `session` arg); `?lang` locale-parity test; warm-cache parity. Tests `apps/search/tests/test_search_api.py`. Deps: S1.1, S1.3. Verify: targeted + fast gate + `test-all` at stage close.

**S1.5 — `GET /api/v1/ads/{id}/` [M]** · `apps/ads/views/api/detail.py`; uniform 404 (absent == audience-blocked); `AD_VIEWED` recorded through the JSON path; media as URLs only; favorites state for sessions. Tests `apps/ads/tests/test_ad_detail_api.py`. Deps: S1.3.

**S1.6 — `GET /api/v1/categories/` + `GET /api/v1/cities/` [S]** · **Single modules per A2**: `apps/categories/api_tree.py` (beside the `views.py` MODULE — never a `views/` package there), `apps/locations/api_cities.py` (same one-off convention, stated); `apps/categories/api_urls.py`, `apps/locations/api_urls.py`, tests `test_categories_api.py`, `test_cities_api.py`. **SWR verdict (auditor Check-5): the JSON tree reads category models directly — it must NOT route through the submenu fragment cache (`categories/views.py:41-59` SWR helper caches rendered fragments)**; optionally exposes the tree version. Cities pairing row: mirror = `apps/core/context_processors.header_context` (imports locations models only). Deps: M0.

**S1.7 — S1 i18n catalog batch [S]** · scratch-extract recipe; `ru/bs/en` `.po` manual targeted apply; `test_i18n_completeness.py` green; `git status --short -- src/backend/locale` shows only the three `.po` files. Deps: S1.3–S1.6.

▸ **M1 GATE:** fast gate + `test-all` green; HTML tests unmodified; gaps 1–3 covered.

### Stage S2 — Private reads (4M+4S)

**S2.1 — Extend favorites service [S]** · **`src/backend/apps/ads/services/favorites.py` already exists (hosts `annotate_favorites:20`, 9+ importers) — extend it** with list + toggle functions (A1); rewire `apps/ads/views/favorite.py` + `apps/cabinet/views/favorites.py` as callers. Tests extend `test_favorites.py` (+ badge/visibility/cabinet suites untouched-green). Deps: M1. AC: HTML fragments byte-identical; no model change.

**S2.2 — Extract dashboard grouping [S]** · `apps/ads/services/dashboard_query.py` (grouped querysets per `AdStatus`, same prefetches — from `dashboard.py:70-90`); rewire `dashboard.py`. The consent gate is NOT relocated (A14 decision §2.3): HTML keeps `_seller_may_create_ad`; API re-asserts via `can_create_ad` with equivalence test-pinned. Tests extend `test_dashboard_stats.py`. Deps: M1.

**S2.3 — `GET /api/v1/dashboard/` [M]** · `apps/ads/views/api/dashboard.py`; `?time_range=` with HTML-identical fallback; **R-L1: absent consent → 403 `consent_required` problem — never a silent empty list** (mirrors `dashboard.py` gate; distinguishes "no rows" from "not allowed"); equivalence test: API `can_create_ad` refusal set == HTML gate refusal set. Tests `apps/ads/tests/test_dashboard_api.py`. Deps: S2.2, S0.4, S0.5.

**S2.4 — `GET /api/v1/favorites/` list [S]** · `apps/cabinet/api_urls.py`, `apps/cabinet/views/api/{__init__,favorites}.py`; test **`apps/cabinet/tests/test_favorites_list_api.py`** (renamed per auditor advisory — the ads toggle test gets a distinct name in S3.2). Deps: S2.1, S0.4.

**S2.5 — Moderation queue/review reads [M]** · `apps/moderation/api_urls.py`, `apps/moderation/views/api/reads.py`; `PriorityService.get_queued_ads` + **`get_priority_counts`** (`priority.py:84`, A11); `PriorityFilter.ALL` sentinel = no filter; tests `apps/moderation/tests/test_moderation_api_reads.py` (401/403/405, no `WWW-Authenticate`). Deps: M1; `staff_required_api` unchanged.

**S2.6 — Trust-dashboards reads [M]** · **Hosted in `apps/analytics` per A3** (mirrors `apps/analytics/views/{seller_dashboard:27, moderation_dashboard:29}.py`; services `trust_analytics`, `moderation_analytics`, `seller_stats` all in `apps/analytics/services/`): create `apps/analytics/api_urls.py` (`app_name="analytics_api"`), `apps/analytics/views/api/{__init__,dashboards}.py`, tests `apps/analytics/tests/test_analytics_api.py`. **URLs keep the trust prefix** (`GET /api/v1/trust/seller/` + `GET /api/v1/trust/moderation/` — prefix orthogonal to module host); seller = SESS, moderation = STAFF. Deps: M1, S0.4.

**S2.7 — Saved-searches + search-history list reads [M]** · `apps/cabinet/views/api/{saved_searches,search_history}.py`; **history is SESS-only (A6): HTML mirrors are `@login_required` (`cabinet/views/search_history.py:24-40`), and the cabinet docstring says anon session history is never shown there — the anon readback claim is dropped**; anon session history remains machine-accessible via autocomplete (#4 stance). Tests `apps/cabinet/tests/test_saved_searches_api.py` (both lists; ownership scoping; 401 matrix). Deps: M1, S0.4.

**S2.8 — S2 i18n batch [S]** · as S1.7. Deps: S2.3–S2.7.

▸ **M2 GATE:** fast gate green; gaps 11, 12, 15/16/18 (read halves) covered; auth matrices green.

### Stage S3 — Session writes (3M+3S)

**S3.1 — Extract saved-searches mutator service [M]** · `apps/search/services/saved_searches.py` (create/update/toggle/delete + ownership, on shared `SavedSearchInput`); rewire `apps/search/views/save_search.py` + `apps/cabinet/views/saved_searches.py`; **`telegram_bot/services/alerts.py` untouched (token protocol by design)**. Tests: extend `test_saved_search_create.py` + new `apps/search/tests/test_saved_search_service.py`; `test_alert_query.py`/`test_alert_delivery.py` untouched-green. Deps: M2.

**S3.2 — Favorites toggle endpoint [S]** · `apps/ads/views/api/favorites.py`; test **`apps/ads/tests/test_favorite_toggle_api.py`** (disambiguated name); 200 `{active,count}`; uniform 404; `API_WRITE`. Deps: S2.1, S0.3, S0.4.

**S3.3 — Consent endpoints + logout [M]** · `apps/users/api_urls.py`, `apps/users/views/api/consent.py`; services request-free; accept/decline anon-allowed (HTML parity), withdraw SESS and still `logout()`s; cookie orchestration stays HTML. Tests `apps/users/tests/test_consent_api.py`; `test_consent.py`/`test_logout.py` untouched-green. Deps: S0.3, S0.4, S0.5.

**S3.4 — Saved-searches write endpoints [M]** · cabinet API: create/toggle/edit/delete on the S3.1 service; 422 via DTO; uniform 404 cross-owner; idempotent toggle. Tests extend `test_saved_searches_api.py`. Deps: S3.1, S0.3, S0.4.

**S3.5 — Search-history clear endpoint [S]** · `POST /api/v1/search-history/clear/` — **SESS-only (`login_required_api`, A6)**; 204; DB-clear parity with the cabinet HTML clear. Tests extend `test_saved_searches_api.py`. Deps: S2.7.

**S3.6 — S3 i18n batch [S]** · as S1.7. Deps: S3.2–S3.5.

▸ **M3 GATE:** fast gate green; gaps 15, 16, 18, 20, 22 fully covered; cabinet/consent HTML suites untouched-green.

### Stage S4 — Ad lifecycle + moderation writes (1L+5M+2S)

**S4.1 — Extract `apps/ads/services/lifecycle.py` [M]** · archive/reactivate/delete orchestration (ownership, `select_for_update`, `transition_to`, reactivate's `auto_moderate` decision identical to the view); **views stay consent-gate callers** — the service carries state mechanics only, consent/audience gates remain caller-side mirrors (HTML and API both assert at their boundary). Rewire `edit.py`, `delete.py`. Tests: new `apps/ads/tests/test_lifecycle_service.py`; existing lifecycle/edit/delete suites untouched-green. Deps: M3.

**S4.2 — Extract the edit-flow helper [L]** · `apps/ads/services/edit_flow.py` encodes **all FIVE outcome families (A5)**: (1) ARCHIVED-reactivation → `submit_ad`; (2) PUBLISHED text-change → `submit_ad`; (3) PUBLISHED price-only → direct `_apply_price_change`; (4) DRAFT/ON_MODERATION direct-save (`EDITABLE_DIRECT_SAVE_STATUSES`, `edit.py:63-65/:364-379` — distinct from both); (5) explicit refusal for other statuses (`:380-397`) → API maps to **409 `not_editable`** (HTML re-renders 200 — deliberate documented mapping). Status→branch table pinned equal to today's view logic; price-only/direct-save never funneled through `submit_ad` (frozen); lock-timeout stays the documented exception (`:398-412`; API 503 `retryable`, HTML edit re-renders 200, reactivation already 503 via `DbLockTimeoutMiddleware` — differences documented). Rewire `edit.py` (view keeps forms/messages); tests `apps/ads/tests/test_edit_flow.py` + `test_edit.py`, `test_edit_views_locking.py`, `test_submission.py` untouched-green. Deps: S4.1.

**S4.3 — Lifecycle endpoints [M]** · `apps/ads/views/api/lifecycle.py`: archive (`SESS+owner+**consent**` per A7 → consent-refused archive test: 403 `consent_required`), reactivate (SESS+owner+consent), delete (SESS+owner, gate-free). 409/204/503 mappings; FSM-integrity tests (DRAFT dialog rows exactly as the UI leaves them). Tests `apps/ads/tests/test_lifecycle_api.py`. Deps: S4.1, S0.3, S0.4.

**S4.4 — Edit endpoint [M]** · `apps/ads/views/api/edit.py`; `AdEditInput`-family DTO → edit-flow helper; five-branch outcome matrix incl. the banned-seller relist mirror of `TestBannedSellerRelistKnownGap` (asserting current behavior, not the phase-15 fix); lock-timeout → 503. Tests `apps/ads/tests/test_edit_api.py`. Deps: S4.2, S0.3.

**S4.5 — Submit-on-draft endpoint [M]** · `apps/ads/views/api/submit.py`; `submit_ad` on an existing DRAFT; full `SubmitAdOutcome` matrix over JSON; consent via the shared `can_create_ad` inside `submit_ad` (→ 403 `consent_required`); dialog/photo staging stays bot-only (documented stance). Tests `apps/ads/tests/test_submit_api.py` + `test_submission.py` + bot suites untouched-green. Deps: S4.1, S0.3.

**S4.6 — Copy endpoint [S]** · `apps/ads/views/api/copy.py` via `copy_ad`; **A10: acceptance anchored to real semantics — `copy_service.py:39` via `_build_ad_copy:15`; the result is a new DRAFT owned by the seller; max-ads + consent predicates as in the bot flow** (the `next_ad_sort_key` clause is deleted — symbol nonexistent). Tests `apps/ads/tests/test_copy_api.py` (+ `test_copy_ad.py` untouched-green). Deps: S0.3, S0.4.

**S4.7 — Moderation single-action endpoints [M]** · `apps/moderation/views/api/actions.py`; `admin_actions` unchanged; §2.5 mappings (`ApproveOutcome`, `BanResult`); bulk endpoint untouched (frozen public shape); moderator action-log + analytics side effects identical to HTML actions. Tests `apps/moderation/tests/test_moderation_api_actions.py` (+ `test_admin_actions.py`, `test_approve_ad_side_effects.py`, `test_moderation_side_effects.py` untouched-green). Deps: S2.5, S0.3.

**S4.8 — S4 i18n batch [S]** · as S1.7. Deps: S4.3–S4.7.

▸ **M4 GATE:** fast gate green; gaps 5 (HTTP tier), 6, 7, 8, 9, 10, 13 covered; no bot test modified.

### Stage S5 — Compliance instruments + close-out (3M+2S)

**S5.1 — `verify_parity` management command [M]** · `apps/core/management/commands/verify_parity.py`; read-only service-query replay (listings/sort/page/search/detail + audience predicates), zero DB writes/no analytics (the poll-safe tier), `--json` for CI; **never scheduled — no `HOURLY_COMMANDS`/`DAILY_COMMANDS` change; `test_scheduler.py`/`test_sweep_lock_structure.py` untouched**. Tests `apps/core/tests/test_verify_parity.py`; invocation documented in `.kilo\rules\commands.md` + api-surface.md. Deps: M4. (Deferred optional: Locust targets — §6.)

**S5.2 — e2e Playwright scaffolding [S, OPTIONAL — droppable]** · `uv add --dev playwright` (the only permitted dev dep); `pyproject.toml` markers += `e2e`; `apps/core/tests/e2e/` with `pytest.importorskip("playwright")` — fast gate skips, never fails. Scope per D7 (a11y, visual regression, HTMX swap, real Telegram login round-trip). Dropping it changes nothing for rule-18 compliance. Deps: M4.

**S5.3 — Docs close-out [M]** · `docs/99-agent/architecture.md` gains the API-parity seam section (§2.3 layout, import rule + frozen-edge allowlist, R-F2 pairing-table pointer); `docs/01-spec/api-surface.md` finalized: all endpoint rows, error taxonomy, budgets, i18n rules, **O-2a commit-boundary rule, O-2b cap+1 semantics, O-2c agent-visible analytics side effects (track= deferred with trigger), O-2d uncacheable-by-default, O-2e Retry-After-only, O-2h lenient Content-Type**, five-branch edit + lock-timeout HTML-shape differences, dual 429 realities (incl. "legacy emits no Retry-After"), **stances (auditor Check-4)**: #21 machine-contract login/status; #23 contact deep-link; #24 support bot-only callable; #25 `?lang`; #26 media URLs; #27 no index endpoint; #17 alert delivery with the agent-visible substitute (`SavedSearchNotification.delivered_at` readable via `verify_parity`/shell tier — O-4L2); `/privacy/` = legal document, HTML-only; category submenu partial = internal HTMX render whose machine form is `GET /api/v1/categories/`; cabinet hub/settings/badge = navigation/render fragments, no data contract; cities mirror = context processor. `spec-index.md`/`README.md` cross-checked. Deps: S5.1, all endpoint tasks.

**S5.4 — Fix the stale scheduler-pins sentence in architecture.md [S]** · one-line correction (R4): the "exact-`==` pinned lists" claim → actual pins (`test_scheduler.py`: len/uniqueness/`DAILY_HOUR_UTC==8`; sweep-name sets in `test_sweep_lock_structure.py`). Zero code diff. Deps: after S5.3 merges.

**S5.5 — Final compliance run [M]** · execute §4 checklist end-to-end; record per-action DoD evidence (test-file refs) in api-surface.md's compliance section; gap-register re-audit table (28 rows: covered / frozen-covered / stanced). Verify: `.\Makefile.ps1 test` + `test-all` green; `verify_parity --json` exit 0; `uv run ruff check src/`; `uv run basedpyright src/backend/apps`; migration tripwire clean; `git grep csrf_exempt src/` empty; no new auth/env/middleware.

▸ **M5 GATE:** fast gate + full suite green; §4 checklist fully checked; compliance recorded.

**Critical path:** S0.2 → S0.3 → **S1.1 (L)** → S1.3/S1.4 → S3.1 → **S4.2 (L)** → S4.4 → S5.1 → S5.5. The two L tasks dominate scheduling.

### File inventory (new/modified per stage — executor's full change surface)

| Stage | New | Modified |
|---|---|---|
| S0 | `apps/api/{__init__,urls}.py`, `apps/api/tests/{__init__ + test_urls + test_import_rule}.py`, `apps/core/utils/problem.py`, `apps/core/utils/api_auth.py`, `apps/core/tests/{test_problem_response,test_api_auth}.py`, `docs/01-spec/api-surface.md` | `config/urls.py` (comment + include), `docs/01-spec/architecture-structure.md`, `docs/01-spec/spec-index.md`, `README.md`, `apps/core/enums.py`, `apps/core/tests/test_rate_limit_budget.py` · **deleted:** empty `apps/api/serializers/`, `apps/api/views/` |
| S1 | `apps/search/services/fts.py` + `test_fts_service.py`, `apps/ads/{api_urls.py, views/api/{__init__,listings,detail}.py}` + `test_listings_api.py` + `test_ad_detail_api.py`, `apps/search/{api_urls.py, views/api/{__init__,search}.py}` + `test_search_api.py`, `apps/categories/{api_urls.py, api_tree.py}` + `test_categories_api.py`, `apps/locations/{api_urls.py, api_cities.py}` + `test_cities_api.py`, `apps/api/urls.py` (includes) | `apps/search/views/search.py` (thin caller; rate-limit entry block `:88-89` untouched), `apps/ads/services/listings_query.py` (`_apply_sort`), `apps/api/tests/test_import_rule.py` (pairing rows), locale `{ru,bs,en}/LC_MESSAGES/django.po` |
| S2 | `apps/ads/services/dashboard_query.py`, `apps/ads/views/api/dashboard.py` + `test_dashboard_api.py`, `apps/cabinet/{api_urls.py, views/api/{__init__,favorites,saved_searches,search_history}.py}` + `test_favorites_list_api.py` + `test_saved_searches_api.py`, `apps/moderation/{api_urls.py, views/api/reads.py}` + `test_moderation_api_reads.py`, `apps/analytics/{api_urls.py, views/api/{__init__,dashboards}.py}` + `test_analytics_api.py` | `apps/ads/services/favorites.py` (**extend**), `apps/ads/views/favorite.py`, `apps/cabinet/views/favorites.py`, `apps/ads/views/dashboard.py`, `apps/api/urls.py`, catalogs |
| S3 | `apps/search/services/saved_searches.py` + `test_saved_search_service.py`, `apps/ads/views/api/favorites.py` + `test_favorite_toggle_api.py`, `apps/users/{api_urls.py, views/api/{__init__,consent}.py}` + `test_consent_api.py`, cabinet API write extensions | `apps/search/views/save_search.py`, `apps/cabinet/views/saved_searches.py`, `apps/cabinet/views/api/{saved_searches,search_history}.py`, catalogs; **untouched:** `telegram_bot/services/alerts.py` |
| S4 | `apps/ads/services/{lifecycle,edit_flow}.py` + `test_lifecycle_service.py` + `test_edit_flow.py`, `apps/ads/views/api/{lifecycle,edit,submit,copy}.py` + `test_lifecycle_api.py` + `test_edit_api.py` + `test_submit_api.py` + `test_copy_api.py`, `apps/moderation/views/api/actions.py` + `test_moderation_api_actions.py` | `apps/ads/views/edit.py` + `apps/ads/views/delete.py` (rewired, behavior-identical), catalogs |
| S5 | `apps/core/management/commands/verify_parity.py` + `test_verify_parity.py`; optional `apps/core/tests/e2e/` | `docs/99-agent/architecture.md` (§seam; §scheduler sentence), `docs/01-spec/api-surface.md` (finalize), `.kilo\rules\commands.md` (verify_parity invocation), `pyproject.toml` (markers, S5.2 only) |

### Exit-gate checklists (milestones — verify before proceeding)

- [ ] **M0:** fast gate green · `/api/v1/` 404 for arbitrary paths (smoke) · aggregator purity + import-harness green · `$dev` migration tripwire clean · 4 doc files + api-surface skeleton landed · no HTML diff.
- [ ] **M1:** fast gate + `test-all` green · every pre-existing search/sort test unmodified-green · parity test green (incl. warm-cache) · catalogs: stage msgids complete, i18n gate green · gaps 1, 2, 3 covered.
- [ ] **M2:** fast gate green · favorites/cabinet/consent HTML suites untouched-green · 401/403/405 matrices green for every private endpoint · gaps 11, 12 covered + 15/16/18 read halves.
- [ ] **M3:** fast gate green · bot alert stack diff-free · gaps 15, 16, 18, 20, 22 closed · rewire tasks byte-identical per untouched suites.
- [ ] **M4:** fast gate green · five-branch edit matrix pinned · consent-refused archive case green · FSM-integrity + moderation side-effect tests green · no bot test modified · gaps 5, 6, 7, 8, 9, 10, 13 closed.
- [ ] **M5:** fast gate + `test-all` green · `verify_parity --json` exit 0 · `git grep csrf_exempt src/` empty · scheduler pin suites untouched-green · §4.4 project gates all checked · compliance section recorded in api-surface.md.

---

## 4. Task dependencies, risks, and acceptance criteria

### 4.1 Dependencies

| Edge | Nature |
|---|---|
| M0 (S0.1–S0.5) → everything | mount, helpers, budgets, docs contract |
| S1.1 → S1.4; S1.2 → S1.3 | extraction strictly before consumer; tiebreaker before deterministic asserts |
| S1.1 → S1.3/S1.5 (serializer/envelope conventions) | soft |
| S2.1 → S2.4/S3.2; S2.2 → S2.3; S3.1 → S3.4; S4.1 → S4.3; S4.2 → S4.4 | extraction before endpoints |
| Endpoint tasks → own api-surface row + `test_import_rule.py` pairing row + own catalog msgids (stage i18n batches last) | per-stage batching |
| S5.1 after all endpoints; S5.3 after S5.1; S5.5 after all | instruments + close-out |
| Docs: S0.1 overturn BEFORE any endpoint ships (Q5); `api-surface.md` maintained per stage (each endpoint task appends its row) | DoD |
| Settings/env: none (budget numbers = StrEnum property dicts) · migrations: none (tripwire each gate) · scheduler pins: untouched | constraints |

### 4.2 Risks → mitigating tasks

| Risk | Mitigation |
|---|---|
| audit 1 FTS extraction behavior change (HIGH) | S1.1 verbatim move (verified-complete list incl. `_fuzzy_match_by_name`); untouched suites = regression proof; `test-all` at M1 |
| audit 2 request/session/CSRF/locale coupling | S0.3/S0.4 helpers; API views read the same middleware-resolved state as mirrors; D3 (no exemption; `Client()` tests) |
| audit 3 auth model blocks headless writers | frozen posture (D3/D7); optional S5.2 for the real login round-trip |
| audit 4 bot-FSM corruption via API writes (MED-HIGH) | S4.1–S4.5 — writes only via `transition_to`/`submit_ad`/edit-flow; FSM-integrity tests; no direct status writes |
| audit 5 i18n coupling of service errors | typed `type` tokens; cataloged `detail`s; stage i18n batches + completeness gate |
| audit 6 import cycles (MED-HIGH) | URL-only aggregator + **mechanical import-subset test (R-F2)** + frozen tripwires untouched |
| audit 7 cache invalidation seams | S1.1 keeps `build_search_cache_key`/`get_cached_search_ids` verbatim; warm-cache parity test |
| audit 8 rate-limit abuse economics | dedicated API budgets (S0.5); R1 problem rendering; nginx edge untouched |
| audit 9 legacy vs per-language vectors | S1.1/S1.4 pin `LanguageLocale.fts_vector_field` only |
| audit 10 interface asymmetry / drift | single-stack extractions: S2.1 (favorites extend), S2.2, S3.1, S4.1, S4.2 |
| audit 11 django-filter dead dep | NOT mitigated in-program — owner decision (§6, R3) |
| audit 12 HTML-coupled tests + CSRF | no HTML-test edits (guard); parity tests add JSON equivalents; CSRF contract tested via `Client()` |
| P1 cache-semantics drift | moved count/rank code + `results_truncated` envelope; warm-cache parity |
| P2 locale-resolution drift | no per-view locale code; `?lang` middleware chain test-pinned |
| P3 pagination parity w/ capped totals | cap+1 semantics tested + documented (O-2b) |
| P4 analytics inflation by polling | dedicated budgets + api-surface guidance + `verify_parity` as the poll-safe tier; revisit trigger documented |
| P5 bulk public-contract drift | frozen; single actions live at new URLs (S4.7) |
| P6 404/410 existence leakage | uniform bodies; single 410 problem for all consume refusals |
| P7 `-id` tiebreaker ordering delta | isolated, approved (R2), documented — the only ordering delta |
| P8 namespace collision | `<app>_api` namespaces (verified non-colliding); reverse test |

### 4.3 Execution guards

1. One implementor at a time; strict dependency order; every task ends with the fast gate green. Never bare `uv run pytest` locally.
2. **Frozen — never touch:** `apps/users/services/__init__.py`; `apps/search/services/__init__.py` (no import additions); the two `login_token` claim/consume predicates; `MIDDLEWARE` (15 pinned entries); scheduler lists `HOURLY_COMMANDS`(10)/`DAILY_COMMANDS`(3) + both pin suites; `staff_required_api` (incl. no-`WWW-Authenticate` + identity-before-method, phase 15 owns reorders); HTMX URLs/templates/fragments; `apps/ads/views/edit.py` view privates as import sources (use the shared `can_create_ad` seam); bulk endpoint response shape; legacy 429 answers — listings/detail bare 429, media-gate variant, search/autocomplete `{"error":"rate_limit"}` (preferred-city has NO limiter — nothing to freeze); `alert_query.py`; `telegram_bot/services/alerts.py`.
3. **Import rule (mechanical):** API view imports ⊆ mirrored HTML view's imports (+ allowlist `apps.core.utils.problem`, `apps.core.utils.api_auth`, stdlib/django). Enforced by `apps/api/tests/test_import_rule.py`; every endpoint task adds its pairing row.
4. Writes: POST-only; no `csrf_exempt`; sessions the only non-staff credential; no new auth; no env vars; lenient Content-Type norm; if 415 ever added — once, in `problem.py`.
5. i18n: scratch-extract recipe only; English msgids; ru/bs non-empty; completeness gate each stage.
6. Deps: no runtime deps; `uv add --dev playwright` only in S5.2 (optional).
7. Migrations: none expected — pinned tripwire form (§0 preamble) must be clean at every gate; any migration diff = stop.
8. Review discipline: extractions prove byte-identical behavior via untouched tests; endpoints must show §2.5 mapping tests + auth matrix + pairing row.

### 4.4 Acceptance criteria — what "done" means

**Per-action DoD (every endpoint row of §2.4):** (1) programmatic surface exists at the planned endpoint or the stance is documented in api-surface.md; (2) it calls the same service/extraction as its HTML or bot mirror — no API-only business predicate, no HTML-view-private imports; (3) a browserless test asserts it: service-level + `Client()` JSON structured asserts (auth matrix, ownership, at least one consent/ban/deletion predicate case); (4) errors follow §2.5 (stable `type`, cataloged `detail`, uniform 404/410, R1 429); (5) new strings are msgids in ru/bs/en, completeness gate green; (6) api-surface.md row + import-rule pairing row updated in the same stage.

**Project gates:** fast gate green at every stage boundary; `test-all` green at M1 and M5; zero HTMX UI behavior change (no URL/template/middleware diff; only the R2 ordering delta); migration tripwire clean everywhere; no new runtime deps (Playwright dev-only behind opt-in `e2e`, skipped via `importorskip`); no new env vars/auth/`csrf_exempt`/`WWW-Authenticate`; scheduler sets untouched; both 429 realities documented (R1); doc contract overturned + current (urls.py, architecture-structure, spec-index, README, api-surface, architecture seam section); `verify_parity --json` exit 0 in CI; gap register re-audit: every row covered, frozen-covered, or stanced with evidence.

---

## 5. API/CLI-first testing and verification strategy

**Layered model (researcher §3 + roadmap):**

| Layer | What | Where | Gate |
|---|---|---|---|
| 1. Service matrix (unit/integration) | exhaustive parametrized filters × sorts × pages on `ListingsQuery` + FTS determinism per locale (`LanguageLocale.fts_vector_field`/`fts_config`) | `test_listings_api.py::TestExhaustiveFilterSortPageMatrix` (O-F5 named owner) + `test_fts_service.py` + existing service suites | fast gate |
| 2. `Client()` JSON tests (integration) | every endpoint: structured field asserts, auth matrix (PUB/SESS/STAFF, ownership, consent/ban predicates), §2.5 error mappings, R1 429 problem | `test_*_api.py` per app (renames: `test_favorites_list_api.py`, `test_favorite_toggle_api.py`) | fast gate |
| 3. Parity tests | identical params → JSON `results[].id` == HTML `page_obj` ids, incl. warm-cache path; locale parity via `?lang`; analytics/history side-effect parity | `test_listings_api.py`, `test_search_api.py`, `test_ad_detail_api.py` | fast gate |
| 4. Regression = untouched suites | every extraction's byte-identical proof is the pre-existing HTML suite running unmodified | search/edit/lifecycle/favorites/cabinet/consent suites | fast gate |
| 5. `verify_parity` CLI | read-only service replay, zero DB writes/no analytics, `--json` for CI + agents | `test_verify_parity.py` (S5.1) | CI (not fast gate; never scheduled) |
| 6. Opt-in e2e (Playwright) | a11y, visual regression, HTMX partial-swap, real Telegram login round-trip ONLY | `apps/core/tests/e2e/` (S5.2, optional) | opt-in `-m e2e` |

**Browserless (rule-18) coverage:** every user-facing action, all filters/sorting/pagination/search — layers 1–3 + 5. **e2e covers only** what browserless cannot: accessibility, visual, HTMX swap behavior, the Telegram round-trip (D7). **CI mapping:** fast gate = `.\Makefile.ps1 test` (`PYTEST_SKIP_MARKERS=seed`); S1/S5 = `test-all` (seed suite, FTS + seeding paths); targeted runs via `$dc` + `PYTEST_OPTS` (word-split caveat); lint/typecheck/i18n-completeness/migration-tripwire per task; `e2e` registered in `pyproject.toml` markers at S5.2, auto-skipped in the fast gate.

---

## 6. Deferred decisions and optional items (owner: Tech Lead)

| Item | Status | Trigger |
|---|---|---|
| `django-filter>=26.2` dead dependency | deferred (R3) | `uv remove` (zero `src/` impact) vs ratify as future substrate; spec-stack question `spec-index.md:47` |
| D3 secret-header write decorator | contingency only | a concrete out-of-process writer need appears → separate auth-model review; nothing in the 38 activates it |
| Playwright/e2e adoption | optional task S5.2 (droppable) | compliance unaffected if dropped; D7 scope preserved |
| Legacy-429-shape unification | not planned | pinned on legacy surfaces until an external consumer of those routes asks |
| O-3index: `GET /api/v1/` static index endpoint | deferred | autonomous-agent discoverability beyond docs; ~S if wanted; docs-only is the ratified D2 default |
| O-3locust: add `/api/v1/ads/` + `/api/v1/search/` Locust targets | deferred | reuses `src/benchmark/` SLO gate; cheap, on-pattern |
| O-obs: API endpoint logging expectations | deferred | one-line expectation (log refusals/writes at mirror level) when adopted |

**Rejected alternatives registry (researcher §7c — verbatim; do not re-litigate):**
`page_token`/cursor pagination — breaks HTML parity; `-id` tiebreaker suffices. · `X-RateLimit-Limit/Remaining/Reset` headers — `Retry-After` is enough for v1; new surface. · Header/media-type versioning beyond `/v1/` — one consumer; prefix is the established convention. · `Accept-Language` locale negotiation as new work — already provided by shared middleware; nothing to build. · `track=` analytics opt-out parameter — grows the public contract for a hypothetical; deferred with a documented trigger. · Per-view `Content-Type` 415 checks — drift from the `api_bulk.py` norm; only a single shared `problem.py` implementation would ever be acceptable. · Full OpenAPI (django-ninja) — D2 ratified deferral; adds framework + RFC-9457 rework for no v1 need.

---

## Appendix A — Phase-5 resolution ledger

| Finding | Where landed |
|---|---|
| Auditor A1 (favorites extend, not create) | §2.3 Q2; S2.1 |
| A2 (categories single-module; locations convention) | §2.3 layout table; S1.6 |
| A3 (trust dashboards host in apps/analytics; URLs keep /trust/) | §2.3 layout; S2.6; §2.4 inventory |
| A4 + A9 (move list + doc path) | S1.1 (move list incl. `_fuzzy_match_by_name`; `docs/01-spec/api-surface.md`) |
| A5 (five-branch edit; refusal + lock-timeout mappings) | §2.4 row 6; §2.5; S4.2/S4.4 |
| A6 (search-history SESS-only) | §2.4 row 18; S2.7; S3.5 |
| A7 (archive consent-gated) | §2.4 row 7; §2.3 consent seam; S4.3 |
| A8 (no legacy Retry-After; problem.py derives it; legacy file untouched) | S0.3; §2.5 429 rows; §4.3 guard 2 |
| A9 fold | S1.1 |
| A10 (copy semantics; drop `next_ad_sort_key`) | §2.4 row 10; S4.6 |
| A11 (`get_priority_counts`) | §2.4 row 12; S2.5 |
| A12 (pinned migration-tripwire invocation) | §0 preamble; §4.3 guard 7 |
| A13 + A15 (legacy-429 list corrected; import-rule rewording) | §2.5 legacy rows; §2.3 import rule; §4.3 guards 2–3 |
| Advisories: `apps/api/__init__.py`; SWR verdict; /privacy/-submenu-hub-settings-badge stances; test-name disambiguation; A14 consent via `can_create_ad` | S0.2; S1.6 + S5.3; S5.3; S2.4/S3.2 test names; §2.3 + S2.3/S4.3 |
| Researcher R-F2 (mechanical import rule) | §2.3; S0.2 (`test_import_rule.py`); §4.3 guard 3 |
| R-L1 (403 consent, never empty list) | §2.4 row 11; S2.3; §4.4 |
| O-2a/2b/2c/2d/2e/2h, O-F5, O-4L2 | folded: §2.5 contract clauses; S1.3 (matrix owner + O-2b tests); S1.4/S1.5 (side-effect asserts); S5.3 (all doc lines incl. L2 stance) |
| O-3index / O-3locust / O-obs | §6 deferred |
| Task count | unchanged: 39 (38 mandatory + S5.2 optional) |

## Appendix B — Working-document index (`.ai\tmp\api-parity\`, historical inputs to this plan)

| Document | Role |
|---|---|
| `C:\py_dev\mko_bazuna\.ai\tmp\api-parity\phase1-audit.md` | Phase 1 — action inventory (28), embedded-logic findings, gap register §7 (rows 1–28 used in §1), migration risks §8 (1–12 used in §4.2) |
| `C:\py_dev\mko_bazuna\.ai\tmp\api-parity\phase2-research.md` | Phase 2 — pattern verdicts per area, testing guidelines §3 (basis of §5), incremental adoption §4, D1–D7 drafts |
| `C:\py_dev\mko_bazuna\.ai\tmp\api-parity\phase3-strategy.md` | Phase 3 — six-stage strategy, endpoint/error/inventory design (§2 supersedes it with corrections) |
| `C:\py_dev\mko_bazuna\.ai\tmp\api-parity\phase4-roadmap.md` | Phase 4 — 39-task roadmap (§3 supersedes it with the Phase-5 resolutions applied; file carries a SUPERSEDED banner) |
| `C:\py_dev\mko_bazuna\.ai\tmp\api-parity\phase5-audit-validation.md` | Phase 5a — auditor: verdict + 12 required edits (A1–A15) + advisories — all incorporated (Appendix A) |
| `C:\py_dev\mko_bazuna\.ai\tmp\api-parity\phase5-research-validation.md` | Phase 5b — researcher: fit-with-adjustments; R-F2, R-L1, optionals O-2*/O-F5/O-3index/O-3locust/O-obs + rejected-alternatives registry (§6 records it verbatim) |

*This plan (`C:\py_dev\mko_bazuna\.ai\plans\api-parity-migration-plan.md`) is the sole execution-ready document; the six files above are working history and remain authoritative only for their original evidence.*
