# Phase 09 Audit Findings — External Integrations & API

**Executor:** audit-executor
**Template:** `.ai/audit/templates/audit-findings.md`
**Phase scope (zones):** Bot/async runtime (`src/telegram_bot/main.py` — aiogram 3.x, polling); async↔sync bridge (`asgiref.sync_to_async` / `asyncio.to_thread` in `src/telegram_bot/handlers/`); Telegram gateway (polling, no webhook — `settings.BOT_TOKEN` from env, never logged); external translation client (`src/backend/apps/core/services/translation.py` → `deep_translator` `GoogleTranslator`); login-token deep-link flow (`src/backend/apps/users/views/consent.py` + `src/telegram_bot/handlers/login.py`); API surface (`src/backend/apps/moderation/views/api_bulk.py`, cabinet, search); reverse proxy/TLS (`docker/nginx/nginx.conf`); secrets (`src/backend/config/settings/{base,prod}.py`, `.env.docker.example`).
**Status:** complete
**Validated:** no (static analysis only; Docker runtime not executed this phase)

> **Cross-phase dedup note:** Login-token lifecycle (incl. AU-001 token-in-GET-URL) is owned by phase 04; bot DB-connection leak is owned by phase 03 (DB-001); search-side translation-bridge removal (SRH-002) and search long-query DoS (SRH-001) are owned by phase 08; the moderation bulk DTO gap is owned by phase 02 (CFG-003). Findings below are scoped to external integrations NOT already filed.

---

## Findings

### EXT-001: Translation client has no retry/backoff, leaks abandoned worker threads, and masks errors with a broad `except Exception`

| Field | Value |
|-------|-------|
| **ID** | EXT-001 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/core/services/translation.py` (translation client, §5c), `src/telegram_bot/handlers/ad_create.py:1270-1274` (caller) |
| **Classification** | advisory |
| **Phase checks** | §5(c) Translation client resilience + PII egress; §7 Translator returns empty/garbage -> fallback |

**Description:** The shared translation client (`apps.core.services.translation`) provides a 500 ms timeout, an in-process circuit-breaker, an LRU cache, and a fallback-to-original-text path — but it is **missing retry/backoff**, which §5(c) explicitly requires. `translate_text` makes a single attempt: on `TimeoutError`/`RequestException` it records one circuit-breaker failure and returns the original text with no retry. The 500 ms bound is enforced by `future.result(timeout=TRANSLATION_TIMEOUT_SECONDS)` (`translation.py:156-159`) against a module-level `ThreadPoolExecutor(max_workers=4)` (`translation.py:29`); when that timeout fires the **worker thread is abandoned and never cancelled** (the module comment at `translation.py:25-28` documents this explicitly), and `GoogleTranslator.translate()` (deep-translator) runs its underlying `requests` call with **no HTTP-level timeout**, so a hung upstream keeps the worker blocked until TCP idle/retransmit expiry (~tens of seconds). Under translator throttling the 4 workers saturate and are never reclaimed; once saturated, `translate_text` can no longer dispatch and the bot's `translate_all_languages` gather (`ad_create.py:1270-1274`, three `asyncio.to_thread` calls) stalls, blocking ad creation. Separately, `except (TimeoutError, RequestException, Exception)` at `translation.py:170` is a catch-all that treats programming errors (e.g. deep-translator `AttributeError`/`KeyError`) as transient translation failures and silently falls back, masking bugs and defeating observability.

**Evidence:**
- `src/backend/apps/core/services/translation.py:29` — `_EXECUTOR: ThreadPoolExecutor(max_workers=4)`
- `src/backend/apps/core/services/translation.py:25-28` — comment acknowledges abandoned futures ("a timed-out future is abandoned rather than waited on via shutdown")
- `src/backend/apps/core/services/translation.py:155-159` — single attempt; `future.result(timeout=0.5)`; no retry/backoff
- `src/backend/apps/core/services/translation.py:170` — `except (TimeoutError, RequestException, Exception) as e:` catch-all
- `src/backend/apps/core/services/translation.py:107,126` — `GoogleTranslator(...).translate(query)` (deep-translator passes no `timeout`; underlying `requests` has no timeout)
- `src/telegram_bot/handlers/ad_create.py:1270-1274` — `asyncio.gather(*[asyncio.to_thread(translate_text, text, "auto", loc) for loc in target_locales])`

**Recommendation:** [BEST-PRACTICE] Add bounded retry with capped exponential backoff (1–2 attempts) at the `translate_text` layer; collapse the redundant `asyncio.to_thread`→executor double-hop into a single concurrency scope bounded by a `Semaphore` so saturated throttling degrades to fallback instead of stalling; narrow the `except` to `TimeoutError, RequestException` so non-transient errors propagate; migrate off deep-translator's un-timeout'd `requests` to `httpx` with an explicit per-request timeout + cancel scope so a timed-out call is actually cancelled rather than leaving an orphaned worker. Effort: medium. Priority: recommended.

---
### EXT-002: Publish-time alert delivery bridge spawns a daemon thread + fresh Bot/session per message with no retry on transient Telegram errors

| Field | Value |
|-------|-------|
| **ID** | EXT-002 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/backend/apps/search/services/immediate_alerts.py` (web→async bridge), `src/backend/apps/moderation/signals.py:56-76` (trigger) |
| **Classification** | advisory |
| **Phase checks** | §2 Async↔Sync bridge (web→async); §5(c) client resilience; §7 graceful degradation when an integration is down |

