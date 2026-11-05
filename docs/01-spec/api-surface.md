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

# Mko Bazuna — Retained JSON Surfaces

> **Contract reference for the retained JSON routes.** The site is HTMX/MPA and ad posting is
> bot-first; there is no general-purpose `/api/v1/` JSON mirror. This file documents the legacy
> JSON interfaces that remain, their auth, error and rate-limit behaviour, and the operational
> endpoints. OpenAPI is deliberately not produced — this document is the contract. Source layout
> is stated in [`architecture-structure.md`](architecture-structure.md).

## Purpose

Specify the JSON interfaces the application still exposes alongside the HTMX/MPA site and the
Telegram bot: the frozen legacy routes (moderation bulk-action, search autocomplete,
preferred-city, the login token protocol) and the operational endpoints (health, metrics, admin,
media).

## Main Concepts

- **Style:** plain Django JSON views; **no DRF, no django-ninja.** The moderation bulk endpoint is
  the reference precedent.
- **Mounting:** every retained JSON route is declared in its own app's `urls.py` and mounted by
  the ordinary root includes — there is no root aggregator and no `api/` app.
- **Writes:** POST-only where an endpoint writes.
- **Errors:** the legacy shapes are frozen and per-endpoint (bare 429, `{"error":"rate_limit"}`,
  the moderation bulk report document).
- **Audience parity:** public reads reuse the same `account_state_q` predicate as the HTML
  surface, so visibility matches by construction.

## Status legend

- **covered/frozen** — behavior exists today and its shape is **frozen** (not to be changed).

## Endpoint inventory

Auth categories: **PUB** = anonymous + `account_state_q` audience; **SESS** = session cookie;
**STAFF** = staff session. Only the retained routes below exist:

| # | Action | Service | Endpoint · Method | Auth | Error notes | Status |
|---|---|---|---|---|---|---|
| 4 | Autocomplete | (existing) | unchanged `/api/search/autocomplete` | PUB | legacy 429 `{"error":"rate_limit"}` | covered/frozen |
| 14 | Bulk | (existing) — **frozen shape** | unchanged `/moderation/api/v1/bulk-action/` | STAFF | per-id errors report; no limiter | covered/frozen |
| 17 | Alert delivery | `send_alerts` + services | unchanged (bot digest + scheduler) | — | stance: no HTTP endpoint; agent-visible substitute is `SavedSearchNotification.delivered_at` (read via the shell/ORM tier) | covered/frozen |
| 19 | Preferred-city | (existing) | unchanged `/api/preferred-city/` | anon + consent cookie | **no rate limiter exists** | covered/frozen |
| 21 | Login issue/status | `issue/consume_token` (predicates frozen) | `/login/issue/` + `/login/status/` (200/204/410) | anon | uniform 410, anti-enumeration | covered/frozen |
| 23 | Contact seller | bot-only by design | deep-link protocol — detail payload carries the `t.me` link | — | stance: no HTTP endpoint | covered/frozen |
| 24 | Support ticket | bot writer only (06-PII-101) | in-process callable; no HTTP intake | — | stance: bot-only support intake | covered/frozen |
| 26 | Media | `media_gate` | unchanged; **URLs only** in payloads | — | binary protocol | covered/frozen |
| 27 | Ops/metrics | `core/views` | health/readiness + `/metrics` (loopback-gated) | — | — | covered/frozen |
| 28 | Admin actions | `admin_actions` | unchanged staff-web | — | — | covered/frozen |

## Auth model

| Category | Enforcement | Notes |
|---|---|---|
| **PUB** | anonymous allowed; audience predicate `account_state_q` applied | visibility identical to the HTML surface (withdrawn/banned sellers invisible) |
| **SESS** | Django session cookie (`@login_required` on the HTML views) | — |
| **STAFF** | `staff_required_api` (`apps/moderation/views/decorators.py`) | plain `{"error": …}` body; identity checked before the method |

- **Sessions are the only credential.** No new auth scheme; the Django session cookie is the sole
  credential.
