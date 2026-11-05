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
  - architecture
---

## Purpose

The authoritative contract for every HTTP interface the application exposes today. The site is an
HTMX/MPA application and ad posting is bot-first, so the overwhelming majority of user-visible
behavior is server-rendered HTML. Alongside it the application exposes a small set of **frozen
legacy JSON routes** and a set of **operational endpoints** (health, readiness, metrics, admin,
media).

There is **no general-purpose JSON API** and no `/api/v1/` per-app mirror. This document is the
contract; no OpenAPI schema is produced. Source layout and deployment topology are in
[`architecture-structure.md`](architecture-structure.md); the browserless verification model is in
[`../99-agent/architecture.md`](../99-agent/architecture.md#task--service--tests-map).

## Main Concepts

- **Style:** plain Django views. **No DRF, no django-ninja.**
- **Mounting:** every route is declared in its own app's `urls.py` and mounted by the ordinary root
  URLconf includes — there is no root aggregator and no separate API app.
- **Writes:** POST-only (`@require_POST` / `@staff_required_api`) where an endpoint writes.
- **Errors:** legacy shapes are frozen and per-endpoint (bare 429, `{"error":"rate_limit"}`, the
  moderation bulk report document). They are **not** retrofitted to RFC 9457 — see rule 18 in
  [`.kilo/rules/project.md`](../../.kilo/rules/project.md).
- **Audience:** public reads reuse the same `account_state_q` predicate as the HTML surface, so
  visibility matches by construction.

## Retained interface inventory

| Interface | Location | Auth | Notes |
|---|---|---|---|
| HTML / HTMX pages | `ads`, `search`, `categories`, `locations`, `cabinet`, `analytics`, `moderation`, `users` URLconfs | PUB / SESS / STAFF | The product: listings, search, detail, dashboards, cabinet, moderation review |
| Telegram bot | `src/telegram_bot/` (aiogram) | Telegram identity | The ad-creation write path; FSM drafts persist as `Ad(DRAFT)` rows |
| Admin | `admin/` | STAFF | Django admin: catalog, lookups, users, `SiteConfig` |
| `POST /moderation/api/v1/bulk-action/` | `moderation:bulk_action` (`apps/moderation/views/api_bulk.py`) | STAFF | Frozen legacy bulk-moderation contract |
| `GET /api/search/autocomplete` | `search:autocomplete` (`apps/search/views/autocomplete.py`) | PUB | Frozen legacy autocomplete |
| `POST /api/preferred-city/` | `search:preferred_city` (`apps/search/views/preferred_city.py`) | anon + consent cookie | No rate limiter |
| `/login/issue/` + `POST /login/status/` | `users:login_issue`, `users:login_status` (`apps/users/views/consent.py`) | anon | Login token protocol |
| Health / readiness | `core:health`, `core:health_live`, `core:health_ready` | — | `/health/`, `/health/live/`, `/health/ready/` |
| Metrics | `prometheus-django-metrics` (`config/urls.py`) | loopback only | `/metrics`, gated in nginx **and** Django |
| Media delivery | `ads:media_gate` (`apps/ads/views/listings.py`) | — | Binary `X-Accel`-gated protocol, URLs only |

## Auth model

| Category | Enforcement | Notes |
|---|---|---|
| **PUB** | anonymous allowed; audience predicate `account_state_q` applied | Visibility identical to the HTML surface (withdrawn/banned/declined sellers invisible) |
| **SESS** | Django session cookie (`@login_required` on the HTML views) | Protected by CSRF on writes |
| **STAFF** | `staff_required_api` (`apps/moderation/views/decorators.py`) | Identity is checked **before** the method; plain `{"error": …}` body |

- **Sessions are the only credential.** No new auth scheme, no CSRF exemption, no bearer token.
  `/login/status/` establishes the session through the Telegram-mediated token handshake.

## Legacy route contracts

### Bulk moderation — `POST /moderation/api/v1/bulk-action/`

Staff-only. Accepts one request body describing the action and the ad ids; returns a **report
document**, never per-id HTTP statuses:

```json
{
  "completed": 1,
  "errors": [{"id": 5, "error": "Invalid transition"}]
}
```

- `200` — report document. `completed` counts ids that were transitioned; `errors` lists each
  failed id with its refusal reason. A happy response carries exactly
  `{"completed": <n>, "errors": []}`.
- `422` — `{"error": "Invalid request body", "errors": pydantic_errors_json(exc)}` (validation of
  the request DTO; `apps/core/utils/sanitize.py`).
- `400` / `401` / `403` / `405` — plain `{"error": …}` body.
- No rate limiter on this route; lock-timeout (`PostgreSQL 55P03`) is handled by
  `DbLockTimeoutMiddleware` → `503`.

### Search autocomplete — `GET /api/search/autocomplete`

Anonymous. Returns ranked suggestions for a query prefix. Over budget it returns the frozen legacy
429 shape `{"error": "rate_limit"}` with **no** `Retry-After`.

### Preferred city — `POST /api/preferred-city/`

Anonymous, consent-cookie backed. Returns `{"ok": true}` on success and
`{"error": "invalid_city"}` with `400` for an unknown slug. **No rate limiter** — the one JSON
route that has none.

### Login token protocol — `/login/issue/` and `POST /login/status/`

- `POST`-free issuance: `GET /login/issue/` renders the deep-link page and issues a token
  (`login_rate_limit_check`, `check_deep_link_render_rate_limit` → `429`).
- `POST /login/status/` is `@require_POST` and reads the raw token from the request body (never from
  the URL — no `Referer` leak). Responses:
  - `200` — token consumed, session established (session cookie set).
  - `204` — pending; the bot has not claimed the token yet.
  - `410` — **uniform** for `not_found` / `gone` / `unbound` / `lost_race` (anti-enumeration).
- Lifecycle and predicates: see
  [`../99-agent/architecture.md`](../99-agent/architecture.md#login-token-lifecycle-seam-ent-005).

## Operational endpoints

- **Health:** `/health/` (Icinga-style check), `/health/live/` (liveness), `/health/ready/`
  (readiness — includes the optional bot-liveness dimension gated by `BOT_HEALTH_CHECK_ENABLED`,
  which defaults off). `/health/v1/` is an alias of readiness.
- **Metrics:** `/metrics` is restricted **twice** — nginx `allow 127.0.0.1; deny all;` and a
  Django gate keyed on the socket peer `REMOTE_ADDR` (loopback allowed, everything else `403`), so
  a caller reaching the `web` container directly across the Docker bridge is still refused.
- **Admin:** `admin/` — staff/superuser session; all catalog and `SiteConfig` editing happens here.
- **Media gate (`ads:media_gate`, `/media/<key>`)**: binary delivery, not JSON. Payloads anywhere
  else in the application carry media **URLs only**, never bytes. `200` only for images attached to
  `PUBLISHED` ads owned by non-banned, non-declined sellers; `403`/`404` otherwise; `X-Accel-Redirect`
  to an nginx `internal` location. Production `200` responses carry `Cache-Control: public,
  max-age=86400` and `Vary: Cookie`; `429` responses carry `no-store`. Storage keys are unguessable
  `<uuid4>.jpg` with no `ad_id`. Operator details:
  [`../ops/media-store-operations.md`](../ops/media-store-operations.md).

## Rate-limit budgets

Budgets are `RateLimitBudget` StrEnum members (`apps/core/enums.py`); the numbers live in the enum
properties, never in environment variables. `rate_limit_check` + `RateLimitBudget` is the single
application-level enforcement point:

| Budget | Limit | Used by |
|---|---|---|
| `SEARCH_PAGE` | 30 / 60 s | Anonymous HTML search rendering |
| `AUTOCOMPLETE` | 30 / 60 s | `/api/search/autocomplete` (independent key namespace) |
| `DEEP_LINK_RENDER` | 60 / 600 s | Anonymous browse pages that render Telegram contact deep-links |
| `LOGIN_ISSUE` | 10 / 60 s | `/login/issue/` |
| `MEDIA_GATE` | 240 / 60 s | Media delivery gate |

nginx adds a separate per-IP edge layer; see
[`architecture-structure.md`](architecture-structure.md#nginx-hardening-zone-r8).

## i18n

Locale is resolved by the **shared middleware chain** — `?lang` > `lang_pref` cookie >
`Accept-Language` — with no per-view locale code, identically for HTML and the retained JSON routes.

## Bot-only and non-HTTP surfaces

These product actions deliberately have no HTTP endpoint:

- **Contact seller** — Telegram deep-link protocol (`t.me/<bot>?start=contact_<ad_id>`); the ad
  detail payload carries the link. No contact endpoint exists (seller anonymity).
- **Support ticket** — the bot handler is the only writer (`ContactUsState` → `SupportTicket`).
- **Alert delivery** — bot digest + scheduler only. The agent-visible delivery receipt is
  `SavedSearchNotification.delivered_at`, readable through the ORM/shell tier.
- **Ad creation** — the bot dialog is the write path (drafts are `Ad(DRAFT)` rows); the web owns
  edit, archive, reactivate and delete.

## Verification model

Every retained route above is exercised browserlessly by Django `Client()` under pytest, with the
exit status as the machine-readable verdict (JUnit XML optional). There is no separate HTTP
consumer, parity CLI or route-pairing harness: a real HTTP parity check would need a real client
surface that does not exist. The per-feature map is
[`../99-agent/architecture.md`](../99-agent/architecture.md#task--service--tests-map).