**Description:** Near-real-time alert delivery (`deliver_immediate_alerts`, gated by `IMMEDIATE_ALERTS_ENABLED`, default OFF) is invoked from a `transaction.on_commit` callback running in the **sync gunicorn worker** (`moderation/signals.py:76`), which then spawns a **dedicated `threading.Thread` per published ad** (`immediate_alerts.py:87-93`) running `asyncio.run(_send_payloads(...))`. Inside that loop, `Bot(token=bot_token)` is constructed **per alert message** (`immediate_alerts.py:178`) — i.e. a fresh `aiohttp` session / TCP connection pool to `api.telegram.org` per recipient, with no reuse across the batch. The only concurrency cap (`_SEND_CONCURRENCY = 10`, `immediate_alerts.py:38`) is a **per-thread** `asyncio.Semaphore`, **not** a global bound, so a burst of published ads creates an unbounded number of daemon threads. Transients outside `TelegramBadRequest`/`TelegramForbiddenError` (e.g. network reset, 5xx, or a Telegram 429 with `retry_after`) hit the bare `except Exception` at `immediate_alerts.py:168` and are **logged then dropped with no retry** — a published ad's alerts can be silently lost. This is the web-process counterpart of the bot↔ORM bridge; §2 correctly flags the cross-process seam, but the sync→async-over-thread bridge here lacks global bounding and retry.

**Evidence:**
- `src/backend/apps/moderation/signals.py:56-76` — `deliver_immediate_alerts_on_publish`; `transaction.on_commit(_deliver)`; guarded only by `IMMEDIATE_ALERTS_ENABLED`
- `src/backend/apps/search/services/immediate_alerts.py:87-93` — `threading.Thread(target=_run_send, …, daemon=True)` created per published ad
- `src/backend/apps/search/services/immediate_alerts.py:164-168` — `_run_send` → `asyncio.run(...)` wrapped in `except Exception as exc:` (no retry, no 429 back-off)
- `src/backend/apps/search/services/immediate_alerts.py:172-193` — `_send_payloads` builds `Bot(token=bot_token)` inside the per-message `_send` (line 178)
- `src/backend/apps/search/services/immediate_alerts.py:186` — only `TelegramBadRequest, TelegramForbiddenError` are handled per-message

**Recommendation:** [BEST-PRACTICE] Reuse a single module-level `Bot` (one shared `aiohttp` session) per worker thread and close it after the batch; bound the number of concurrent delivery threads globally (process-level semaphore / bounded `ThreadPoolExecutor`) so a publish burst cannot spawn unbounded threads; implement retry-with-backoff for non-fatal Telegram errors (honour `retry_after` on 429, exponential backoff on 5xx/network) and route permanently-unreachable chats to a dead-letter record rather than silently dropping. Effort: medium. Priority: recommended.

---
### EXT-003: Reverse-proxy rate limiting covers only /login/ and /search/; public browse surface + moderation API are unthrottled

