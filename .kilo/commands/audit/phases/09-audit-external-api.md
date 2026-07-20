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
| **Telegram Gateway** | The credential (bot token) and the update channel (polling or webhook). Webhook (if used) must verify Telegram's secret. |
| **External Translation Client** | Calls a third-party machine-translation service (search + ad-creation). Needs timeout, retry/backoff, circuit-breaker, fallback, cost/rate-limit awareness, and NO PII egress. |
| **Login-Token / Deep-Link** | Issues a one-time token delivered via deep-link/QR; two-phase claim; expiry; replay protection; cross-process auth handoff (crypto/expiry detail in phase 04; delivery + claim + replay here). |
| **API Gateway (if present)** | Any REST/endpoint surface: authn/authz, rate-limit, input validation, injection safety, versioning. |
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

1. **Webhook/API auth (if present)** — POST to the webhook/API endpoint WITHOUT the Telegram secret (or auth) → assert rejected (401/403). WITH valid secret → accepted. If no webhook/API surface exists, assert reverse-proxy rate-limit zones are applied to public endpoints.
2. **Bot token isolation** — grep repo + capture client error traces + logs → assert the bot credential is NOT present anywhere except the runtime environment; never logged.
3. **Translation resilience** — simulate translator timeout/outage → assert bounded latency, fallback to original text, no crash, circuit-breaker/backoff engages; verify synthetic (non-PII) text only was sent.
4. **Login-token lifecycle** — issue token → claim once → success; replay same token → rejected; expired token → rejected; concurrent claim race → exactly one wins. Verify raw token not persisted; only a salted hash stored.
5. **API surface (if present)** — unauthenticated → 401; malformed input → 422 (not 500); injection payload → safe; rate-limit exceeded → 429.
6. **Secrets** — grep repo + container env dump for hardcoded secrets; assert credentials come from env/secret store; note absence of rotation procedure.
7. **TLS / headers** — assert valid cert, HSTS, CSP, nosniff, frame-deny at the proxy; media hardening present.
8. **Graceful degradation** — kill translation/bot dependency → assert core browse still works; search returns degraded results, not 500s.
9. **Quality gates** — run linter, type-checker, integration test suite.

## 5. Audit Dimensions (checks + evidence)

### (a) Bot token + webhook/API auth — CRITICAL
Credential sourced only from environment; never logged/leaked. If a webhook or API surface exists, it authenticates callers (Telegram secret / API authn).
- Evidence: no token in repo/logs/traces; webhook rejects unauthenticated updates; reverse-proxy rate-limits public endpoints.

### (b) Async↔Sync bridge safety — HIGH
ORM calls offloaded off the event loop; no connection exhaustion/leak under load; thread-safe.
- Evidence: bridge wraps every ORM call; connection sanity under concurrency; no event-loop blocking on slow calls.

### (c) Translation client resilience + PII egress — CRITICAL
Timeout, retry/backoff, circuit-breaker, fallback, cost/rate-limit awareness. NO PII sent to the third party.
- Evidence: outage → bounded fallback, no cascade; synthetic text only in tests; no user identity content transmitted.

### (d) Login-token lifecycle — CRITICAL
Issuance, two-phase claim, expiry, replay rejection, race safety; raw token never persisted.
- Evidence: replay/expiry/race assertions pass; only hashed value stored; cross-process claim atomic.

### (e) API surface security (if present) — CRITICAL
Authn/authz, rate-limit, input validation, injection safety, versioning.
- Evidence: unauth→401, bad input→422, injection safe, rate-limit→429, versioned contracts.

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
- Telegram gateway 429 → backoff, no corruption of in-flight drafts.
- Translator returns empty/garbage → ad-creation fallback (store original, not crash).
- Login-token opened on wrong device / twice / after expiry → rejected safely.
- API version mismatch (client v1 vs server v2) → handled, not 500.
- Reverse-proxy restart drops webhook registration → re-register.
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
  - No rate-limit on API/webhook/public endpoints.
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
