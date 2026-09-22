# 09 — External Integrations & API

> Audit phase. LLM-auditor instruction. Architecture-agnostic: described via
> ARCHITECTURAL LAYERS, ZONES OF RESPONSIBILITY, KEY RISKS, GOALS. NOT tied to
> specific files, modules, or functions. Must stay valid if the architecture changes.
>
> **Output mode:** `problems-only` — report only findings; do not narrate a clean bill of health.

## 1. Goal

Verify that every boundary to the outside world — the bot runtime, the external
translation service, the login-token deep-link flow, any REST/API surface, the
reverse proxy, and secret storage — is authenticated, resilient, and does not
leak PII or secrets. Confirm the system degrades gracefully when an integration
is unavailable.

## 2. System Under Audit (layers & zones)

| Zone | Concern |
|------|---------|
| **Bot / Async Runtime** | The async bot process drives all seller writes; bridges into the shared synchronous persistence layer. |
| **Async↔Sync Bridge** | The wrapper that lets async handlers call the synchronous ORM. Must not block the event loop or exhaust connections (overlaps phase 03 connection sanity). |
| **Telegram Gateway** | The credential (`BOT_TOKEN`) and the update channel. The bot uses aiogram long-polling (`dp.run_polling`); no webhook endpoint is exposed — no HTTPS ingress for the bot. Updates are de-duplicated by `UpdateIdDedupMiddleware` (atomic Redis `cache.add` on `update_id`); the raw token is env-sourced only and never logged. |
| **External Translation Client** | Calls a third-party machine-translation service (search + ad-creation). Needs timeout, retry/backoff, circuit-breaker, fallback, cost/rate-limit awareness, and NO PII egress. |
| **Login-Token / Deep-Link** | Issues a one-time token delivered via deep-link/QR; two-phase claim; expiry; replay protection; cross-process auth handoff (crypto/expiry detail in phase 04; delivery + claim + replay here). |
| **API Gateway** | Mixed API surface. Public JSON endpoints (`/api/search/autocomplete`, `/api/preferred-city/`, `/search/`, `/health/live/`, `/health/ready/`, `/csp-report/`) return `200` to anonymous users by design (no auth gate). Staff-only JSON API (`/moderation/api/v1/*`, e.g. `bulk-action/`) is gated by the custom `@staff_required_api` decorator returning `401` (unauthenticated, with `WWW-Authenticate: Bearer`), `403` (authenticated non-staff), `405` (wrong method). Staff-only template views (`/moderation/queue/`, `/moderation/review/<id>/`, …) use the custom `@staff_required` decorator returning `404` for any non-staff (URL-leak prevention — not `401`/`403`). No moderation view uses Django's built-in `@staff_member_required`. No API versioning exists — the `/v1/` path prefix is not a negotiated version. |
| **Reverse Proxy / TLS** | TLS termination, security headers (HSTS, CSP, nosniff, frame-deny), rate-limit zones, media hardening. |
| **Secrets / Credentials** | Bot token, framework secret key, DB credentials: sourced from env/secret store, never hardcoded, rotation possible. |

## 3. Prerequisites

- Services runnable via the documented Docker commands (web + bot + DB + reverse proxy).
- External dependencies (Telegram gateway, translator) MUST be mocked in tests — no real calls, no cost, no real token.
- Synthetic login tokens and synthetic ad text only (NO PII, NO real secrets).
- Ability to inspect the reverse proxy config and TLS responses.
- Linter, type-checker, and integration tests available.

## 4. Runtime Verification (mandatory)

Execute, then capture evidence (HTTP responses, logs, config dumps, latency):