| Field | Value |
|-------|-------|
| **ID** | EXT-003 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `docker/nginx/nginx.conf` (rate-limit zones), `src/backend/apps/moderation/views/api_bulk.py` (moderation API), `src/backend/apps/ads/views/listings.py` (public browse) |
| **Classification** | mandatory |
| **Phase checks** | §5(a) reverse-proxy rate-limit zones on public endpoints; §8 HIGH "No rate-limit on API/webhook/public endpoints"; §7 graceful degradation / DoS |

**Description:** `nginx.conf` defines only two `limit_req_zone`s — `login_limit` (10 r/s) and `search_limit` (20 r/s) (`nginx.conf:24-25`) — and attaches `limit_req` to **only** `location /login/` (`nginx.conf:101`) and `location /search/` (`nginx.conf:111`). The default `location /`, the catalog/ads browse surface (`/`, category and ad detail/listings), and the state-changing `POST /moderation/bulk-action/` all inherit **no `limit_req`**. Per §5(a) and §5(h), public endpoints must carry a reverse-proxy rate-limit zone; their absence leaves the FTS/join-heavy listings and the moderation bulk API open to unthrottled requests. This is the amplification path for the §8 DoS class: phase 08 SRH-001 shows `/search/` is bounded by `search_limit` (so its long-query 500-DoS is partially capped), but the unthrottled catalog listings perform the same per-language GIN/FTS joins with no comparable guard, and the admin bulk-action API has no throttle **plus** an unbounded `selected_items` batch, allowing a single request to drive mass ad mutations.

**Evidence:**
- `docker/nginx/nginx.conf:24-25` — only `login_limit` and `search_limit` zones defined
- `docker/nginx/nginx.conf:100-107` — `limit_req zone=login_limit` on `/login/` only
- `docker/nginx/nginx.conf:109-117` — `limit_req zone=search_limit` on `/search/` only
- `docker/nginx/nginx.conf:128-135` — default `location /` has **no** `limit_req`
- `src/backend/apps/moderation/views/api_bulk.py:54` — `for ad_id in ad_ids:` (no cap on `selected_items` batch size)
- phase 08 SRH-001 (search long-query 500-DoS), confirming the FTS read path is a known DoS amplifier

**Recommendation:** [BEST-PRACTICE] Attach a reverse-proxy `limit_req` zone to the public browse surface (`location /`) and to `/moderation/`; enforce an application-level cap on `selected_items` in the bulk API (e.g. max 100/request) and prefer an app-level throttle (cached rate counter) so limits are observable and testable rather than only proxy-imposed. Effort: small. Priority: recommended.

---
### EXT-004: `/protected-media/` location drops HSTS and `Referrer-Policy`/`Permissions-Policy` are absent site-wide

| Field | Value |
|-------|-------|
| **ID** | EXT-004 |
| **Severity** | LOW |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `docker/nginx/nginx.conf` (TLS/header hardening) |
| **Classification** | advisory |
| **Phase checks** | §5(g) Reverse proxy / TLS hardening (HSTS, CSP, nosniff, frame-deny); §8 TLS/header weaknesses |

**Description:** Server-wide security headers are set once at the `server` level (`Strict-Transport-Security`, `X-Content-Type-Options nosniff`, `X-Frame-Options DENY`, `Content-Security-Policy-Report-Only` — `nginx.conf:38-47`). nginx's `add_header` inheritance rule states that a `location` with **any** `add_header` of its own **drops all inherited** `add_header` directives. The `location /protected-media/` block (`nginx.conf:82-96`) re-declares `X-Content-Type-Options` (87), `X-Frame-Options` (89), and `Content-Security-Policy-Report-Only` (90) but **omits `Strict-Transport-Security`** → HSTS is silently dropped on every protected-media response. Additionally, no `Referrer-Policy` and no `Permissions-Policy` header is emitted anywhere in the config (server or location level — 0 matches), leaving referrer-leakage control to browser defaults. CSP is intentionally Report-Only only (deferred "Phase 2" per the inline comment at `nginx.conf:41-47`); that is a deliberate deferral and is not asserted here — the HSTS drop on protected-media is an unintended regression, not a listed deferral.