- **Browserless testing:** headless verification rides Django `Client()` (CSRF disabled in
  pytest), never a new auth scheme.

## Errors (retained shapes)

The legacy JSON routes keep their frozen shapes:

| Route | Shape | Notes |
|---|---|---|
| Moderation bulk-action | 200 report document with per-id `errors`; 403/405 plain `{"error": …}` | `api_bulk.py`; validation errors rendered `422` with `errors = pydantic_errors_json(exc)` (`apps/core/utils/sanitize.py`) |
| Autocomplete (429) | `{"error":"rate_limit"}` | frozen legacy 429 shape |
| Listings / detail HTML 429 | bare `429` (`json=False`) | frozen |
| Media gate 429 | its own variant | frozen |
| Preferred-city | — | no rate limiter at all |
| Login status | 200 issued / 204 pending / 410 uniform | `not_found` / `gone` / `unbound` / `lost_race` collapse to one response (anti-enumeration) |
| Lock timeout (PostgreSQL `55P03`) | 503 via `DbLockTimeoutMiddleware` | HTML shape, unchanged |

Legacy 429s carry **no** `Retry-After` (`rate_limit_response.py` is a pure formatter and production never supplies `retry_after`).

## Rate-limit budgets

Budgets are `RateLimitBudget` StrEnum members (`apps/core/enums.py`); the numbers live in the enum
property dicts, never in environment variables. The shared `rate_limit_check` + `RateLimitBudget`
mechanism remains the single enforcement point. The budgets exercised by retained routes:

| Budget | Limit | Notes |
|---|---|---|
| `AUTOCOMPLETE` | per the enum | `/api/search/autocomplete` |
| `LOGIN_ISSUE` | per the enum | `/login/issue/` |
| `MEDIA_GATE` | per the enum | media delivery gate |
| `SEARCH_PAGE`, `DEEP_LINK_RENDER` | per the enum | HTML listings/search and the contact deep link |

## i18n

Locale is resolved via the **shared middleware chain** — `?lang` > `lang_pref` cookie >
`Accept-Language` — with **no per-view locale code**, identically for HTML and the retained JSON
routes.

## Stances

- **#4 autocomplete — not aliased.** The existing `/api/search/autocomplete` endpoint stays as-is.
- **#14 bulk — frozen shape.** `/moderation/api/v1/bulk-action/` keeps its contract, including the
  per-id error report; it carries no rate limiter.
- **#17 alert delivery — bot + scheduler only, no HTTP endpoint.** The agent-visible substitute is
  the delivery receipt `SavedSearchNotification.delivered_at`, read via the shell/ORM tier.
- **#19 preferred-city — the one JSON route with no rate limiter.**
- **#21 login — token protocol, no extra endpoint.** `/login/issue/` issues, `/login/status/` reports
  (200 issued / 204 pending / 410 uniform).
- **#23 contact seller — deep-link protocol.** Bot-only by design (seller anonymity); the ad-detail
  payload carries the `t.me` deep link, and there is no HTTP contact endpoint.
- **#24 support ticket — bot-only intake.** The bot handler is the only writer (06-PII-101 signed
  identity).
- **#26 media — URLs only.** Media access stays the binary nginx `X-Accel`-gated protocol; payloads
  carry media URLs only, never bytes.
- **#27 ops/metrics — health/readiness and loopback-gated `/metrics`.** No JSON index endpoint.
- **#28 admin actions — unchanged staff-web.**

## Analytics side effects (agent-visible)

HTML reads record analytics (`AD_VIEWED`, `SEARCH_PERFORMED` plus popular-search and search-history
entries). Verification loops that must avoid side effects should use the service tier or the
shell/ORM tier on the test database.

## Change log

- **Retirement (P4).** The unused `/api/v1/` JSON mirror surface was retired: its root mount, the
  aggregator package, per-app API route/view modules, API adapters, the parity CLI and the related
  tests were removed. Only the retained legacy routes and operational endpoints documented above
  remain. Historical stage entries (S0–S5) are recorded in the architecture plan.