1. **Bot gateway auth (long-polling)** — assert no `set_webhook()` call exists and no webhook URL env vars (`WEBHOOK_URL`, `TELEGRAM_WEBHOOK_SECRET`) are referenced anywhere in entrypoints or compose; assert `UpdateIdDedupMiddleware` de-duplicates updates by `update_id`; assert the bot token is sourced from env only and never appears in repo, logs, or traces.
1b. **API auth (per-endpoint, not blanket)** — for each API endpoint, assert the *actual* response code: public endpoints (`/api/search/autocomplete`, `/search/`, `/health/*`, `/csp-report/`) return `200` to anonymous; unauthenticated staff-only API (`/moderation/api/v1/*`) returns `401` + `WWW-Authenticate: Bearer`; authenticated non-staff API returns `403`; non-staff template views (`/moderation/*`) return `404`.
2. **Bot token isolation** — grep repo + capture client error traces + logs → assert the bot credential is NOT present anywhere except the runtime environment; never logged.
3. **Translation resilience** — simulate translator timeout/outage → assert bounded latency, fallback to original text, no crash, circuit-breaker/backoff engages; verify synthetic (non-PII) text only was sent.
4. **Login-token lifecycle** — issue token → claim once → success; replay same token → rejected; expired token → rejected; concurrent claim race → exactly one wins. Verify raw token not persisted; only a salted hash stored.
5. **API surface (mixed)** — per-endpoint matrix (not blanket `401`): public endpoints return `200` to anonymous; staff-only JSON API returns `401`/`403`/`405`; staff-only template views return `404`. Malformed input → `422` (Pydantic DTO validation, e.g. `BulkModerationRequest`, `CSPReportPayload`); injection payload → safe; rate-limit exceeded → `429`. No API versioning exists — `/v1/` is a path prefix, not a negotiated version.
6. **Secrets** — grep repo + container env dump for hardcoded secrets; assert credentials come from env/secret store; verify a rotation procedure is documented for `BOT_TOKEN`, `GOOGLE_TRANSLATE_API_KEY`, and `DJANGO_SECRET_KEY`.
7. **TLS / headers** — assert valid cert, HSTS, CSP, nosniff, frame-deny at the proxy; media hardening present.
8. **Graceful degradation** — kill translation/bot dependency → assert core browse still works; search returns degraded results, not 500s.
9. **Quality gates** — run linter, type-checker, integration test suite.

## 5. Audit Dimensions (checks + evidence)

### (a) Bot token + API auth — CRITICAL
Bot token sourced only from environment; never logged/leaked. The bot uses long-polling (`dp.run_polling`) — no webhook exists, so Telegram secret verification is moot. The API surface authenticates callers via the custom `@staff_required`/`@staff_required_api` decorators (checks `is_staff or is_superuser`), not via Telegram's secret token.
- Evidence: no token in repo/logs/traces; no `set_webhook()` call; public endpoints return 200; staff-only JSON API returns 401/403/405; staff-only template views return 404; reverse-proxy rate-limits public endpoints.

### (b) Async↔Sync bridge safety — HIGH
ORM calls offloaded off the event loop; no connection exhaustion/leak under load; thread-safe.
- Evidence: bot calls `django.setup()` and shares `config.settings.prod` + the same PostgreSQL DB with the web (gunicorn) process; `DatabaseConnectionMiddleware` (bot-only, registered via `dp.update.outer_middleware` in `main.py:79`) wraps each update dispatch in `try/finally` calling `sync_to_async(close_old_connections)()` in `finally` on the asgiref worker thread owning the thread-local connection; `CONN_MAX_AGE=0` (`base.py`) prevents cross-update connection leakage; every ORM call in handlers is wrapped in `@sync_to_async`/`await sync_to_async(...)`; shared Redis cache (`django-redis`) keeps rate-limit counters and cache invalidations coherent across gunicorn workers and the bot; login-token claim is two-phase and atomic via `UPDATE … RETURNING WHERE consumed_at IS NULL AND expires_at > %s` (`login.py:191`, `consent.py:409–414`) with only a SHA-256 hash persisted.

### (c) Translation client resilience + PII egress — CRITICAL
Timeout, retry/backoff, circuit-breaker, fallback, cost/rate-limit awareness. NO PII sent to the third party.
- Evidence: outage → bounded fallback, no cascade; synthetic text only in tests; no user identity content transmitted.