**Evidence:**
- `docker/nginx/nginx.conf:38` — server-level `Strict-Transport-Security "max-age=31536000; includeSubDomains"`
- `docker/nginx/nginx.conf:82-96` — `/protected-media/` block declares nosniff (87), `Content-Disposition` (88), `X-Frame-Options` (89), `CSP-Report-Only` (90) but **no** `Strict-Transport-Security`
- `docker/nginx/nginx.conf` (whole file) — 0 occurrences of `Referrer-Policy`; 0 of `Permissions-Policy`

**Recommendation:** [BEST-PRACTICE] Re-declare `Strict-Transport-Security` inside `/protected-media/` (or factor all security headers into an `include`'d snippet so every `location` emits the full set consistently — note the static `/static/` block already hand-re-declares all four, `nginx.conf:66-69`, which is the correct pattern to replicate). Add a site-wide `Referrer-Policy: strict-origin-when-cross-origin` (and a `Permissions-Policy` if no cross-origin features are required). Effort: trivial. Priority: recommended.

---
### EXT-005: Bot ad-creation FSM is not idempotent against re-delivered Telegram updates — crash mid-handler can create duplicate DRAFTs

| Field | Value |
|-------|-------|
| **ID** | EXT-005 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/telegram_bot/main.py:65` (`dp.run_polling`), `src/telegram_bot/handlers/ad_create.py:865-875` (`create_draft_ad` -> `Ad.objects.create(..., DRAFT)`), `src/telegram_bot/handlers/ad_create.py:1270-1274` (translation side-effect) |
| **Classification** | advisory |
| **Phase checks** | §7 Duplicate / out-of-order Telegram updates -> idempotent handling; §2 Bot / Async Runtime; §5(b) bridge correctness; §4.3/§4.9 quality gates |

**Description:** The bot receives updates via `dp.run_polling(bot)` (`main.py:65`) with aiogram's default offset acknowledgement: the `getUpdates` offset is confirmed **only after** a handler returns without error. Updates that were received but not yet acked are therefore **re-delivered on restart** (aiogram does not persist the offset to disk, and `main.py:43-58` registers only `AccountStateMiddleware()` — no update-ID dedup middleware). The login deep-link claim **is** idempotent (phase 04 confirmed the `UPDATE … RETURNING` row-lock guard at `login.py:119-131` rejects replays), but **ad creation is not**: `create_draft_ad` (`ad_create.py:870-875`) does a plain `Ad.objects.create(user_id=..., status=AdStatus.DRAFT)` (`ad_create.py:873`) with no client-message idempotency key, no `update_id` dedup, and no re-creation guard. If the bot process crashes between receiving a `/post` (or the category/photo step) and acknowledging the offset — e.g. mid-`sync_to_async` DB work or during `translate_all_languages` — Telegram re-delivers the update on restart and the handler re-runs, producing a **duplicate DRAFT** plus re-execution of translation/photo side-effects. Phase §7 explicitly lists "Duplicate / out-of-order Telegram updates → idempotent handling" as an edge case to verify; it is currently unguarded on the ad-creation path.

**Evidence:**
- `src/telegram_bot/main.py:65` — `dp.run_polling(bot)` (no `allowed_updates`, no offset persistence, no update-dedup middleware)
- `src/telegram_bot/main.py:43-58` — only `AccountStateMiddleware()` + routers registered (no idempotency middleware)
- `src/telegram_bot/handlers/ad_create.py:870-875` — `@sync_to_async def _create(): return Ad.objects.create(user_id=user_id, status=AdStatus.DRAFT)` (no idempotency key / no `get_or_create`)
- `src/telegram_bot/handlers/ad_create.py:1270-1274` — `translate_all_languages` re-invocable side effect on re-delivery
- contrast (idempotent): `src/telegram_bot/handlers/login.py:119-131` — login claim uses `UPDATE … WHERE telegram_id IS NULL … RETURNING`

**Recommendation:** [BEST-PRACTICE] Persist processed `update_id`s (dedup table or Redis SET) and skip re-delivered updates in an update-level middleware; or make `create_draft_ad` idempotent keyed on the originating `message.message_id`/`update_id`. At minimum, guard side-effects (photo writes, translation calls) so a re-delivered update cannot double-create. Effort: medium. Priority: recommended.

---
### EXT-006: Moderation bulk-action API deviates from the §5(e) API contract (403 for unauthenticated instead of 401; no versioning)

| Field | Value |
|-------|-------|
| **ID** | EXT-006 |
| **Severity** | LOW |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/moderation/views/decorators.py:34-49` (`staff_required_api`), `src/backend/apps/moderation/views/api_bulk.py` (bulk endpoint), `src/backend/apps/moderation/urls.py` |
| **Classification** | advisory |
| **Phase checks** | §5(e) API surface security (authn/authz); §7 API version mismatch -> handled, not 500 |

**Description:** `POST /moderation/bulk-action/` is the system's only JSON API. It is guarded by `staff_required_api` (`decorators.py:34-49`), which returns `JsonResponse({"error": "Unauthorized"}, status=403)` for any non-staff caller — **including a fully unauthenticated (`AnonymousUser`) request**. Per RFC 7235 and phase §5(e) ("unauthenticated → 401"), an unauthenticated caller should receive `401` with a `WWW-Authenticate` challenge so the client knows to authenticate, while an authenticated-but-non-staff caller should receive `403`. Conflating both as `403` blurs the authn/authz boundary and breaks standard API-client auth flow. Additionally the moderation API has **no version segment** in its URL (`moderation/urls.py:18` → `path("bulk-action/", …)`, no `/v1/`), so the §7 edge case "API version mismatch (client v1 vs server v2) → handled, not 500" cannot be satisfied: there is no versioning surface to mismatch against and no explicit error path for an unknown version. (Body input-schema validation is the separate CFG-003 concern filed in phase 02 and is not re-asserted here.)

**Evidence:**
- `src/backend/apps/moderation/views/decorators.py:45-46` — `if not (request.user.is_staff or request.user.is_superuser): return JsonResponse({"error": "Unauthorized"}, status=403)` (no branch for unauthenticated → 401)
- `src/backend/apps/moderation/urls.py:18` — `path("bulk-action/", bulk_moderation_action, name="bulk_action")` (no version prefix)
- `src/backend/apps/moderation/views/decorators.py:26-28` — template moderation views use `Http404` for non-staff (deny-by-obscurity), contrasting with the API's 403

**Recommendation:** [BEST-PRACTICE] On API views, return `401` (with `WWW-Authenticate`) when `not request.user.is_authenticated`, else `403` when authenticated-but-not-allowed. Add a version prefix (`/api/v1/moderation/...`) to the JSON endpoint so an unknown version degrades to an explicit `400`/`404` instead of silently matching. Effort: small. Priority: recommended (advisory).

---
## Summary

| Severity | Count | IDs |
|----------|-------|-----|
| CRITICAL | 0 | — |
| HIGH | 1 | EXT-003 |
| MEDIUM | 3 | EXT-001, EXT-002, EXT-005 |
| LOW | 2 | EXT-004, EXT-006 |

## Mandatory Fixes

- **EXT-003** (HIGH): attach a reverse-proxy `limit_req` zone to the public browse surface (`location /`) and to `/moderation/`; cap `selected_items` in the bulk API (e.g. max 100/request).

## Advisory Recommendations

- **EXT-001**: add bounded retry/backoff to the translation client; replace the abandoned-`ThreadPoolExecutor`-future pattern with a bounded `Semaphore` and a real (httpx) timeout+cancel scope; narrow the catch-all `except Exception` to `TimeoutError, RequestException`.
- **EXT-002**: reuse a single module-level `Bot`/session per worker thread; bound delivery threads globally (semaphore/bounded thread pool); retry non-fatal Telegram send errors and honour `retry_after` on 429.
- **EXT-004**: re-declare `Strict-Transport-Security` in `/protected-media/` (or extract security headers into a shared `include` snippet matching the `/static/` pattern); add site-wide `Referrer-Policy` (and `Permissions-Policy` if no cross-origin features are required).
- **EXT-005**: persist processed `update_id`s and skip re-delivered updates at the bot update-middleware level; make `create_draft_ad` idempotent (keyed on `message.message_id`/`update_id`) and guard translation/photo side-effects.
- **EXT-006**: return `401` (with `WWW-Authenticate`) for unauthenticated API callers, `403` for authenticated-non-staff; version the moderation JSON API.

## Doc Updates Needed

(None — every finding is a code/config deviation or best-practice gap; no documentation asserts behaviour that the implementation contradicts, so no `[DOC-UPDATE]` findings are raised.)