### (d) Login-token lifecycle — CRITICAL
Issuance, two-phase claim, expiry, replay rejection, race safety; raw token never persisted.
- Evidence: replay/expiry/race assertions pass; only hashed value stored; cross-process claim atomic.

### (e) API surface security — CRITICAL
Authn/authz, rate-limit, input validation, injection safety.
- Evidence: public→200 (anonymous), staff-only JSON→401/403/405, staff-only templates→404; bad input→422 (Pydantic DTOs e.g. `BulkModerationRequest`, `CSPReportPayload`); injection safe; rate-limit→429. No API versioning exists — `/v1/` is a path prefix, not a negotiated version.

### (f) Secrets management — CRITICAL
No hardcoded secrets; env/secret store; rotation feasible.
- Evidence: grep clean; credentials from env; rotation path documented or flagged.

### (g) Reverse proxy / TLS hardening — HIGH
Valid TLS, HSTS, secure headers, rate-limit zones, media hardening.
- Evidence: cert valid; HSTS+CSP+nosniff+frame-deny present; media script-exec blocked.

### (h) Graceful degradation — HIGH
Core browse survives integration outages; search degrades, not fails.
- Evidence: translation/bot down → browse works; no 500 cascade.

## 6. Cross-Cutting (owned here, not duplicated)
- **Async↔Sync bridge** is the seam between bot runtime and shared ORM — bridge safety overlaps phase 03 (connection pool) but the event-loop/thread correctness is this phase.
- **Login-token** crypto/expiry detail is phase 04; the deep-link delivery + claim orchestration + replay is here.
- **Translation failure handling** is partly phase 08 (search recall) but the CLIENT resilience + PII-to-third-party is here.

## 7. Edge Cases
- Duplicate / out-of-order Telegram updates → idempotent handling.
- Telegram gateway 429 → backoff, no corruption of in-flight drafts. (Gap: no explicit application-level Telegram-API 429 backoff — relies on aiogram's `run_polling` built-in handling; verify or document.)
- Translator returns empty/garbage → ad-creation fallback (store original, not crash).
- Login-token opened on wrong device / twice / after expiry → rejected safely.
- API version mismatch (client v1 vs server v2) → handled, not 500.
- Reverse-proxy restart drops webhook registration → re-register. (OBSOLETE — no webhook exists to re-register; bot uses long-polling. Verify `DatabaseConnectionMiddleware`'s `finally` closes connections on crash instead.)
- Secret rotation without downtime.
- Bot process crash mid-bridge call → connection/transaction left consistent.

## 8. Severity Taxonomy

- **CRITICAL**
  - Webhook/API accepts unauthenticated forged updates.
  - Bot credential leaked (repo/logs/traces).
  - Login-token replay succeeds or has no expiry.
  - PII sent to external translator.
  - API missing auth / injection-unsafe.
  - Secrets hardcoded in repo.
- **HIGH**
  - Async↔Sync bridge causes connection exhaustion / event-loop block.
  - Translation outage cascades with no fallback / circuit-breaker.
  - Public endpoint missing its rate-limit zone assignment.
  - TLS/header weaknesses at reverse proxy.
  - No graceful degradation when an integration is down.
- **MEDIUM**
  - Translation retry storm / cost blowup.
  - Login-token race not fully handled.
  - API versioning/validation gaps.
  - Secrets not rotated.
- **LOW**
  - Missing type hints on integration helpers.
  - Log verbosity / no integration-health metrics.
  - No alerting on repeated translation failures.

## 9. Recommended Sequence
1. Discovery — map each integration, the bridge, the token flow, API surface, proxy, secrets.
2. Runtime verification (§4).
3. Per-dimension checks (§5 a–h).
4. Cross-cutting (§6) and edge cases (§7).
5. Consolidate findings.

## 10. Finding Prefix
Use `EXT-` for all findings in this phase.

## 11. Reporting
- `problems-only: true`.
- Each finding: severity, zone, evidence (path/line/HTTP response/config dump), and recommendation with effort/priority.
- Append incrementally (≤100 lines per write) to the phase findings file per `docs/99-agent/rules.md`.
